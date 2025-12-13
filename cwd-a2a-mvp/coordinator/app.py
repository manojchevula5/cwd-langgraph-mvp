"""
Coordinator agent - orchestrates work result.

Listens on http://localhost:8001

Responsibilities:
- Expose A2A skill: assign_tasks(description) -> {request_id, tasks[]}
- Accept HTTP POST /request from users
- Delegate tasks to Delegator via A2A protocol
- Subscribe to Redis Pub/Sub for status updates and log them
"""

import os
import sys
import logging
import asyncio
import threading
import uuid
from contextlib import asynccontextmanager

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import httpx

from common.models import WorkRequest, TaskAssignmentResponse, Task
from common.langgraph_state import create_coordinator_state, log_state_message
from common.llm_stub import request_to_tasks
from common.redis_utils import subscribe_to_status_events, health_check
from common.redis_utils import subscribe_to_status_events, health_check
from common.mlflow_utils import setup_mlflow, log_agent_communication, create_root_run
from coordinator.a2a_server import CoordinatorSkillsServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [COORDINATOR] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Global skills server
coordinator_skills = CoordinatorSkillsServer()

# Track active subscriptions
active_subscriptions = {}


def status_update_callback(event: dict):
    """
    Callback for Redis Pub/Sub status updates.
    Logs and displays status updates to console.
    """
    request_id = event.get("request_id", "unknown")
    task_id = event.get("task_id", "unknown")
    status = event.get("status", "unknown")
    progress = event.get("progress", None)
    message = event.get("message", "")
    timestamp = event.get("timestamp", "")
    
    log_msg = f"[{timestamp}] Task {task_id}: {status}"
    if progress is not None:
        log_msg += f" ({progress}%)"
    if message:
        log_msg += f" - {message}"
    
    logger.info(f"📊 Status Update: {log_msg}")
    print(f"  ✓ {log_msg}")


def subscribe_to_request_updates(request_id: str):
    """
    Subscribe to Redis Pub/Sub updates for a request in a background thread.
    
    Args:
        request_id: Unique request identifier
    """
    def subscription_thread():
        logger.info(f"Starting Redis subscription for request {request_id}")
        try:
            subscribe_to_status_events(request_id, status_update_callback)
        except Exception as e:
            logger.error(f"Subscription error for {request_id}: {e}")
    
    # Start subscription in background thread
    thread = threading.Thread(target=subscription_thread, daemon=True)
    active_subscriptions[request_id] = thread
    thread.start()


async def delegate_tasks_to_delegator(request_id: str, tasks: list[Task]):
    """
    Send tasks to Delegator via A2A HTTP protocol.
    
    Args:
        request_id: Unique request identifier
        tasks: List of tasks to delegate
    """
    try:
        delegator_url = os.getenv("DELEGATOR_URL", "http://localhost:8002")
        
        # Step 1: Call accept_tasks
        accept_tasks_url = f"{delegator_url}/a2a/accept_tasks"
        logger.info(f"Calling delegator A2A skill: accept_tasks for request {request_id}")
        
        payload = {
            "request_id": request_id,
            "tasks": [t.model_dump() for t in tasks]
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(accept_tasks_url, json=payload, timeout=30.0)
            response.raise_for_status()
            result = response.json()
        
        logger.info(f"Delegator accepted tasks for request {request_id}: {result}")
        
        # Get run_id from tasks if available (assuming all tasks have same run_id)
        parent_run_id = tasks[0].mlflow_run_id if tasks else None

        # Log to MLflow
        log_agent_communication(
            request_id=request_id,
            sender="Coordinator",
            receiver="Delegator",
            action="accept_tasks",
            payload=payload,
            response=result,
            parent_run_id=parent_run_id
        )
        
        # Step 2: Trigger delegation to workers
        delegate_url = f"{delegator_url}/a2a/delegate_to_workers"
        logger.info(f"Calling delegator A2A skill: delegate_to_workers for request {request_id}")
        
        delegate_payload = {"request_id": request_id, "mlflow_run_id": parent_run_id}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(delegate_url, json=delegate_payload, timeout=30.0)
            response.raise_for_status()
            delegate_result = response.json()
        
        logger.info(f"Delegator delegated tasks to workers for request {request_id}: {delegate_result}")

        # Log to MLflow
        log_agent_communication(
            request_id=request_id,
            sender="Coordinator",
            receiver="Delegator",
            action="delegate_to_workers",
            payload=delegate_payload,
            response=delegate_result,
            parent_run_id=parent_run_id
        )
    except Exception as e:
        logger.error(f"Failed to delegate tasks to delegator: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup/shutdown.
    """
    # Startup
    logger.info("Coordinator agent starting on port 8001")
    setup_mlflow()
    redis_ok = health_check()
    if not redis_ok:
        logger.warning("Redis not available - status updates won't be persisted")
    
    yield
    
    # Shutdown
    logger.info("Coordinator agent shutting down")


# Create FastAPI app
app = FastAPI(
    title="Coordinator Agent",
    description="CWD Coordinator - Work request orchestration and task planning",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent": "coordinator",
        "port": 8001,
        "redis": health_check()
    }


@app.post("/request")
async def create_request(request: WorkRequest) -> dict:
    """
    HTTP endpoint to submit a work request.
    Internally invokes assign_tasks and delegates to Delegator.
    
    Args:
        request: WorkRequest with description
        
    Returns:
        JSON response with request_id and tasks
    """
    try:
        request_id = str(uuid.uuid4())
        logger.info(f"New request received: {request_id} - {request.description[:50]}...")
        
        # Start MLflow root run
        root_run_id = create_root_run(request_id, request.description)
        logger.info(f"Created MLflow root run: {root_run_id}")
        
        # Call A2A skill to assign tasks
        response = coordinator_skills.assign_tasks(
            request.description,
            request_id
        )
        
        # Add run_id to tasks
        if root_run_id:
            for task in response.tasks:
                task.mlflow_run_id = root_run_id
        
        # Subscribe to status updates for this request
        subscribe_to_request_updates(request_id)
        logger.info(f"Subscribed to status updates for request {request_id}")
        
        # Delegate tasks to Delegator asynchronously
        asyncio.create_task(delegate_tasks_to_delegator(request_id, response.tasks))
        
        return {
            "status": "success",
            "request_id": request_id,
            "root_run_id": root_run_id,
            "tasks": [t.model_dump() for t in response.tasks],
            "message": f"Request {request_id} created with {len(response.tasks)} tasks. Monitoring status updates..."
        }
    
    except Exception as e:
        logger.error(f"Error creating request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/a2a/assign_tasks")
async def a2a_assign_tasks(request: WorkRequest) -> dict:
    """
    A2A skill endpoint: assign_tasks
    Called by other agents via A2A HTTP protocol.
    
    Args:
        request: WorkRequest with description
        
    Returns:
        JSON response with request_id and tasks
    """
    try:
        request_id = str(uuid.uuid4())
        response = coordinator_skills.assign_tasks(request.description, request_id)
        return response.model_dump()
    except Exception as e:
        logger.error(f"Error in A2A assign_tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Copy .env if it doesn't exist
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            import shutil
            shutil.copy(".env.example", ".env")
    
    # Load env vars
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run with uvicorn on port 8001
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
