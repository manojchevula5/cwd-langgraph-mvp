"""
MLflow utilities for logging agent-to-agent communication.
"""

import os
import logging
import json
import mlflow
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Experiment name for CWD Agent interactions
# EXPERIMENT_NAME = "/Shared/CWD_Agent_Interactions"
EXPERIMENT_NAME = "CWD_Agent_Interactions"

def setup_mlflow():
    """Confirms MLflow is ready or sets the experiment."""
    try:
        # Check if tracking URI is set, otherwise default might be local
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        
        mlflow.set_experiment(EXPERIMENT_NAME)
    except Exception as e:
        logger.warning(f"Failed to setup MLflow experiment: {e}")

def create_root_run(request_id: str, description: str = "") -> Optional[str]:
    """
    Start a root run for a new request.
    Returns the run_id.
    """
    try:
        run_name = f"request_id::{request_id}"
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.set_tag("request_id", request_id)
            mlflow.set_tag("role", "root")
            if description:
                mlflow.log_param("description", description)
            return run.info.run_id
    except Exception as e:
        logger.error(f"Failed to create root run: {e}")
        return None

def log_agent_communication(
    request_id: str,
    sender: str,
    receiver: str,
    action: str,
    payload: Dict[str, Any],
    response: Dict[str, Any],
    status: str = "success",
    parent_run_id: Optional[str] = None
):
    """
    Log a single request-response interaction between agents to MLflow.
    
    Args:
        request_id: Context ID for the workflow
        sender: Name of sending agent (e.g., "Coordinator")
        receiver: Name of receiving agent (e.g., "Delegator")
        action: The action or skill being called (e.g., "accept_tasks")
        payload: The arguments passed to the call
        response: The result returned
        status: success or failed
    """
    try:
        # Create a run name based on timestamp and action
        run_name = f"{sender}_to_{receiver}_{action}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Start a nested run if there is an active run, otherwise a new run
        # For distributed tracing in MLflow, we link via tags if we can't be in the same process context.
        tags = {
            "request_id": request_id,
            "sender": sender,
            "receiver": receiver,
            "action": action,
            "status": status
        }
        
        if parent_run_id:
            # linking to parent run via tag expected by MLflow UI for nesting
            tags["mlflow.parentRunId"] = parent_run_id
        
        with mlflow.start_run(run_name=run_name, nested=True, tags=tags) as run:
            # Log params (summary of payload)
            # We flatten crucial info or just log keys
            mlflow.log_param("payload_keys", list(payload.keys()))
            
            # Log full payload and response as artifacts (JSON files)
            mlflow.log_dict(payload, "request_payload.json")
            mlflow.log_dict(response, "response_payload.json")
            
            # Use metrics for simple numeric data if applicable, e.g. payload size
            mlflow.log_metric("payload_size_bytes", len(str(payload)))
            mlflow.log_metric("response_size_bytes", len(str(response)))
            
            logger.info(f"Logged MLflow run {run.info.run_id} for {sender}->{receiver} [{action}]")

    except Exception as e:
        # We don't want logging to break the application flow
        logger.error(f"Failed to log to MLflow: {e}")
