import time
import uuid
from datetime import datetime, timezone, timedelta
import requests

BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SEC = 2

AGENT_ID = f"worker-{uuid.uuid4().hex[:8]}"
LEASE_SECONDS = 60


def utc_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def lease_until_ts() -> float:
    return (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).timestamp()


def get_state() -> dict:
    r = requests.get(f"{BASE_URL}/state", timeout=10)
    r.raise_for_status()
    return r.json()


def patch_state(patch: dict) -> dict:
    r = requests.post(f"{BASE_URL}/patch", json={"patch": patch}, timeout=10)
    r.raise_for_status()
    return r.json()


def add_event(event: dict) -> dict:
    r = requests.post(f"{BASE_URL}/event", json={"event": event}, timeout=10)
    r.raise_for_status()
    return r.json()


def is_claimable(task: dict, now: float) -> bool:
    if task.get("status") != "pending":
        return False
    owner = task.get("owner")
    lease_until = task.get("lease_until")
    if owner in (None, "", "null"):
        return True
    if lease_until is None:
        return True
    try:
        return float(lease_until) < now
    except Exception:
        return True


def claim_one_task(state: dict) -> dict | None:
    tasks = state.get("tasks", [])
    now = utc_ts()

    for i, t in enumerate(tasks):
        if t.get("type") == "work" and is_claimable(t, now):
            tasks[i]["owner"] = AGENT_ID
            tasks[i]["claimed_at"] = now
            tasks[i]["lease_until"] = lease_until_ts()
            tasks[i]["status"] = "in_progress"

            patch_state({"tasks": tasks})

            add_event({
                "type": "worker_claimed",
                "agent_id": AGENT_ID,
                "ts": now,
                "task_id": t.get("task_id"),
            })

            return tasks[i]

    return None


def complete_task(state: dict, task_id: str, result: dict):
    tasks = state.get("tasks", [])
    now = utc_ts()

    for i, t in enumerate(tasks):
        if t.get("task_id") == task_id:
            tasks[i]["status"] = "done"
            tasks[i]["lease_until"] = None
            tasks[i]["result"] = result
            patch_state({"tasks": tasks})

            add_event({
                "type": "worker_done",
                "agent_id": AGENT_ID,
                "ts": now,
                "task_id": task_id,
            })
            return


def worker_loop():
    print(f"[worker] started, agent_id={AGENT_ID}", flush=True)

    while True:
        try:
            state = get_state()
            task = claim_one_task(state)

            if not task:
                print("[worker] No claimable tasks. Waiting...", flush=True)
                time.sleep(POLL_INTERVAL_SEC)
                continue

            tid = task.get("task_id")
            print(f"[worker] Working on {tid} ...", flush=True)

            # FAKE EXECUTION (2 секунды работы)
            time.sleep(2)

            # Простейший результат-заглушка
            result = {
                "ok": True,
                "note": "Stub result: worker executed task (no AI yet).",
                "task_id": tid,
                "finished_at": utc_ts(),
            }

            # перечитываем state перед записью результата (на всякий)
            state2 = get_state()
            complete_task(state2, tid, result)

        except Exception as e:
            print(f"[worker] error: {e}", flush=True)
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        worker_loop()
    except KeyboardInterrupt:
        print("[worker] stopped", flush=True)
