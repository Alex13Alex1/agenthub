import json
from pathlib import Path
from typing import Any, Dict

STATE_PATH = Path(__file__).parent / "state.json"


def read_state() -> Dict[str, Any]:
    """Read state from state.json file."""
    if not STATE_PATH.exists():
        base = {"goal": "", "tasks": [], "notes": [], "artifacts": {}, "events": []}
        write_state(base)
        return base
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: Dict[str, Any]) -> None:
    """Write state to state.json file."""
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_state(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge patch into state (top-level keys only)."""
    state = read_state()
    state.update(patch)
    write_state(state)
    return state


def add_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Append event to events list."""
    state = read_state()
    state.setdefault("events", []).append(event)
    write_state(state)
    return {"ok": True, "event": event}
