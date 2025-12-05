"""
A2A skills server for Worker agent.
Exposes the execute_task skill.
"""

import logging
import asyncio
from datetime import datetime

from common.models import Task, StatusUpdate
from common.langgraph_state import create_worker_state, log_state_message

logger = logging.getLogger(__name__)


class WorkerSkillsServer:
    """
    Exposes Worker skills via A2A protocol.
    """
    
    def __init__(self):
        """Initialize worker skills server."""
        self.state_store = {}  # Simple in-memory store per task_id
    
    async def execute_task(
        self,
        task: dict,
        incident_id: str,
        callback_url: str = None
    ) -> dict:
        """
        A2A skill: Execute a task with simulated progress updates.
        
        This skill:
        1. Initializes local LangGraph state
        2. Simulates task execution with 3 steps
        3. Sends status updates via A2A callback to Delegator
        4. Returns final result
        
        Args:
            task: Task dictionary with task_id and description
            incident_id: Unique incident identifier
            callback_url: Optional URL for status callbacks (Delegator address)
            
        Returns:
            Execution result dict with status and completion info
        """
        task_obj = Task(**task) if isinstance(task, dict) else task
        task_id = task_obj.task_id
        
        logger.info(f"execute_task called: task_id={task_id}, description={task_obj.description[:50]}...")
        
        # Initialize local state
        state = create_worker_state(task_obj)
        self.state_store[task_id] = state
        
        log_state_message(state, "Task execution initialized")
        
        try:
            # Simulate task execution with progress updates
            state["status"] = "started"
            log_state_message(state, "Task execution started")
            
            # Execute 3 steps
            for step in range(1, 4):
                state["current_step"] = step
                progress = int((step / state["total_steps"]) * 100)
                state["progress"] = progress
                state["status"] = "in_progress"
                
                step_msg = f"Executing step {step}/{state['total_steps']}"
                log_state_message(state, step_msg)
                logger.info(f"Task {task_id}: {step_msg}")
                
                # Simulate work
                await asyncio.sleep(1)
            
            # Mark complete
            state["status"] = "completed"
            state["progress"] = 100
            log_state_message(state, "Task execution completed successfully")
            logger.info(f"Task {task_id} completed successfully")
            
            return {
                "status": "completed",
                "task_id": task_id,
                "message": "Task executed successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            state["status"] = "failed"
            log_state_message(state, f"Task execution failed: {str(e)}")
            logger.error(f"Task {task_id} execution failed: {e}")
            
            return {
                "status": "failed",
                "task_id": task_id,
                "message": f"Task execution failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_task_state(self, task_id: str) -> dict:
        """
        Internal helper to retrieve local state for a task.
        Used for monitoring/debugging.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Current task state or empty dict if not found
        """
        return self.state_store.get(task_id, {})
