"""
Deterministic LLM stub for converting incident text to tasks.
Designed to be easily swappable with real LLM providers (OpenAI, Gemini, etc.)
"""

import os
from common.models import Task


def stub_incident_to_tasks(incident_text: str) -> list[Task]:
    """
    Stub LLM that deterministically converts incident text to 2-3 tasks.
    In production, this would call OpenAI, Gemini, or another LLM API.
    
    Args:
        incident_text: Description of the incident
        
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


def incident_to_tasks(incident_text: str) -> list[Task]:
    """
    Route to appropriate LLM implementation based on LLM_PROVIDER env var.
    
    Args:
        incident_text: Description of the incident
        
    Returns:
        List of Task objects
    """
    provider = get_llm_provider()
    
    if provider == "stub":
        return stub_incident_to_tasks(incident_text)
    elif provider == "openai":
        # Placeholder: would import OpenAI and call API
        raise NotImplementedError("OpenAI provider not yet implemented")
    elif provider == "gemini":
        # Placeholder: would import Gemini and call API
        raise NotImplementedError("Gemini provider not yet implemented")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
