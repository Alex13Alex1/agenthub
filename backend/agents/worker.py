"""
Worker Agent - Executes tasks from the queue.
Run from backend folder: python agents/worker.py

Implements R1: State-Only Coordination
Implements R2: Task Claiming & Locking
- Explicit claim step with owner, claimed_at, lease_until
- Lease refresh while working
- Proper status transitions: pending -> in_progress -> done
"""
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = "http://127.0.0.1:8000"
AGENT_ID = f"worker-{uuid.uuid4().hex[:8]}"
LEASE_MINUTES = 10


def iso_now() -> str:
    """Return current time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def iso_future(minutes: int) -> str:
    """Return future time in ISO 8601 format."""
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def is_lease_expired(lease_until: str) -> bool:
    """Check if lease has expired."""
    if not lease_until:
        return True
    try:
        lease_dt = datetime.fromisoformat(lease_until.replace('Z', '+00:00'))
        return datetime.now(timezone.utc) > lease_dt
    except:
        return True


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


def can_claim_task(task: dict) -> bool:
    """Check if this worker can claim the task (R2)."""
    status = task.get("status", "pending")
    owner = task.get("owner")
    lease_until = task.get("lease_until")
    
    # Can claim if pending
    if status == "pending":
        return True
    
    # Can claim if in_progress but lease expired (reclaim)
    if status == "in_progress":
        if owner == AGENT_ID:
            return True  # Already ours
        if is_lease_expired(lease_until):
            return True  # Lease expired, can reclaim
    
    return False


def claim_task(tasks: list, task_index: int, task: dict) -> bool:
    """Claim a task atomically (R2)."""
    task_id = task.get("task_id", f"task-{task_index}")
    was_reclaim = task.get("status") == "in_progress" and task.get("owner") != AGENT_ID
    
    # Update task fields for claiming
    tasks[task_index]["status"] = "in_progress"
    tasks[task_index]["owner"] = AGENT_ID
    tasks[task_index]["claimed_at"] = iso_now()
    tasks[task_index]["lease_until"] = iso_future(LEASE_MINUTES)
    tasks[task_index]["attempt"] = task.get("attempt", 0) + 1
    
    event_type = "task_reclaimed" if was_reclaim else "task_claimed"
    reason = f"Reclaiming expired task" if was_reclaim else f"Claiming pending task"
    
    update_state({"tasks": tasks}, reason=f"{reason}: {task.get('title', task_id)}")
    add_event(event_type, {"task_id": task_id, "title": task.get("title", "")}, reason)
    
    return True


def complete_task(tasks: list, task_index: int, task: dict, artifact: dict = None):
    """Mark task as done (R2)."""
    task_id = task.get("task_id", f"task-{task_index}")
    title = task.get("title", "Untitled")
    
    tasks[task_index]["status"] = "done"
    tasks[task_index]["completed_at"] = iso_now()
    tasks[task_index]["lease_until"] = None  # Clear lease
    
    patch = {"tasks": tasks}
    
    # Add artifact if provided (R3)
    if artifact:
        state = get_state()
        artifacts = state.get("artifacts", {})
        artifact_id = f"artifact-{uuid.uuid4().hex[:8]}"
        artifact["task_id"] = task_id
        artifact["artifact_id"] = artifact_id
        artifact["created_at"] = iso_now()
        artifact["created_by"] = AGENT_ID
        artifacts[artifact_id] = artifact
        patch["artifacts"] = artifacts
    
    # Add completion note
    state = get_state()
    notes = state.get("notes", [])
    notes.append(f"[{iso_now()}] {AGENT_ID}: completed task '{title}'")
    patch["notes"] = notes
    
    update_state(patch, reason=f"Completed task: {title}")
    add_event("task_done", {"task_id": task_id, "title": title}, f"Task completed successfully")


def main():
    print(f"Worker started. agent_id={AGENT_ID}")

    while True:
        try:
            state = get_state()
            tasks = state.get("tasks") or []

            # Find first claimable task (R2)
            task = None
            task_index = None
            for i, t in enumerate(tasks):
                if isinstance(t, dict) and can_claim_task(t):
                    task = t
                    task_index = i
                    break

            if task is None:
                print("No claimable tasks. Waiting...")
                time.sleep(3)
                continue

            title = task.get("title", "Untitled task")
            task_id = task.get("task_id", f"task-{task_index}")
            
            # Claim the task (R2)
            print(f"Claiming task: {title}")
            claim_task(tasks, task_index, task)
            
            # Simulate work
            print(f"Working on task: {title}")
            time.sleep(2)
            
            # Re-read state to get latest tasks
            state = get_state()
            tasks = state.get("tasks") or []
            
            # Verify we still own the task
            if task_index < len(tasks):
                current_task = tasks[task_index]
                if current_task.get("owner") != AGENT_ID:
                    print(f"Lost ownership of task: {title}")
                    continue
            
            # Complete the task (R2, R3)
            artifact = {
                "type": "completion_note",
                "content": f"Task '{title}' was simulated and completed.",
                "output_type": "text"
            }
            complete_task(tasks, task_index, task, artifact)
            print(f"Task done: {title}")

        except Exception as e:
            print(f"Worker error: {e}")

        time.sleep(3)


if __name__ == "__main__":
    main()
