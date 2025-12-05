"""
A2A client helper for creating clients to other agents.

Note: Since we're using HTTP-based A2A protocol (POST to /a2a/skill_name endpoints),
this module provides convenience functions for building A2A URLs rather than SDK clients.
"""

import os
from typing import Any, Optional


def get_a2a_skill_url(agent_url: str, skill_name: str) -> str:
    """
    Get the A2A skill URL for a specific agent.
    
    Args:
        agent_url: Base URL of the target agent (e.g., http://localhost:8001)
        skill_name: Name of the A2A skill (e.g., "accept_tasks")
        
    Returns:
        Full URL to the skill endpoint
    """
    return f"{agent_url}/a2a/{skill_name}"


def get_coordinator_skill_url(skill_name: str) -> str:
    """Get A2A skill URL for Coordinator."""
    url = os.getenv("COORDINATOR_URL", "http://localhost:8001")
    return get_a2a_skill_url(url, skill_name)


def get_delegator_skill_url(skill_name: str) -> str:
    """Get A2A skill URL for Delegator."""
    url = os.getenv("DELEGATOR_URL", "http://localhost:8002")
    return get_a2a_skill_url(url, skill_name)


def get_worker_skill_url(skill_name: str, worker_url: Optional[str] = None) -> str:
    """Get A2A skill URL for Worker."""
    if worker_url is None:
        worker_url = os.getenv("WORKER_URL", "http://localhost:8003")
    return get_a2a_skill_url(worker_url, skill_name)
