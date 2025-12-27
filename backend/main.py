from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import time

from . import db

app = FastAPI(title="AgentHub API", version="1.0.0")


class Patch(BaseModel):
    patch: Dict[str, Any]


class Event(BaseModel):
    event: Dict[str, Any]


class ResetRequest(BaseModel):
    state: Dict[str, Any]


class AnswerRequest(BaseModel):
    task_id: str
    answers: Dict[str, Any]


@app.get("/")
def home():
    return {"ok": True, "message": "Backend is running"}


@app.get("/state")
def get_state():
    return db.read_state()


@app.post("/patch")
def patch_state(req: Patch):
    return db.update_state(req.patch)


@app.post("/event")
def add_event(req: Event):
    return db.add_event(req.event)


@app.post("/reset")
def reset_state(req: ResetRequest):
    db.write_state(req.state)
    return {"ok": True}


@app.post("/answer")
def answer(req: AnswerRequest):
    # 1. Save task to state
    task = {
        "task_id": req.task_id,
        "answers": req.answers,
        "created_at": time.time(),
        "status": "new"
    }

    state = db.read_state()
    tasks = state.setdefault("tasks", [])
    tasks.append(task)
    db.write_state(state)

    # 2. Emit event for planner
    event = {
        "type": "new_task",
        "task_id": req.task_id,
        "payload": req.answers,
        "ts": time.time()
    }

    db.add_event(event)

    return {"ok": True, "message": "Task accepted", "task_id": req.task_id}
