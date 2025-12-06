# CWD A2A MVP: Detailed Workflow & Debugging Guide

This document traces the complete execution flow of a single work request through the Coordinator-Delegator-Worker system. It details function calls, state changes, variable updates, and network interactions at every stage.

**Scenario**: User sends a request `POST /request` to the Coordinator.
**Input**: `{"description": "Service X is experiencing errors and timeouts"}`

---

## 🚀 Phase 1: Request Initialization (Coordinator)

**Trigger**: User (Client) -> `POST http://localhost:8001/request`

### 1.1 Endpoint Entry
- **File**: `coordinator/app.py`
- **Function**: `create_request(request: WorkRequest)`
- **Variables**:
  - `request.description`: "Service X is experiencing errors and timeouts"
  - `request_id`: Generated UUID (e.g., `550e8400...`)

### 1.2 Task Planning
- **Call**: `coordinator_skills.assign_tasks(description, request_id)`
- **File**: `coordinator/a2a_server.py`
- **Actions**:
  1. **State Init**: `create_coordinator_state` called.
     - `self.state_store[request_id]` = `{ status: "planning", tasks: [], ... }`
  2. **LLM Call**: `request_to_tasks` (LLM Stub) is invoked.
     - **Returns**: List of 3 `Task` objects (Diagnose, Fix, Verify).
  3. **State Update**:
     - `state["tasks"]` = `[Task(id=..., desc="Diagnose..."), ...]`
     - `state["status"]` = `"assigned"`
- **Return**: `TaskAssignmentResponse` object.

### 1.3 Subscription Setup
- **Call**: `subscribe_to_request_updates(request_id)`
- **File**: `common/redis_utils.py`
- **Actions**:
  - Spawns a background thread.
  - Subscribes to Redis channel: `request:{request_id}:status`.
  - **Note**: No events are published yet, but Coordinator is now listening.

### 1.4 Delegation Trigger
- **Call**: `asyncio.create_task(delegate_tasks_to_delegator(...))`
- **Logic**: This launches the delegation process in the background so the HTTP response to the user is fast.

### 1.5 Response to User
- **Return**: HTTP 200 JSON
  ```json
  {
    "status": "success",
    "request_id": "550e8400...",
    "tasks": [...],
    "message": "Request ... created..."
  }
  ```

---

## 🤝 Phase 2: Delegation Handshake (Coordinator → Delegator)

**Context**: Background task in `coordinator/app.py`.

### 2.1 Sending Tasks (Acceptance)
- **Action**: HTTP POST `http://localhost:8002/a2a/accept_tasks`
- **Payload**: `{ "request_id": "...", "tasks": [...] }`

#### [Delegator Side]
- **File**: `delegator/a2a_server.py`
- **Function**: `accept_tasks(request_id, tasks)`
- **Actions**:
  1. **Conversion**: Dicts converted back to `Task` objects.
  2. **State Init**: `create_delegator_state` called.
     - `self.state_store[request_id]` = `{ status: "idle", tasks: [...], active_tasks: {}, ... }`
  3. **Logging**: `log_state_message` records acceptance.
- **Return**: `{ "status": "accepted", "task_count": 3 }`

### 2.2 Triggering Execution (Delegation)
- **Action**: HTTP POST `http://localhost:8002/a2a/delegate_to_workers`
- **Payload**: `{ "request_id": "..." }`

#### [Delegator Side]
- **File**: `delegator/a2a_server.py`
- **Function**: `delegate_to_workers(request_id)`
- **Actions**:
  1. **Routing**: Iterates through tasks.
     - **Logic**: Round-Robin selection from `self.worker_urls` (default: `http://localhost:8003`).
  2. **State Update**:
     - `task.assigned_worker_url` set.
     - `state["active_tasks"][task_id]` = `{ status: "queued", worker_url: "..." }`
  3. **Redis Write**:
     - Key: `request:{id}:task:{task_id}`
     - Value: `{ status: "queued", worker_id: "..." }`
  4. **State Update**: `state["status"]` = `"delegating"`
  5. **Async Launch**: A background task `run_tasks()` is created to spawn `execute_task_on_worker` coroutines for all 3 tasks concurrently.
