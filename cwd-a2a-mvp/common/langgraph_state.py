"""
LangGraph state definitions for each agent.
Minimal TypedDict + simple state management patterns.
"""

from typing import TypedDict, Optional
from datetime import datetime
from common.models import Task


class CoordinatorState(TypedDict):
    """
    Local state for Coordinator agent.
    Tracks incident planning and task assignment context.
    """
    incident_id: str
    incident_text: str
    tasks: list[Task]
    status: str  # planning, assigned, monitoring, completed
    messages: list[dict]  # List of {timestamp, message} for local logging
    redis_subscription_active: bool


class DelegatorState(TypedDict):
    """
    Local state for Delegator agent.
    Tracks task routing and worker assignments.
    """
    incident_id: str
    tasks: list[Task]
    active_tasks: dict  # {task_id: {status, worker_url, started_at}}
    completed_tasks: list[str]  # list of task_ids
    failed_tasks: list[str]
    status: str  # idle, accepting, delegating, monitoring, completed
    messages: list[dict]  # Local event log


class WorkerState(TypedDict):
    """
    Local state for Worker agent.
    Tracks task execution lifecycle.
    """
    task_id: str
    task_description: str
    status: str  # idle, started, in_progress, completed, failed
    progress: int  # 0-100
    current_step: int
    total_steps: int
    messages: list[dict]  # Execution log


def create_coordinator_state(incident_id: str, incident_text: str) -> CoordinatorState:
    """Initialize coordinator state for a new incident."""
    return {
        "incident_id": incident_id,
        "incident_text": incident_text,
        "tasks": [],
        "status": "planning",
        "messages": [],
        "redis_subscription_active": False,
    }


def create_delegator_state(incident_id: str, tasks: list[Task]) -> DelegatorState:
    """Initialize delegator state for incident tasks."""
    return {
        "incident_id": incident_id,
        "tasks": tasks,
        "active_tasks": {},
        "completed_tasks": [],
        "failed_tasks": [],
        "status": "idle",
        "messages": [],
    }


def create_worker_state(task: Task) -> WorkerState:
    """Initialize worker state for a task."""
    return {
        "task_id": task.task_id,
        "task_description": task.description,
        "status": "idle",
        "progress": 0,
        "current_step": 0,
        "total_steps": 3,  # Simulate 3 steps per task
        "messages": [],
    }


def log_state_message(state: dict, message: str) -> None:
    """Append a timestamped message to state."""
    state["messages"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "message": message,
    })
