# CWD A2A MVP: Three-Agent Architecture with Agent-to-Agent Communication

A proof-of-concept implementation demonstrating a **Coordinator-Delegator-Worker (CWD)** architecture using the **Google Agent-to-Agent (A2A) Protocol** for inter-agent communication and **Redis** for shared state management between Coordinator and Delegator.

## Architecture Overview

### System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Client                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP POST /incident
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ Coordinator (C) @ 8001                                           │
│ ─────────────────────────────────────────────────────────────── │
│ • Receives incident text from user                              │
│ • Uses stub LLM to decompose into 2-3 tasks                     │
│ • Maintains local LangGraph state (planning context)            │
│ • Subscribes to Redis Pub/Sub for status updates                │
│ • Sends tasks to Delegator via A2A protocol                     │
└──────────┬───────────────────────────────────────────────────────┘
           │ A2A: accept_tasks()
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ Delegator (D) @ 8002                                             │
│ ─────────────────────────────────────────────────────────────── │
│ • Receives tasks from Coordinator (A2A)                         │
│ • Maintains local LangGraph state (routing, worker tracking)    │
│ • Distributes tasks to Workers via A2A protocol                 │
│ • Writes task status to Redis hash: incident:{id}:task:{id}    │
│ • Publishes status to Redis Pub/Sub: incident:{id}:status      │
└──────────┬───────────────────────────────────────────────────────┘
           │ A2A: execute_task()
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ Worker (W) @ 8003 (+ more on different ports)                    │
│ ─────────────────────────────────────────────────────────────── │
│ • Receives task from Delegator (A2A)                            │
│ • Maintains local LangGraph state (task execution lifecycle)    │
│ • Simulates task execution with 3 steps                         │
│ • Returns completion status to Delegator (A2A)                  │
│ • NO Redis access (architectural constraint)                    │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Incident Submission**: User sends incident text to Coordinator's `POST /incident`
2. **Task Planning**: Coordinator uses stub LLM to generate tasks (2-3 per incident)
3. **Task Delegation**: Coordinator sends tasks to Delegator via A2A `accept_tasks()` skill
4. **Worker Assignment**: Delegator assigns tasks to available Workers (round-robin)
5. **Task Execution**: Delegator calls Worker's A2A `execute_task()` skill for each task
6. **Status Tracking**: 
   - Worker executes task and returns status
   - Delegator writes status to Redis hash
   - Delegator publishes event to Redis Pub/Sub
   - Coordinator subscribes and logs updates to console

### State Management

#### Shared State (Coordinator ↔ Delegator via Redis)
- **Redis Hash**: `incident:{incident_id}:task:{task_id}` stores: `status`, `updated_at`, `worker_id`, `message`
- **Redis Pub/Sub**: Channel `incident:{incident_id}:status` for publishing status events
- **Coordinator** subscribes to updates; **Delegator** publishes updates

#### Local State (Per Agent)
- **Coordinator**: LangGraph `CoordinatorState` with incident context and tasks
- **Delegator**: LangGraph `DelegatorState` with active tasks, routing info, worker assignments
- **Worker**: LangGraph `WorkerState` with task execution progress and lifecycle

**Important**: Workers have NO Redis access—they communicate only via A2A protocol.

### A2A Protocol Usage

All inter-agent communication follows the **Agent-to-Agent (A2A) Protocol** via HTTP POST:

**A2A Skill Endpoints** (all POST requests with JSON payloads):

| Agent | Endpoint | Method | Skill Name | Input JSON | Output JSON |
|-------|----------|--------|-----------|-----------|------------|
| Coordinator | `/a2a/assign_incident_tasks` | POST | assign_incident_tasks | `{incident_text: string}` | `{incident_id, tasks[]}` |
| Delegator | `/a2a/accept_tasks` | POST | accept_tasks | `{incident_id, tasks[]}` | `{status, task_count}` |
| Delegator | `/a2a/delegate_to_workers` | POST | delegate_to_workers | `{incident_id}` | `{status, delegated_count}` |
| Worker | `/a2a/execute_task` | POST | execute_task | `{task, incident_id}` | `{status, message, timestamp}` |

**Example A2A Call** (Coordinator → Delegator):
```bash
curl -X POST http://localhost:8002/a2a/accept_tasks \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "550e8400-e29b-41d4-a716-446655440000",
    "tasks": [{"task_id": "...", "description": "..."}]
  }'
```