- **Return**: `{ "status": "delegated", "delegated_count": 3 }`

---

## ⚙️ Phase 3: Execution Loop (Delegator ↔ Worker)

**Context**: `Delegator` is running `execute_task_on_worker` for each task concurrently.

### 3.1 Pre-Execution Hook
- **File**: `delegator/a2a_server.py`
- **Function**: `execute_task_on_worker`
- **Actions**:
  1. **State Update**: `state["active_tasks"][task_id]["status"]` = `"executing"`
  2. **Redis Write**:
     - Key: `request:{id}:task:{task_id}` -> Updates status to `"executing"`.
  3. **Redis Pub/Sub Publish**:
     - Channel: `request:{request_id}:status`
     - Message: `{ "task_id": "...", "status": "executing", ... }`

### 3.2 Coordinator Monitoring (Async)
- **Coordinator** receives the Pub/Sub message.
- **Function**: `status_update_callback` in `coordinator/app.py`.
- **Output**: Logs `📊 Status Update: Task ... executing`.

### 3.3 Worker Invocation
- **Action**: HTTP POST `http://localhost:8003/a2a/execute_task`
- **Payload**: `{ "task": {...}, "request_id": "..." }`

#### [Worker Side]
- **File**: `worker/a2a_server.py`
- **Function**: `execute_task(task, request_id)`
- **Actions**:
  1. **State Init**: `create_worker_state` called.
  2. **Loop**: For step 1 to 3:
     - `state["current_step"]` updates.
     - `state["progress"]` updates (33%, 66%, 100%).
     - **LOGS**: `[WORKER] INFO: Task ... Executing step X/3`.
     - `await asyncio.sleep(1)` (Simulates work).
  3. **Completion**:
     - `state["status"]` = `"completed"`
- **Return**: `{ "status": "completed", "message": "Success" }`

### 3.4 Post-Execution Hook (Delegator)
- **Delegator** receives response from Worker.
- **Actions**:
  1. **State Update**: `state["active_tasks"][task_id]["status"]` = `"completed"`
  2. **Redis Write**:
     - Key: `request:{id}:task:{task_id}` -> Updates status to `"completed"`.
  3. **Redis Pub/Sub Publish**:
     - Channel: `request:{request_id}:status`
     - Message: `{ "task_id": "...", "status": "completed", ... }`

---

## 🏁 Phase 4: Final State

1. **Coordinator**:
   - Logs `📊 Status Update: Task ... completed`.
   - Has a complete record of events in its logs.
   - Initial `CoordinatorState` remains in memory (status "assigned").

2. **Delegator**:
   - `DelegatorState` shows all tasks in `"completed_tasks"` list.
   - `active_tasks` map shows status `"completed"` for all IDs.

3. **Worker**:
   - Local state persists in memory until restart.
   - Ready for next request.

4. **Redis**:
   - Hash keys `request:{id}:task:{task_id}` persist with final status `"completed"`.

---

## 🔎 Debugging Checklist

If the flow gets stuck, check these specific points:

1. **Request Stuck at "Planning" (Coordinator)**:
   - Check LLM Stub in `common/llm_stub.py`.
   - Verify `assign_tasks` returns valid JSON.

2. **Request Stuck at "Queued" (Delegator)**:
   - Check if `delegate_to_workers` was called.
   - Verify `run_tasks` background task started.
   - Check Redis: `HGETALL request:{id}:task:{task_id}`.

3. **Request Stuck at "Executing" (Worker)**:
   - Check Worker logs for "Executing step...".
   - If Worker logs "completed" but Delegator doesn't:
     - Check network (HTTP 500/timeout).
     - Check Delegator logs for "Task failed...".

4. **Updates Missing in Coordinator**:
   - Check Redis connection on both ends.
   - Verify Channel name matches: `request:{request_id}:status`.
