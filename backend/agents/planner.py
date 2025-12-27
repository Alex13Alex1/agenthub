import time
import uuid
from datetime import datetime, timezone
import requests

BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SEC = 2
AGENT_ID = "planner"


def utc_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


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


def ensure_work_task_for_new_tasks(state: dict) -> bool:
    """
    Берём задачи со status == 'new' и создаём одну исполняемую задачу (work) со status == 'pending'.
    Возвращает True если были изменения.
    """
    tasks = state.get("tasks", [])
    changed = False

    for t in tasks:
        if t.get("status") == "new" and not t.get("planned"):
            # создаём work task
            work_id = f"work_{uuid.uuid4().hex[:8]}"
            goal = None
            answers = t.get("answers") or {}
            if isinstance(answers, dict):
                goal = answers.get("goal")

            work_task = {
                "task_id": work_id,
                "parent": t.get("task_id"),
                "type": "work",
                "title": "Implement solution (stub)",
                "goal": goal,
                "status": "pending",
                "owner": None,
                "claimed_at": None,
                "lease_until": None,
                "created_at": utc_ts(),
                "result": None,
            }

            tasks.append(work_task)
            t["planned"] = True  # пометка, чтобы не плодить дубли
            changed = True

            add_event({
                "type": "planner_created_work",
                "agent_id": AGENT_ID,
                "ts": utc_ts(),
                "parent": t.get("task_id"),
                "task_id": work_id,
                "goal": goal,
            })

    if changed:
        patch_state({"tasks": tasks})

    return changed


def heartbeat(task_count: int):
    add_event({
        "type": "planner_heartbeat",
        "agent_id": AGENT_ID,
        "ts": utc_ts(),
        "task_count": task_count,
    })


def planner_loop():
    print("[planner] started", flush=True)
    last_hb = 0.0

    while True:
        try:
            state = get_state()
            tasks = state.get("tasks", [])
            ensure_work_task_for_new_tasks(state)

            now = utc_ts()
            if now - last_hb >= 5:
                heartbeat(len(tasks))
                last_hb = now

        except Exception as e:
            print(f"[planner] error: {e}", flush=True)

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        planner_loop()
    except KeyboardInterrupt:
        print("[planner] stopped", flush=True)
