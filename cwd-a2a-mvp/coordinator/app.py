"""
Coordinator agent - orchestrates incident response.

Listens on http://localhost:8001

Responsibilities:
- Expose A2A skill: assign_incident_tasks(incident_text) -> {incident_id, tasks[]}
- Accept HTTP POST /incident from users
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

from common.models import IncidentRequest, TaskAssignmentResponse, Task
from common.langgraph_state import create_coordinator_state, log_state_message
from common.llm_stub import incident_to_tasks
from common.a2a_client import create_delegator_client
from common.redis_utils import subscribe_to_status_events, health_check
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
    incident_id = event.get("incident_id", "unknown")
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


def subscribe_to_incident_updates(incident_id: str):
    """
    Subscribe to Redis Pub/Sub updates for an incident in a background thread.
    
    Args:
        incident_id: Unique incident identifier
    """
    def subscription_thread():
        logger.info(f"Starting Redis subscription for incident {incident_id}")
        try:
            subscribe_to_status_events(incident_id, status_update_callback)
        except Exception as e:
            logger.error(f"Subscription error for {incident_id}: {e}")
    
    # Start subscription in background thread
    thread = threading.Thread(target=subscription_thread, daemon=True)
    active_subscriptions[incident_id] = thread
    thread.start()


async def delegate_tasks_to_delegator(incident_id: str, tasks: list[Task]):
    """
    Send tasks to Delegator via A2A protocol.
    
    Args:
        incident_id: Unique incident identifier
        tasks: List of tasks to delegate
    """
    try:
        delegator_client = create_delegator_client()
        logger.info(f"Calling delegator A2A skill: accept_tasks for incident {incident_id}")
        
        # Call Delegator's accept_tasks skill via A2A
        # This assumes the A2A SDK provides a method to call remote skills
        # Adjust based on actual A2A SDK API
        result = await delegator_client.call_skill(
            skill_name="accept_tasks",
            incident_id=incident_id,
            tasks=[t.model_dump() for t in tasks]
        )
        
        logger.info(f"Delegator accepted tasks for incident {incident_id}: {result}")
    except Exception as e:
        logger.error(f"Failed to delegate tasks to delegator: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup/shutdown.
    """
    # Startup
    logger.info("Coordinator agent starting on port 8001")
    redis_ok = health_check()
    if not redis_ok:
        logger.warning("Redis not available - status updates won't be persisted")
    
    yield
    
    # Shutdown
    logger.info("Coordinator agent shutting down")


# Create FastAPI app
app = FastAPI(
    title="Coordinator Agent",
    description="CWD Coordinator - Incident orchestration and task planning",
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


@app.post("/incident")
async def create_incident(request: IncidentRequest) -> dict:
    """
    HTTP endpoint to submit an incident.
    Internally invokes assign_incident_tasks and delegates to Delegator.
    
    Args:
        request: IncidentRequest with incident_text
        
    Returns:
        JSON response with incident_id and tasks
    """
    try:
        incident_id = str(uuid.uuid4())
        logger.info(f"New incident received: {incident_id} - {request.incident_text[:50]}...")
        
        # Call A2A skill to assign tasks
        response = coordinator_skills.assign_incident_tasks(
            request.incident_text,
            incident_id
        )
        
        # Subscribe to status updates for this incident
        subscribe_to_incident_updates(incident_id)
        logger.info(f"Subscribed to status updates for incident {incident_id}")
        
        # Delegate tasks to Delegator asynchronously
        asyncio.create_task(delegate_tasks_to_delegator(incident_id, response.tasks))
        
        return {
            "status": "success",
            "incident_id": incident_id,
            "tasks": [t.model_dump() for t in response.tasks],
            "message": f"Incident {incident_id} created with {len(response.tasks)} tasks. Monitoring status updates..."
        }
    
    except Exception as e:
        logger.error(f"Error creating incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.a2a.skill(
    name="assign_incident_tasks",
    description="Assign tasks to an incident using LLM analysis"
)
async def a2a_assign_incident_tasks(incident_text: str) -> TaskAssignmentResponse:
    """
    A2A skill endpoint: assign_incident_tasks
    Called by other agents via A2A protocol.
    
    Args:
        incident_text: Description of the incident
        
    Returns:
        TaskAssignmentResponse with incident_id and tasks
    """
    incident_id = str(uuid.uuid4())
    return coordinator_skills.assign_incident_tasks(incident_text, incident_id)


if __name__ == "__main__":
    # Run with uvicorn on port 8001
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
