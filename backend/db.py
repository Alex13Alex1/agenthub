import json
import os
import time
from pathlib import Path
from typing import Any, Dict

STATE_PATH = Path(__file__).parent / "state.json"

# сколько событий максимум храним (чтобы heartbeat не раздувал файл)
MAX_EVENTS = 200


def _default_state() -> Dict[str, Any]:
    return {
        "goal": None,
        "tasks": [],
        "events": [],
        "answers": {},
    }


def read_state(retries: int = 5, delay: float = 0.05) -> Dict[str, Any]:
    """
    Read state.json safely.
    If another process writes at the same time, we might briefly read partial file -> JSONDecodeError.
    We'll retry a few times.
    """
    if not STATE_PATH.exists():
        base = _default_state()
        write_state(base)
        return base

    last_err: Exception | None = None
    for _ in range(retries):
        try:
            raw = STATE_PATH.read_text(encoding="utf-8").strip()
            if not raw:
                # empty file (partial write) -> retry
                time.sleep(delay)
                continue
            data = json.loads(raw)
            if not isinstance(data, dict):
                return _default_state()
            # гарантируем ключи
            data.setdefault("goal", None)
            data.setdefault("tasks", [])
            data.setdefault("events", [])
            data.setdefault("answers", {})
            return data
        except json.JSONDecodeError as e:
            last_err = e
            time.sleep(delay)

    # если совсем плохо — возвращаем дефолт, но не падаем сервером
    # (лучше так, чем 500 на каждом /state)
    return _default_state()


def write_state(state: Dict[str, Any]) -> None:
    """
    Atomic write:
    write to temp file then replace state.json
    """
    tmp_path = STATE_PATH.with_suffix(".json.tmp")

    payload = json.dumps(state, ensure_ascii=False, indent=2)
    tmp_path.write_text(payload, encoding="utf-8")

    # атомарная замена (Windows тоже ок)
    os.replace(tmp_path, STATE_PATH)


def update_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge patch into state (top-level keys only)."""
    state = read_state()
    state.update(patch)
    write_state(state)
    return state


def add_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Append event to events list (keep only last MAX_EVENTS)."""
    state = read_state()
    events = state.setdefault("events", [])
    events.append(event)
    if len(events) > MAX_EVENTS:
        state["events"] = events[-MAX_EVENTS:]
    write_state(state)
    return {"ok": True, "event": event}
