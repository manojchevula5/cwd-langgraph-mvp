"""
Delegator agent - routes and monitors task execution.

Listens on http://localhost:8002

Responsibilities:
- Expose A2A skills: accept_tasks(request_id, tasks[]) and delegate_to_workers(request_id)
- Receive tasks from Coordinator via A2A
- Delegate tasks to Workers via A2A protocol
- Write task status to Redis hashes
- Publish status events to Redis Pub/Sub
- Handle worker failures with retry logic
"""

import os
import sys
import logging
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx

from common.models import Task, StatusUpdate
from common.redis_utils import health_check
from common.mlflow_utils import setup_mlflow
from delegator.a2a_server import DelegatorSkillsServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [DELEGATOR] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Global skills server
delegator_skills = DelegatorSkillsServer()


class AcceptTasksRequest(BaseModel):
    """Request to accept tasks from Coordinator."""
    request_id: str
    tasks: list[dict]
    mlflow_run_id: str = None


class DelegateTasksRequest(BaseModel):
    """Request to delegate tasks to workers."""
    request_id: str
    mlflow_run_id: str = None


async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup/shutdown.
    """
    # Startup
    logger.info("Delegator agent starting on port 8002")
    setup_mlflow()
    redis_ok = health_check()
    if not redis_ok:
        logger.warning("Redis not available - task status won't be persisted")
    
    yield
    
    # Shutdown
    logger.info("Delegator agent shutting down")


# Create FastAPI app
app = FastAPI(
    title="Delegator Agent",
    description="CWD Delegator - Task routing and worker management",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent": "delegator",
        "port": 8002,
        "redis": health_check()
    }


@app.post("/accept-tasks")
async def accept_tasks_http(request: AcceptTasksRequest) -> dict:
    """
    HTTP endpoint for Coordinator to submit tasks.
    Also callable via A2A protocol.
    
    Args:
        request: AcceptTasksRequest with request_id and tasks
        
    Returns:
        Acknowledgment dict
    """
    try:
        result = delegator_skills.accept_tasks(request.request_id, request.tasks)
        logger.info(f"Tasks accepted for request {request.request_id}")
        return result
    except Exception as e:
        logger.error(f"Error accepting tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/delegate-tasks")
async def delegate_tasks_http(request: DelegateTasksRequest) -> dict:
    """
    HTTP endpoint to trigger delegation of accepted tasks to workers.
    
    Args:
        request: DelegateTasksRequest with request_id
        
    Returns:
        Delegation status dict
    """
    try:
        result = delegator_skills.delegate_to_workers(request.request_id)
        
        # Start execution of tasks asynchronously
        request_id = request.request_id
        state = delegator_skills.get_request_state(request_id)
        
        if state and state["tasks"]:
            # Launch all task executions concurrently
            tasks = state["tasks"]
            async def run_tasks():
                execution_coros = [
                    delegator_skills.execute_task_on_worker(
                        request_id,
                        task,
                        task.assigned_worker_url or "http://localhost:8003"
                    )
                    for task in tasks
                ]
                await asyncio.gather(*execution_coros, return_exceptions=True)
            asyncio.create_task(run_tasks())
            logger.info(f"Started execution of {len(tasks)} tasks for request {request_id}")
        
        return result
    except Exception as e:
        logger.error(f"Error delegating tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/a2a/accept_tasks")
async def a2a_accept_tasks(request: AcceptTasksRequest) -> dict:
    """
    A2A skill endpoint: accept_tasks
    Called by Coordinator via A2A HTTP protocol.
    
    Args:
        request: AcceptTasksRequest with request_id and tasks
        
    Returns:
        Acknowledgment dict
    """
    return delegator_skills.accept_tasks(request.request_id, request.tasks)


@app.post("/a2a/delegate_to_workers")
async def a2a_delegate_to_workers(request: DelegateTasksRequest) -> dict:
    """
    A2A skill endpoint: delegate_to_workers
    Called internally or by Coordinator after accept_tasks.
    
    Args:
        request: DelegateTasksRequest with request_id
        
    Returns:
        Delegation status dict
    """
    result = delegator_skills.delegate_to_workers(request.request_id)
    
    # Start execution asynchronously
    request_id = request.request_id
    state = delegator_skills.get_request_state(request_id)
    
    if state and state["tasks"]:
        tasks = state["tasks"]
        async def run_tasks():
            execution_coros = [
                delegator_skills.execute_task_on_worker(
                    request_id,
                    task,
                    task.assigned_worker_url or "http://localhost:8003"
                )
                for task in tasks
            ]
            await asyncio.gather(*execution_coros, return_exceptions=True)
        asyncio.create_task(run_tasks())
    
    return result


if __name__ == "__main__":
    # Copy .env if it doesn't exist
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            import shutil
            shutil.copy(".env.example", ".env")
    
    # Load env vars
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run with uvicorn on port 8002
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )
