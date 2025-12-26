"""
Planner Agent - Creates initial task plan and sends heartbeats.
Run from backend folder: python agents/planner.py

Implements R1: State-Only Coordination
- All writes include agent_id, timestamp, reason
- Communication only via HTTP API
"""
import time
import uuid
import requests
from datetime import datetime, timezone

BASE_URL = "http://127.0.0.1:8000"
AGENT_ID = f"planner-{uuid.uuid4().hex[:8]}"


def iso_now() -> str:
    """Return current time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def api_get(path: str):
    """GET request with timeout and error handling."""
    r = requests.get(f"{BASE_URL}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload: dict):
    """POST request with timeout and error handling."""
    r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else None


def get_state():
    """GET /state"""
    return api_get("/state")


def update_state(patch: dict, reason: str):
    """POST /state/update with R1-compliant metadata."""
    patch["_meta"] = {
        "agent_id": AGENT_ID,
        "timestamp": iso_now(),
        "reason": reason
    }
    return api_post("/state/update", {"patch": patch})


def add_event(event_type: str, data: dict = None, reason: str = ""):
    """POST /events with R1-compliant metadata."""
    event = {
        "type": event_type,
        "agent_id": AGENT_ID,
        "timestamp": iso_now(),
        "reason": reason,
        **(data or {})
    }
    return api_post("/events", {"event": event})


def main():
    print(f"Planner started. agent_id={AGENT_ID}")

    # 1) Read initial state
    try:
        state = get_state()
        print(f"Current goal: {state.get('goal')}")
    except Exception as e:
        print(f"Error reading initial state: {e}")
        state = {}

    # 2) If no tasks, create initial plan
    tasks = state.get("tasks") or []
    if not tasks:
        try:
            new_tasks = [
                {
                    "task_id": f"task-{uuid.uuid4().hex[:8]}",
                    "title": "Create shared memory (state.json via API)",
                    "status": "pending",
                    "created_at": iso_now(),
                    "created_by": AGENT_ID,
                    "owner": None,
                    "claimed_at": None,
                    "lease_until": None,
                    "attempt": 0
                },
                {
                    "task_id": f"task-{uuid.uuid4().hex[:8]}",
                    "title": "Teach agents to read state",
                    "status": "pending",
                    "created_at": iso_now(),
                    "created_by": AGENT_ID,
                    "owner": None,
                    "claimed_at": None,
                    "lease_until": None,
                    "attempt": 0
                },
                {
                    "task_id": f"task-{uuid.uuid4().hex[:8]}",
                    "title": "Teach agents to update state",
                    "status": "pending",
                    "created_at": iso_now(),
                    "created_by": AGENT_ID,
                    "owner": None,
                    "claimed_at": None,
                    "lease_until": None,
                    "attempt": 0
                },
            ]
            update_state({
                "goal": "Build universal agent system with shared state",
                "tasks": new_tasks,
                "notes": [f"[{iso_now()}] {AGENT_ID}: created initial task plan"]
            }, reason="Initialize tasks - no existing tasks found")
            
            add_event("planner_initialized", {}, "Created initial task plan")
            print("Initialized tasks and wrote to shared state.")
        except Exception as e:
            print(f"Error initializing tasks: {e}")
    else:
        print(f"Tasks already exist ({len(tasks)} tasks), nothing to init.")

    # 3) Main loop: heartbeat every 5 seconds
    while True:
        try:
            state = get_state()
            tasks = state.get("tasks") or []
            pending = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "pending")
            in_progress = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "in_progress")
            done = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "done")
            
            add_event("planner_heartbeat", {
                "task_count": len(tasks),
                "pending": pending,
                "in_progress": in_progress,
                "done": done
            }, "Periodic heartbeat")
            
            print(f"Heartbeat. total={len(tasks)} pending={pending} in_progress={in_progress} done={done}")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)


if __name__ == "__main__":
    main()
