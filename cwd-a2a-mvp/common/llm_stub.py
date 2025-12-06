"""
Deterministic LLM stub for converting incident text to tasks.
Designed to be easily swappable with real LLM providers (OpenAI, Gemini, etc.)
"""

import os
from common.models import Task


def stub_request_to_tasks(description: str) -> list[Task]:
    """
    Stub LLM that deterministically converts description to 2-3 tasks.
    In production, this would call OpenAI, Gemini, or another LLM API.
    
    Args:
        description: Description of the work request
        
    Returns:
        List of Task objects
    """
    # Hardcoded tasks for MVP demonstration
    tasks = [
        Task(
            description="Diagnose service status and root cause",
            priority="high",
        ),
        Task(
            description="Apply fix or mitigation",
            priority="high",
        ),
        Task(
            description="Verify recovery and health check",
            priority="normal",
        ),
    ]
    
    return tasks


def get_llm_provider() -> str:
    """Get the configured LLM provider from env vars."""
    return os.getenv("LLM_PROVIDER", "stub")


def request_to_tasks(description: str) -> list[Task]:
    """
    Route to appropriate LLM implementation based on LLM_PROVIDER env var.
    
    Args:
        description: Description of the work request
        
    Returns:
        List of Task objects
    """
    provider = get_llm_provider()
    
    if provider == "stub":
        return stub_request_to_tasks(description)
    elif provider == "openai":
        # Placeholder: would import OpenAI and call API
        raise NotImplementedError("OpenAI provider not yet implemented")
    elif provider == "gemini":
        # Placeholder: would import Gemini and call API
        raise NotImplementedError("Gemini provider not yet implemented")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
