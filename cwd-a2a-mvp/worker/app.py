"""
Worker agent - executes assigned tasks.

Listens on http://localhost:8003

Responsibilities:
- Expose A2A skill: execute_task(task) -> execution result
- Receive tasks from Delegator via A2A
- Simulate task execution with progress updates
- Report status back to Delegator via A2A
- Maintain local LangGraph state per task
- NO direct Redis access (as per architecture requirements)
"""

import os
import sys
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from common.models import Task
from worker.a2a_server import WorkerSkillsServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WORKER] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Global skills server
worker_skills = WorkerSkillsServer()


class ExecuteTaskRequest(BaseModel):
    """Request to execute a task."""
    task: dict
    incident_id: str = None
    callback_url: str = None


async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup/shutdown.
    """
    # Startup
    logger.info("Worker agent starting on port 8003")
    
    yield
    
    # Shutdown
    logger.info("Worker agent shutting down")


# Create FastAPI app
app = FastAPI(
    title="Worker Agent",
    description="CWD Worker - Task execution engine",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent": "worker",
        "port": 8003
    }


@app.post("/execute")
async def execute_task_http(request: ExecuteTaskRequest) -> dict:
    """
    HTTP endpoint to execute a task.
    Also callable via A2A protocol.
    
    Args:
        request: ExecuteTaskRequest with task details
        
    Returns:
        Execution result dict
    """
    try:
        result = await worker_skills.execute_task(
            task=request.task,
            incident_id=request.incident_id,
            callback_url=request.callback_url
        )
        logger.info(f"Task execution completed: {result['status']}")
        return result
    except Exception as e:
        logger.error(f"Error executing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/a2a/execute_task")
async def a2a_execute_task(request: ExecuteTaskRequest) -> dict:
    """
    A2A skill endpoint: execute_task
    Called by Delegator via A2A HTTP protocol.
    
    Args:
        request: ExecuteTaskRequest with task details
        
    Returns:
        Execution result dict
    """
    try:
        result = await worker_skills.execute_task(
            task=request.task,
            incident_id=request.incident_id,
            callback_url=request.callback_url
        )
        logger.info(f"Task execution completed: {result['status']}")
        return result
    except Exception as e:
        logger.error(f"Error executing task: {e}")
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
    
    # Run with uvicorn on port 8003
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8003,
        log_level="info"
    )
