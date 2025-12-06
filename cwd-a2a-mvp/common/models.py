"""
Pydantic models for work items, tasks, and status updates.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class Task(BaseModel):
    """Represents a single task derived from a work request."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    priority: str = "normal"  # low, normal, high
    assigned_worker_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "description": "Diagnose service health",
                "priority": "high",
            }
        }


class WorkItem(BaseModel):
    """Represents a work item with associated tasks."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    tasks: list[Task] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "550e8400-e29b-41d4-a716-446655440001",
                "description": "Service X is erroring",
                "tasks": [],
            }
        }


class StatusUpdate(BaseModel):
    """Status update from worker or delegator."""
    status: str  # started, in_progress, completed, failed
    progress: Optional[int] = None  # percentage
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "in_progress",
                "progress": 50,
                "message": "Executing task step 2 of 3"
            }
        }


class WorkRequest(BaseModel):
    """HTTP request to POST /request."""
    description: str


class TaskAssignmentResponse(BaseModel):
    """Response from coordinator's assign_tasks skill."""
    request_id: str
    tasks: list[Task]
