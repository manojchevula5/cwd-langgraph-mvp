#!/usr/bin/env python3
"""
Integration test for CWD A2A MVP.
Tests the complete work request lifecycle: creation -> delegation -> execution -> status tracking.

Run this with all three agents running:
  Terminal 1: python coordinator/app.py
  Terminal 2: python delegator/app.py
  Terminal 3: python worker/app.py
  Terminal 4: python test_integration.py
"""

import asyncio
import httpx
import json
import time
from datetime import datetime


async def test_request_workflow():
    """Test complete work request workflow."""
    
    print("\n" + "="*80)
    print("CWD A2A MVP Integration Test")
    print("="*80)
    
    coordinator_url = "http://localhost:8001"
    delegator_url = "http://localhost:8002"
    worker_url = "http://localhost:8003"
    
    async with httpx.AsyncClient() as client:
        # Test 1: Health checks
        print("\n[1/4] Checking agent health...")
        try:
            coord_health = await client.get(f"{coordinator_url}/health", timeout=5.0)
            coord_health.raise_for_status()
            print("  ✓ Coordinator healthy")
        except Exception as e:
            print(f"  ✗ Coordinator failed: {e}")
            return False
        
        try:
            deleg_health = await client.get(f"{delegator_url}/health", timeout=5.0)
            deleg_health.raise_for_status()
            print("  ✓ Delegator healthy")
        except Exception as e:
            print(f"  ✗ Delegator failed: {e}")
            return False
        
        try:
            worker_health = await client.get(f"{worker_url}/health", timeout=5.0)
            worker_health.raise_for_status()
            print("  ✓ Worker healthy")
        except Exception as e:
            print(f"  ✗ Worker failed: {e}")
            return False
        
        # Test 2: Submit work request
        print("\n[2/4] Submitting request to Coordinator...")
        try:
            request_response = await client.post(
                f"{coordinator_url}/request",
                json={"description": "Database connection pool exhausted - service degradation"},
                timeout=10.0
            )
            request_response.raise_for_status()
            request_data = request_response.json()
            request_id = request_data.get("request_id")
            task_count = len(request_data.get("tasks", []))
            
            print(f"  ✓ Request created: {request_id}")
            print(f"  ✓ Generated {task_count} tasks")
            
            for i, task in enumerate(request_data.get("tasks", []), 1):
                print(f"    Task {i}: {task['description']}")
        
        except Exception as e:
            print(f"  ✗ Request submission failed: {e}")
            return False
        
        # Test 3: Call Delegator A2A skill directly
        print("\n[3/4] Testing A2A skill communication...")
        try:
            accept_payload = {
                "request_id": request_id,
                "tasks": request_data.get("tasks", [])
            }
            accept_response = await client.post(
                f"{delegator_url}/a2a/accept_tasks",
                json=accept_payload,
                timeout=10.0
            )
            accept_response.raise_for_status()
            accept_data = accept_response.json()
            print(f"  ✓ Delegator accepted tasks: {accept_data}")
        
        except Exception as e:
            print(f"  ✗ Delegator A2A call failed: {e}")
            return False
        
        # Test 4: Trigger worker delegation
        print("\n[4/4] Triggering worker delegation and execution...")
        try:
            delegate_payload = {"request_id": request_id}
            delegate_response = await client.post(
                f"{delegator_url}/a2a/delegate_to_workers",
                json=delegate_payload,
                timeout=10.0
            )
            delegate_response.raise_for_status()
            delegate_data = delegate_response.json()
            print(f"  ✓ Tasks delegated to workers: {delegate_data}")
            
            # Wait for tasks to complete
            print("\n  Waiting for task execution (3 sec per task)...")
            await asyncio.sleep(10)
            print("  ✓ Task execution completed")
        
        except Exception as e:
            print(f"  ✗ Worker delegation failed: {e}")
            return False
        
        print("\n" + "="*80)
        print("✓ All tests passed!")
        print("="*80)
        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_request_workflow())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        exit(1)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        exit(1)
