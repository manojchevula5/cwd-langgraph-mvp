"""
A2A client helper for creating clients to other agents.
"""

import os
from typing import Any, Optional


def get_a2a_client(agent_url: str):
    """
    Factory function to create an A2A client to a specific agent.
    
    Args:
        agent_url: Base URL of the target agent (e.g., http://localhost:8001)
        
    Returns:
        An A2A SDK client instance
    """
    # Import here to avoid circular dependencies
    try:
        from a2a_sdk import Client
    except ImportError:
        raise ImportError("a2a-sdk not installed. Install with: pip install a2a-sdk[http-server]")
    
    # A2A SDK client initialization
    # The actual SDK may use different init patterns; adjust as needed
    client = Client(base_url=agent_url)
    return client


def create_coordinator_client() -> Any:
    """Create A2A client to Coordinator."""
    url = os.getenv("COORDINATOR_URL", "http://localhost:8001")
    return get_a2a_client(url)


def create_delegator_client() -> Any:
    """Create A2A client to Delegator."""
    url = os.getenv("DELEGATOR_URL", "http://localhost:8002")
    return get_a2a_client(url)


def create_worker_client(worker_url: Optional[str] = None) -> Any:
    """Create A2A client to Worker."""
    if worker_url is None:
        worker_url = os.getenv("WORKER_URL", "http://localhost:8003")
    return get_a2a_client(worker_url)
