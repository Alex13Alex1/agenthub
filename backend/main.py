from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

import db

app = FastAPI(title="AgentHub API", version="1.0.0")


class Patch(BaseModel):
    patch: Dict[str, Any]


class Event(BaseModel):
    event: Dict[str, Any]


class ResetRequest(BaseModel):
    state: Dict[str, Any]


@app.get("/")
def home():
    return {"ok": True, "message": "Backend is running!"}


@app.get("/state")
def get_state():
    return db.read_state()


@app.post("/state/update")
def post_update_state(body: Patch):
    return db.update_state(body.patch)


@app.post("/events")
def post_event(body: Event):
    return db.add_event(body.event)


@app.post("/reset")
def reset_state(body: ResetRequest):
    """Reset state to a known fixture (for testing only)."""
    db.write_state(body.state)
    return {"ok": True, "message": "State reset"}