## Project Structure

```
cwd-a2a-mvp/
├── pyproject.toml              # Project metadata and dependencies
├── .env.example                # Environment configuration template
├── README.md                   # This file
├── common/
│   ├── __init__.py
│   ├── models.py               # Pydantic: Incident, Task, StatusUpdate
│   ├── llm_stub.py             # Stub LLM (easily swappable for OpenAI/Gemini)
│   ├── a2a_client.py           # A2A client factory helper
│   ├── langgraph_state.py      # TypedDict state definitions for all agents
│   └── redis_utils.py          # Redis client, pub/sub, hash operations (C & D only)
├── coordinator/
│   ├── __init__.py
│   ├── app.py                  # FastAPI/A2A server on port 8001
│   └── a2a_server.py           # Coordinator skills: assign_incident_tasks
├── delegator/
│   ├── __init__.py
│   ├── app.py                  # FastAPI/A2A server on port 8002
│   └── a2a_server.py           # Delegator skills: accept_tasks, delegate_to_workers
└── worker/
    ├── __init__.py
    ├── app.py                  # FastAPI/A2A server on port 8003
    └── a2a_server.py           # Worker skill: execute_task
```

## Installation & Setup

### Prerequisites

- Python 3.9+
- `uv` package manager ([install docs](https://docs.astral.sh/uv/))
- Redis server running locally or in Docker

### Step 1: Clone and Install

```bash
# Navigate to project directory
cd /workspaces/cwd-langgraph-mvp/cwd-a2a-mvp

# Create virtual environment and install dependencies using uv
uv sync
```

### Step 2: Set Up Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Default values are already set for local development:
# REDIS_URL=redis://localhost:6379/0
# COORDINATOR_URL=http://localhost:8001
# DELEGATOR_URL=http://localhost:8002
# WORKER_URL=http://localhost:8003
# LLM_PROVIDER=stub
```

### Step 3: Start Redis

```bash
# Option A: Docker (recommended)
docker run -d -p 6379:6379 --name redis-cwd redis

# Option B: Local Redis server (if installed)
redis-server
```

### Step 4: Start Agents (in separate terminals)

Each agent runs standalone with `uv run`:

**Terminal 1 - Coordinator (port 8001)**:
```bash
cd /workspaces/cwd-langgraph-mvp/cwd-a2a-mvp
uv run coordinator/app.py
```

**Terminal 2 - Delegator (port 8002)**:
```bash
cd /workspaces/cwd-langgraph-mvp/cwd-a2a-mvp
uv run delegator/app.py
```

**Terminal 3 - Worker (port 8003)**:
```bash
cd /workspaces/cwd-langgraph-mvp/cwd-a2a-mvp
uv run worker/app.py
```

All three agents should now be running. You'll see startup logs like:
```
Coordinator agent starting on port 8001
Delegator agent starting on port 8002
Worker agent starting on port 8003
```

## Usage Demo

### Submit an Incident

In a new terminal, submit an incident to the Coordinator:

```bash
curl -X POST http://localhost:8001/incident \
  -H "Content-Type: application/json" \
  -d '{"incident_text": "Service X is experiencing errors and timeouts"}'
```

**Expected Response**:
```json
{
  "status": "success",
  "incident_id": "550e8400-e29b-41d4-a716-446655440000",
  "tasks": [
    {
      "task_id": "...",
      "description": "Diagnose service status and root cause",
      "priority": "high"
    },
    {
      "task_id": "...",
      "description": "Apply fix or mitigation",
      "priority": "high"
    },
    {
      "task_id": "...",
      "description": "Verify recovery and health check",
      "priority": "normal"
    }
  ],
  "message": "Incident 550e8400-e29b-41d4-a716-446655440000 created with 3 tasks. Monitoring status updates..."
}
```

### Observe Progress

1. **Coordinator Console**: Watch for Redis Pub/Sub status updates
   ```
   📊 Status Update: [2024-01-15T10:30:45] Task ...: started
   📊 Status Update: [2024-01-15T10:30:46] Task ...: in_progress (33%)
   ...
   ```

2. **Delegator Console**: Watch for task delegation and status writes
   ```
   [DELEGATOR] INFO: Delegating 3 tasks to 1 worker(s)
   [DELEGATOR] INFO: Executing task ... on http://localhost:8003 (attempt 1)
   ...
   ```

3. **Worker Console**: Watch for task execution logs
   ```
   [WORKER] INFO: execute_task called: task_id=..., description=...
   [WORKER] INFO: Task ...: Executing step 1/3
   [WORKER] INFO: Task ...: Executing step 2/3
   [WORKER] INFO: Task ...: Executing step 3/3
   [WORKER] INFO: Task ... completed successfully
   ```

### Check Health

```bash
# Check Coordinator health
curl http://localhost:8001/health | jq .

# Check Delegator health
curl http://localhost:8002/health | jq .

# Check Worker health
curl http://localhost:8003/health | jq .
```

### Run Integration Test

With all three agents running, execute the integration test in a fourth terminal:

```bash
cd /workspaces/cwd-langgraph-mvp/cwd-a2a-mvp
python test_integration.py
```

This tests:
1. Agent health checks
2. Incident creation via HTTP
3. A2A skill communication (Delegator accept_tasks)
4. Task delegation and execution
5. Complete workflow end-to-end

## Extending the MVP

### Adding More Workers

The architecture supports multiple workers. To add a second worker:

1. **Edit Delegator Configuration** (`delegator/a2a_server.py`):
   ```python
   self.worker_urls = [
       "http://localhost:8003",  # Worker 1
       "http://localhost:8004",  # Worker 2
   ]
   ```

2. **Start Worker 2** on port 8004:
   ```bash
   # Update WORKER_URL in .env or pass via env var
   WORKER_URL=http://localhost:8004 uv run worker/app.py
   ```

3. **Delegator now uses round-robin** to assign tasks across all workers.

### Swapping LLM Providers

The stub LLM is easily replaceable. To add OpenAI support:

1. **Edit `common/llm_stub.py`**:
   ```python
   def incident_to_tasks(incident_text: str) -> list[Task]:
       provider = get_llm_provider()
       
       if provider == "openai":
           return openai_incident_to_tasks(incident_text)
       # ... rest of logic
   ```

2. **Implement `openai_incident_to_tasks()`** with OpenAI SDK calls.

3. **Set environment variable**:
   ```bash
   LLM_PROVIDER=openai OPENAI_API_KEY=sk-... uv run coordinator/app.py
   ```

### Adding Custom Task Logic

To implement real task execution instead of simulation:

1. **Edit `worker/a2a_server.py`** `execute_task()` method:
   ```python
   # Replace simulated sleep/steps with real logic
   if "diagnose" in task_description.lower():
       result = await perform_health_check()
   elif "fix" in task_description.lower():
       result = await apply_mitigation()
   # ... etc
   ```

## Code Architecture & Key Patterns

### A2A Protocol Integration

The A2A SDK is used to:
1. **Define skills** as FastAPI decorators (`@app.a2a.skill()`)
2. **Create clients** via `a2a_client.py` factory functions
3. **Call remote skills** with `client.call_skill(skill_name, **args)`

Example:
```python
# Server: expose skill
@app.a2a.skill(name="accept_tasks")
async def a2a_accept_tasks(incident_id: str, tasks: list[dict]) -> dict:
    return delegator_skills.accept_tasks(incident_id, tasks)

# Client: call skill
delegator_client = create_delegator_client()
result = await delegator_client.call_skill(
    skill_name="accept_tasks",
    incident_id=incident_id,
    tasks=task_dicts
)
```

### LangGraph State Pattern

Each agent maintains a local TypedDict for state management:

```python
# Define state schema
class CoordinatorState(TypedDict):
    incident_id: str
    tasks: list[Task]
    status: str
    messages: list[dict]

# Initialize state
state = create_coordinator_state(incident_id, incident_text)

# Update state
state["status"] = "assigned"
log_state_message(state, "Tasks assigned")
```

### Redis Shared State

Only Coordinator and Delegator use Redis:

```python
# Delegator writes task status
from common.redis_utils import write_task_status, publish_status_event

write_task_status(incident_id, task_id, {
    "status": "in_progress",
    "worker_id": "http://localhost:8003",
    "progress": 50
})

# Publish to Pub/Sub
publish_status_event(incident_id, {
    "task_id": task_id,
    "status": "in_progress",
    "progress": 50
})

# Coordinator subscribes
from common.redis_utils import subscribe_to_status_events
subscribe_to_status_events(incident_id, callback_fn)
```

**Workers do not import `redis_utils.py`** — architectural constraint maintained.

### Error Handling & Retry Logic

Delegator implements simple retry logic:

```python
# In delegator/a2a_server.py
async def execute_task_on_worker(self, incident_id, task, worker_url, retry_count=1):
    attempt = 0
    while attempt <= retry_count:
        try:
            result = await worker_client.call_skill("execute_task", task=task)
            # Mark completed
            return True
        except Exception as e:
            attempt += 1
            if attempt > retry_count:
                # Mark failed in Redis, publish failure event
                return False
```

## Logging & Monitoring

### Structured Logging

All agents log with consistent format:
```
[TIMESTAMP] [AGENT_NAME] [LOG_LEVEL]: message
```

Example output:
```
2024-01-15T10:30:45 [COORDINATOR] INFO: New incident received: 550e8400... - Service X is erroring...
2024-01-15T10:30:46 [DELEGATOR] INFO: accept_tasks called: incident_id=550e8400..., task_count=3
2024-01-15T10:30:47 [WORKER] INFO: Task execution started
```

### Health Endpoints

All agents expose `/health`:
```bash
curl http://localhost:8001/health
# {
#   "status": "healthy",
#   "agent": "coordinator",
#   "port": 8001,
#   "redis": true
# }
```

### Redis Pub/Sub Monitoring

Monitor Redis messages in real-time:
```bash
# In another terminal, subscribe to incident status
redis-cli
> SUBSCRIBE "incident:*:status"
```

## Development Notes

### Testing Locally

For manual testing without full integration:

```python
# Test stub LLM directly
from common.llm_stub import incident_to_tasks
tasks = incident_to_tasks("Service is down")
print(tasks)

# Test Redis utils
from common.redis_utils import health_check
assert health_check()

# Test Coordinator skill
from coordinator.a2a_server import CoordinatorSkillsServer
coordinator = CoordinatorSkillsServer()
result = coordinator.assign_incident_tasks("Test incident", "test-id")
print(result)
```

### Adding Logging Levels

Set `LOG_LEVEL` environment variable:
```bash
LOG_LEVEL=DEBUG uv run coordinator/app.py
```

### Debugging A2A Communication

Add debug logs to see A2A protocol traffic:
```python
# In a2a_client.py or a2a_server.py
import logging
logging.getLogger("a2a").setLevel(logging.DEBUG)
```

## Production Considerations

1. **Persistence**: Replace in-memory state stores with persistent databases (PostgreSQL, DynamoDB)
2. **Scalability**: Use task queues (Celery, RabbitMQ) instead of direct A2A calls
3. **Observability**: Integrate OpenTelemetry for distributed tracing
4. **Security**: Add authentication/authorization to A2A skills
5. **Load Balancing**: Run multiple Delegator/Worker instances with load balancer
6. **Circuit Breaking**: Add resilience patterns to handle cascading failures

## Troubleshooting

### Agents Won't Start

**Error**: `ModuleNotFoundError: No module named 'a2a_sdk'`
- **Solution**: Run `uv sync` to install dependencies

**Error**: `Connection refused` on port 8001/8002/8003
- **Solution**: Check if agent is already running on that port; kill and restart

### Redis Connection Failed

**Error**: `ConnectionError: Error 111 connecting to localhost:6379`
- **Solution**: 
  - Start Redis: `docker run -p 6379:6379 redis`
  - Or verify Redis is running: `redis-cli ping` (should return PONG)

### A2A Skills Not Responding

**Error**: A2A client call times out or returns 404
- **Solution**: Verify A2A SDK is installed and skills are properly decorated

### No Status Updates in Coordinator

**Error**: Coordinator logs no Pub/Sub messages even after tasks complete
- **Solution**:
  - Verify Redis is running
  - Check Delegator is actually calling `publish_status_event()`
  - Monitor Redis directly: `redis-cli SUBSCRIBE "incident:*:status"`

## References

- [Google Agent-to-Agent (A2A) Protocol](https://ai.google.dev/docs/agents/tools)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Redis Documentation](https://redis.io/docs/)
- [uv Package Manager](https://docs.astral.sh/uv/)

## License

MIT
