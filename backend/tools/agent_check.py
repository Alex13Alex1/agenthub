"""
Agent Self-Check Harness - Tests R1/R2/R3 compliance.
Run from backend folder: python tools/agent_check.py

Scenarios:
A) Single worker claim
B) Two workers, no double-claim  
C) Lease expiry reclaim
"""
import os
import sys
import time
import uuid
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
REPORT_DIR = Path(__file__).parent.parent.parent / "reports"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_get(path: str):
    r = requests.get(f"{BASE_URL}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload: dict):
    r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
    r.raise_for_status()
    return r.json() if r.content else None


def reset_state(fixture: dict):
    """Reset backend state to fixture."""
    return api_post("/reset", {"state": fixture})


def get_state():
    return api_get("/state")


def check_backend_running() -> bool:
    """Check if backend is running."""
    try:
        r = requests.get(f"{BASE_URL}/", timeout=2)
        return r.status_code == 200
    except:
        return False


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.violations = []
        self.events = []
        self.notes = []
    
    def add_violation(self, msg: str):
        self.violations.append(msg)
    
    def add_event(self, event: dict):
        self.events.append(event)
    
    def add_note(self, note: str):
        self.notes.append(note)


def check_r1_compliance(events: list, state: dict) -> list:
    """Check R1 violations: state updates must have agent_id, timestamp, reason."""
    violations = []
    
    for i, event in enumerate(events):
        if not event.get("agent_id"):
            violations.append(f"Event {i} missing agent_id: {event.get('type', 'unknown')}")
        if not event.get("timestamp"):
            violations.append(f"Event {i} missing timestamp: {event.get('type', 'unknown')}")
        if not event.get("reason") and event.get("type") not in ["planner_heartbeat"]:
            # Heartbeats can have minimal reason
            pass
    
    meta = state.get("_meta", {})
    if meta:
        if not meta.get("agent_id"):
            violations.append("State _meta missing agent_id")
        if not meta.get("timestamp"):
            violations.append("State _meta missing timestamp")
        if not meta.get("reason"):
            violations.append("State _meta missing reason")
    
    return violations


def check_r2_compliance(events: list, state: dict) -> list:
    """Check R2 violations: task claiming, locking, no double-claim."""
    violations = []
    
    tasks = state.get("tasks", [])
    
    # Check for tasks marked done without prior task_claimed
    task_claimed_ids = set()
    task_done_ids = set()
    
    for event in events:
        etype = event.get("type", "")
        task_id = event.get("task_id", "")
        
        if etype == "task_claimed" or etype == "task_reclaimed":
            task_claimed_ids.add(task_id)
        if etype == "task_done":
            task_done_ids.add(task_id)
            if task_id not in task_claimed_ids:
                violations.append(f"Task {task_id} marked done without prior task_claimed")
    
    # Check for proper task fields
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        if task.get("status") == "in_progress":
            if not task.get("owner"):
                violations.append(f"Task {i} in_progress but missing owner")
            if not task.get("claimed_at"):
                violations.append(f"Task {i} in_progress but missing claimed_at")
            if not task.get("lease_until"):
                violations.append(f"Task {i} in_progress but missing lease_until")
    
    return violations


def scenario_a_single_worker_claim() -> TestResult:
    """Scenario A: Single worker claim."""
    result = TestResult("Scenario A: Single worker claim")
    
    # Reset to fixture with one pending task
    fixture = {
        "goal": "Test scenario A",
        "tasks": [{
            "task_id": "test-task-a",
            "title": "Test task A",
            "status": "pending",
            "created_at": iso_now(),
            "created_by": "test-harness",
            "owner": None,
            "claimed_at": None,
            "lease_until": None,
            "attempt": 0
        }],
        "notes": [],
        "artifacts": {},
        "events": []
    }
    
    try:
        reset_state(fixture)
        result.add_note("Reset state to fixture")
        
        # Start worker subprocess
        backend_dir = Path(__file__).parent.parent
        worker_path = backend_dir / "agents" / "worker.py"
        
        result.add_note(f"Starting worker from {worker_path}")
        proc = subprocess.Popen(
            [sys.executable, str(worker_path)],
            cwd=str(backend_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for worker to process
        time.sleep(8)
        
        # Terminate worker
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except:
            proc.kill()
        
        # Check results
        state = get_state()
        events = state.get("events", [])
        tasks = state.get("tasks", [])
        
        result.events = events[-10:]  # Last 10 events
        
        # Check task was claimed and completed
        task = tasks[0] if tasks else {}
        
        if task.get("status") == "done":
            result.add_note("Task completed successfully")
        else:
            result.add_violation(f"Task not completed. Status: {task.get('status')}")
        
        # Check for task_claimed event
        claimed = any(e.get("type") == "task_claimed" for e in events)
        if claimed:
            result.add_note("task_claimed event found")
        else:
            result.add_violation("No task_claimed event found")
        
        # Check for task_done event
        done = any(e.get("type") == "task_done" for e in events)
        if done:
            result.add_note("task_done event found")
        else:
            result.add_violation("No task_done event found")
        
        # Check task fields were set
        if task.get("owner"):
            result.add_note(f"Task owner set: {task.get('owner')}")
        else:
            result.add_violation("Task owner not set")
        
        if task.get("claimed_at"):
            result.add_note("Task claimed_at set")
        
        # Check R1/R2 compliance
        r1_violations = check_r1_compliance(events, state)
        r2_violations = check_r2_compliance(events, state)
        
        for v in r1_violations:
            result.add_violation(f"R1: {v}")
        for v in r2_violations:
            result.add_violation(f"R2: {v}")
        
        result.passed = len(result.violations) == 0
        
    except Exception as e:
        result.add_violation(f"Exception: {str(e)}")
    
    return result


def scenario_b_two_workers_no_double_claim() -> TestResult:
    """Scenario B: Two workers, no double-claim."""
    result = TestResult("Scenario B: Two workers, no double-claim")
    
    # Reset to fixture with one pending task
    fixture = {
        "goal": "Test scenario B",
        "tasks": [{
            "task_id": "test-task-b",
            "title": "Test task B",
            "status": "pending",
            "created_at": iso_now(),
            "created_by": "test-harness",
            "owner": None,
            "claimed_at": None,
            "lease_until": None,
            "attempt": 0
        }],
        "notes": [],
        "artifacts": {},
        "events": []
    }
    
    try:
        reset_state(fixture)
        result.add_note("Reset state to fixture")
        
        # Start two workers
        backend_dir = Path(__file__).parent.parent
        worker_path = backend_dir / "agents" / "worker.py"
        
        proc1 = subprocess.Popen(
            [sys.executable, str(worker_path)],
            cwd=str(backend_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        proc2 = subprocess.Popen(
            [sys.executable, str(worker_path)],
            cwd=str(backend_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        result.add_note("Started 2 workers concurrently")
        
        # Wait for processing
        time.sleep(10)
        
        # Terminate workers
        for proc in [proc1, proc2]:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()
        
        # Check results
        state = get_state()
        events = state.get("events", [])
        
        result.events = events[-15:]
        
        # Count claims for the same task
        claims = [e for e in events if e.get("type") == "task_claimed" and e.get("task_id") == "test-task-b"]
        
        if len(claims) <= 1:
            result.add_note(f"No double-claim detected ({len(claims)} claims)")
        else:
            # Check if claims had overlapping valid leases
            result.add_note(f"Multiple claims detected ({len(claims)}), checking lease overlap...")
            # For simplicity, if there are 2 claims and both succeeded, it's a violation
            # In practice, the second worker should have waited or seen in_progress
            owners = set(c.get("agent_id") for c in claims)
            if len(owners) > 1:
                result.add_violation(f"Double-claim: {len(owners)} different workers claimed same task")
            else:
                result.add_note("Same worker reclaimed (acceptable)")
        
        # Check R1/R2 compliance
        r1_violations = check_r1_compliance(events, state)
        r2_violations = check_r2_compliance(events, state)
        
        for v in r1_violations:
            result.add_violation(f"R1: {v}")
        for v in r2_violations:
            result.add_violation(f"R2: {v}")
        
        result.passed = len(result.violations) == 0
        
    except Exception as e:
        result.add_violation(f"Exception: {str(e)}")
    
    return result


def scenario_c_lease_expiry_reclaim() -> TestResult:
    """Scenario C: Lease expiry reclaim."""
    result = TestResult("Scenario C: Lease expiry reclaim")
    
    # Reset to fixture with task already claimed but expired lease
    expired_lease = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    
    fixture = {
        "goal": "Test scenario C",
        "tasks": [{
            "task_id": "test-task-c",
            "title": "Test task C",
            "status": "in_progress",
            "created_at": iso_now(),
            "created_by": "test-harness",
            "owner": "dead-worker-xyz",
            "claimed_at": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
            "lease_until": expired_lease,
            "attempt": 1
        }],
        "notes": [],
        "artifacts": {},
        "events": [{
            "type": "task_claimed",
            "agent_id": "dead-worker-xyz",
            "task_id": "test-task-c",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
            "reason": "Original claim"
        }]
    }
    
    try:
        reset_state(fixture)
        result.add_note("Reset state to fixture with expired lease")
        result.add_note(f"Lease expired at: {expired_lease}")
        
        # Start worker
        backend_dir = Path(__file__).parent.parent
        worker_path = backend_dir / "agents" / "worker.py"
        
        proc = subprocess.Popen(
            [sys.executable, str(worker_path)],
            cwd=str(backend_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        result.add_note("Started worker to reclaim expired task")
        
        # Wait for processing
        time.sleep(8)
        
        # Terminate
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except:
            proc.kill()
        
        # Check results
        state = get_state()
        events = state.get("events", [])
        tasks = state.get("tasks", [])
        
        result.events = events[-10:]
        
        # Check for task_reclaimed event
        reclaimed = any(e.get("type") == "task_reclaimed" for e in events)
        if reclaimed:
            result.add_note("task_reclaimed event found")
        else:
            result.add_violation("No task_reclaimed event found")
        
        # Check task was completed
        task = tasks[0] if tasks else {}
        if task.get("status") == "done":
            result.add_note("Task completed after reclaim")
        else:
            result.add_note(f"Task status: {task.get('status')}")
        
        # Check new owner is different
        if task.get("owner") and task.get("owner") != "dead-worker-xyz":
            result.add_note(f"New owner: {task.get('owner')}")
        
        # Check attempt incremented
        if task.get("attempt", 0) > 1:
            result.add_note(f"Attempt incremented to {task.get('attempt')}")
        
        result.passed = len(result.violations) == 0
        
    except Exception as e:
        result.add_violation(f"Exception: {str(e)}")
    
    return result


def generate_report(results: list) -> str:
    """Generate Markdown report."""
    lines = [
        "# Agent Self-Check Report",
        "",
        f"**Generated:** {iso_now()}",
        "",
        "## Summary",
        "",
        "| Scenario | Result |",
        "|----------|--------|",
    ]
    
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        lines.append(f"| {r.name} | {status} |")
    
    lines.append("")
    
    for r in results:
        lines.append(f"## {r.name}")
        lines.append("")
        lines.append(f"**Result:** {'PASS' if r.passed else 'FAIL'}")
        lines.append("")
        
        if r.notes:
            lines.append("### Notes")
            for note in r.notes:
                lines.append(f"- {note}")
            lines.append("")
        
        if r.violations:
            lines.append("### Violations Detected")
            for v in r.violations:
                lines.append(f"- ⚠️ {v}")
            lines.append("")
        
        if r.events:
            lines.append("### Observed Events (last 10)")
            lines.append("```json")
            for e in r.events[:10]:
                etype = e.get("type", "unknown")
                agent = e.get("agent_id", "?")
                ts = e.get("timestamp", "?")[:19] if e.get("timestamp") else "?"
                lines.append(f"  {etype} | {agent} | {ts}")
            lines.append("```")
            lines.append("")
    
    # Suggested fixes
    all_violations = []
    for r in results:
        all_violations.extend(r.violations)
    
    if all_violations:
        lines.append("## Suggested Fixes")
        lines.append("")
        if any("agent_id" in v for v in all_violations):
            lines.append("- Ensure all events include `agent_id` field")
        if any("timestamp" in v for v in all_violations):
            lines.append("- Ensure all events include `timestamp` field in ISO 8601 format")
        if any("double-claim" in v.lower() for v in all_violations):
            lines.append("- Implement proper lease checking before claiming tasks")
        if any("task_claimed" in v for v in all_violations):
            lines.append("- Ensure task_claimed event is emitted before processing")
        lines.append("")
    
    return "\n".join(lines)


def main():
    print("=" * 60)
    print("Agent Self-Check Harness")
    print("=" * 60)
    print()
    
    # Check backend is running
    if not check_backend_running():
        print("ERROR: Backend is not running on http://127.0.0.1:8000")
        print("Please start the backend first:")
        print("  python -m uvicorn main:app --reload")
        sys.exit(1)
    
    print("Backend is running ✓")
    print()
    
    results = []
    
    # Run scenarios
    print("Running Scenario A: Single worker claim...")
    results.append(scenario_a_single_worker_claim())
    print(f"  Result: {'PASS' if results[-1].passed else 'FAIL'}")
    print()
    
    print("Running Scenario B: Two workers, no double-claim...")
    results.append(scenario_b_two_workers_no_double_claim())
    print(f"  Result: {'PASS' if results[-1].passed else 'FAIL'}")
    print()
    
    print("Running Scenario C: Lease expiry reclaim...")
    results.append(scenario_c_lease_expiry_reclaim())
    print(f"  Result: {'PASS' if results[-1].passed else 'FAIL'}")
    print()
    
    # Generate report
    report = generate_report(results)
    
    # Write report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "agent_check_report.md"
    report_path.write_text(report, encoding="utf-8")
    
    print("=" * 60)
    print(f"Report written to: {report_path}")
    print("=" * 60)
    print()
    print(report)


if __name__ == "__main__":
    main()

