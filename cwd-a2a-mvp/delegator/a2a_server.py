"""
A2A skills server for Delegator agent.
Exposes accept_tasks and delegate_to_workers skills.
"""

import logging
import asyncio
import httpx
from typing import Optional

from common.models import Task
from common.langgraph_state import create_delegator_state, log_state_message
from common.redis_utils import write_task_status, publish_status_event
from common.mlflow_utils import log_agent_communication

logger = logging.getLogger(__name__)


class DelegatorSkillsServer:
    """
    Exposes Delegator skills via A2A protocol.
    """
    
    def __init__(self):
        """Initialize delegator skills server."""
        self.state_store = {}  # Simple in-memory store per request_id
        self.worker_urls = ["http://localhost:8003"]  # Config: add more workers here
    
    def accept_tasks(self, request_id: str, tasks: list[dict]) -> dict:
        """
        A2A skill: Accept tasks from Coordinator.
        
        Args:
            request_id: Unique request identifier
            tasks: List of task dictionaries
            
        Returns:
            Acknowledgment with request_id and task count
        """
        logger.info(f"accept_tasks called: request_id={request_id}, task_count={len(tasks)}")
        
        # Convert task dicts to Task objects
        task_objects = [Task(**t) if isinstance(t, dict) else t for t in tasks]
        
        # Initialize local state
        state = create_delegator_state(request_id, task_objects)
        self.state_store[request_id] = state
        
        log_state_message(state, f"Accepted {len(task_objects)} tasks from Coordinator")
        
        return {
            "status": "accepted",
            "request_id": request_id,
            "task_count": len(task_objects)
        }
    
    def delegate_to_workers(self, request_id: str) -> dict:
        """
        A2A skill: Delegate tasks to workers.
        Distributes tasks across available workers and initiates execution.
        
        Args:
            request_id: Unique request identifier
            
        Returns:
            Status dict with delegation result
        """
        logger.info(f"delegate_to_workers called: request_id={request_id}")
        
        state = self.state_store.get(request_id)
        if not state:
            logger.error(f"No state found for request {request_id}")
            return {"status": "error", "message": f"No state for {request_id}"}
        
        tasks = state["tasks"]
        logger.info(f"Delegating {len(tasks)} tasks to {len(self.worker_urls)} worker(s)")
        
        # Simple round-robin assignment: task_index % worker_count
        for idx, task in enumerate(tasks):
            worker_url = self.worker_urls[idx % len(self.worker_urls)]
            task.assigned_worker_url = worker_url
            
            # Initialize task tracking in local state
            state["active_tasks"][task.task_id] = {
                "status": "queued",
                "worker_url": worker_url,
                "started_at": None,
            }
            
            log_state_message(state, f"Assigned task {task.task_id} to {worker_url}")
            
            # Write initial status to Redis
            write_task_status(
                request_id,
                task.task_id,
                {
                    "status": "queued",
                    "worker_id": worker_url,
                    "message": "Task queued for execution"
                }
            )
        
        state["status"] = "delegating"
        
        return {
            "status": "delegated",
            "request_id": request_id,
            "delegated_count": len(tasks)
        }
    
    async def execute_task_on_worker(
        self,
        request_id: str,
        task: Task,
        worker_url: str,
        retry_count: int = 1
    ) -> bool:
        """
        Execute a task on a worker via A2A HTTP protocol and monitor status.
        Includes retry logic and Redis updates.
        
        Args:
            request_id: Unique request identifier
            task: Task to execute
            worker_url: Worker agent URL
            retry_count: Number of retries on failure
            
        Returns:
            True if successful, False if failed after retries
        """
        state = self.state_store.get(request_id)
        if not state:
            logger.error(f"No state for request {request_id}")
            return False
        
        attempt = 0
        while attempt <= retry_count:
            attempt += 1
            try:
                logger.info(f"Executing task {task.task_id} on {worker_url} (attempt {attempt})")
                
                # Mark task as executing
                state["active_tasks"][task.task_id]["status"] = "executing"
                write_task_status(
                    request_id,
                    task.task_id,
                    {
                        "status": "executing",
                        "worker_id": worker_url,
                        "message": f"Execution attempt {attempt} started"
                    }
                )
                publish_status_event(
                    request_id,
                    {
                        "task_id": task.task_id,
                        "status": "executing",
                        "message": f"Worker starting execution"
                    }
                )
                
                # Call worker's execute_task skill via A2A HTTP protocol
                skill_url = f"{worker_url}/a2a/execute_task"
                payload = {
                    "task": task.model_dump(),
                    "request_id": request_id,
                    "callback_url": worker_url
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(skill_url, json=payload, timeout=30.0)
                    response.raise_for_status()
                    result = response.json()

                # Log to MLflow
                log_agent_communication(
                    request_id=request_id,
                    sender="Delegator",
                    receiver=f"Worker({worker_url})",
                    action="execute_task",
                    payload=payload,
                    response=result,
                    parent_run_id=task.mlflow_run_id
                )
                
                # If successful, mark complete
                state["active_tasks"][task.task_id]["status"] = "completed"
                state["completed_tasks"].append(task.task_id)
                
                write_task_status(
                    request_id,
                    task.task_id,
                    {
                        "status": "completed",
                        "worker_id": worker_url,
                        "message": "Task completed successfully"
                    }
                )
                publish_status_event(
                    request_id,
                    {
                        "task_id": task.task_id,
                        "status": "completed",
                        "message": "Task execution completed"
                    }
                )
                
                logger.info(f"Task {task.task_id} completed successfully")
                return True
            
            except Exception as e:
                logger.warning(f"Task {task.task_id} failed on attempt {attempt}: {e}")
                
                if attempt <= retry_count:
                    logger.info(f"Retrying task {task.task_id}")
                else:
                    # Mark as failed
                    state["active_tasks"][task.task_id]["status"] = "failed"
                    state["failed_tasks"].append(task.task_id)
                    
                    write_task_status(
                        request_id,
                        task.task_id,
                        {
                            "status": "failed",
                            "worker_id": worker_url,
                            "message": f"Task failed after {retry_count + 1} attempts"
                        }
                    )
                    publish_status_event(
                        request_id,
                        {
                            "task_id": task.task_id,
                            "status": "failed",
                            "message": "Task execution failed"
                        }
                    )
                    
                    logger.error(f"Task {task.task_id} failed permanently")
                    return False
        
        return False
    
    def get_request_state(self, request_id: str) -> dict:
        """
        Internal helper to retrieve local state for a request.
        Used for monitoring/debugging.
        
        Args:
            request_id: Unique request identifier
            
        Returns:
            Current request state or empty dict if not found
        """
        return self.state_store.get(request_id, {})
