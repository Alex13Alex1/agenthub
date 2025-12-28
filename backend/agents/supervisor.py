from __future__ import annotations

import time
from typing import Any, Dict

from .. import db
from .worker import worker_generate_artifacts, worker_fix_artifacts
from .reviewer import reviewer_review_task


DEFAULT_LIMITS = {
    "max_review_cycles": 5,  # защита от зацикливания
}


def supervisor_tick(task_id: str) -> Dict[str, Any]:
    """
    Supervisor управляет lifecycle задачи:
      CREATED -> PLANNING -> WORKING -> REVIEWING -> (FIXING -> REVIEWING)* -> DONE/FAILED

    Дополнительно:
      - пишет события tick_started / tick_finished / tick_error
      - в событиях артефактов показывает llm_used/model
    """
    t0 = time.time()

    task = db.get_task(task_id)
    if not task:
        db.add_event({"type": "tick_error", "task_id": task_id, "ts": time.time(), "payload": {"error": "task_not_found"}})
        return {"ok": False, "error": "task_not_found", "task_id": task_id}

    status_before = (task.get("status") or "CREATED").upper()

    # лимиты / счетчики
    limits = task.get("limits")
    if not isinstance(limits, dict):
        limits = DEFAULT_LIMITS.copy()

    review_cycles = int(task.get("review_cycles") or 0)
    attempts = int(task.get("attempts") or 0)

    def emit(type_: str, payload: Dict[str, Any] | None = None) -> None:
        ev = {"type": type_, "task_id": task_id, "ts": time.time()}
        if payload is not None:
            ev["payload"] = payload
        db.add_event(ev)

    def patch(p: Dict[str, Any]) -> Dict[str, Any]:
        base = {"limits": limits, "attempts": attempts, "review_cycles": review_cycles}
        base.update(p)
        return db.patch_task(task_id, base)

    emit("tick_started", {"status": status_before})

    try:
        # Финалы
        if status_before in ("DONE", "FAILED"):
            emit("tick_finished", {"status": status_before, "elapsed_ms": int((time.time() - t0) * 1000)})
            return {"ok": True, "task": task, "message": "Already finished"}

        # CREATED -> PLANNING
        if status_before == "CREATED":
            patch({"status": "PLANNING", "progress": 20})
            emit("status_changed", {"from": status_before, "to": "PLANNING", "progress": 20})
            task_after = db.get_task(task_id)
            emit("tick_finished", {"status": "PLANNING", "elapsed_ms": int((time.time() - t0) * 1000)})
            return {"ok": True, "task": task_after}

        # PLANNING -> WORKING
        if status_before == "PLANNING":
            patch({"status": "WORKING", "progress": 55})
            emit("status_changed", {"from": status_before, "to": "WORKING", "progress": 55})
            task_after = db.get_task(task_id)
            emit("tick_finished", {"status": "WORKING", "elapsed_ms": int((time.time() - t0) * 1000)})
            return {"ok": True, "task": task_after}

        # WORKING -> generate artifacts -> REVIEWING
        if status_before == "WORKING":
            try:
                artifacts = worker_generate_artifacts(task)
                patch(
                    {
                        "artifacts": artifacts,
                        "result": {"type": "artifact", "artifact": artifacts.get("result_html")},
                        "status": "REVIEWING",
                        "progress": 92,
                        "error": None,
                    }
                )

                emit(
                    "artifact_created",
                    {
                        "artifacts": list(artifacts.keys()),
                        "llm_used": bool(artifacts.get("_llm_used")),
                        "model": artifacts.get("_model"),
                    },
                )
                emit("status_changed", {"from": status_before, "to": "REVIEWING", "progress": 92})

                task_after = db.get_task(task_id)
                emit("tick_finished", {"status": "REVIEWING", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": True, "task": task_after}
            except Exception as e:
                patch({"status": "FAILED", "progress": 100, "error": f"Worker error: {e}"})
                emit("task_failed", {"reason": f"Worker error: {e}"})
                emit("tick_error", {"status": "FAILED", "error": "worker_error", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": False, "task": db.get_task(task_id), "error": "worker_error"}

        # REVIEWING -> call reviewer -> approve/fix/fail
        if status_before == "REVIEWING":
            review_report = reviewer_review_task(task)
            verdict = (review_report.get("verdict") or "fail").lower()

            emit("review_finished", {"review": review_report})

            if verdict == "approve":
                patch({"status": "DONE", "progress": 100, "review": review_report})
                emit("status_changed", {"from": status_before, "to": "DONE", "progress": 100})
                emit("task_done")
                task_after = db.get_task(task_id)
                emit("tick_finished", {"status": "DONE", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": True, "task": task_after}

            if verdict == "fail":
                patch({"status": "FAILED", "progress": 100, "review": review_report, "error": "Quality gate failed"})
                emit("task_failed", {"reason": "Quality gate failed", "review": review_report})
                task_after = db.get_task(task_id)
                emit("tick_finished", {"status": "FAILED", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": False, "task": task_after, "error": "quality_failed"}

            # verdict == fix
            review_cycles_inc = int(task.get("review_cycles") or 0) + 1
            attempts_inc = int(task.get("attempts") or 0) + 1

            if review_cycles_inc > int(limits.get("max_review_cycles", 5)):
                patch(
                    {
                        "status": "FAILED",
                        "progress": 100,
                        "review": review_report,
                        "error": f"Max review cycles exceeded ({limits.get('max_review_cycles')})",
                        "review_cycles": review_cycles_inc,
                        "attempts": attempts_inc,
                    }
                )
                emit("task_failed", {"reason": "max_review_cycles_exceeded", "review_cycles": review_cycles_inc})
                task_after = db.get_task(task_id)
                emit("tick_finished", {"status": "FAILED", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": False, "task": task_after, "error": "max_review_cycles_exceeded"}

            patch(
                {
                    "status": "FIXING",
                    "progress": 78,
                    "review": review_report,
                    "review_cycles": review_cycles_inc,
                    "attempts": attempts_inc,
                }
            )
            emit(
                "status_changed",
                {"from": status_before, "to": "FIXING", "progress": 78, "review_cycles": review_cycles_inc},
            )
            task_after = db.get_task(task_id)
            emit("tick_finished", {"status": "FIXING", "elapsed_ms": int((time.time() - t0) * 1000)})
            return {"ok": True, "task": task_after}

        # FIXING -> worker_fix -> back to REVIEWING
        if status_before == "FIXING":
            try:
                task_latest = db.get_task(task_id) or task
                review_report = task_latest.get("review") or {}
                artifacts = worker_fix_artifacts(task_latest, review_report)

                patch(
                    {
                        "artifacts": artifacts,
                        "result": {"type": "artifact", "artifact": artifacts.get("result_html")},
                        "status": "REVIEWING",
                        "progress": 92,
                        "error": None,
                    }
                )
                emit(
                    "artifact_updated",
                    {
                        "artifacts": list(artifacts.keys()),
                        "llm_used": bool(artifacts.get("_llm_used")),
                        "model": artifacts.get("_model"),
                    },
                )
                emit("status_changed", {"from": status_before, "to": "REVIEWING", "progress": 92})

                task_after = db.get_task(task_id)
                emit("tick_finished", {"status": "REVIEWING", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": True, "task": task_after}
            except Exception as e:
                patch({"status": "FAILED", "progress": 100, "error": f"Fixer error: {e}"})
                emit("task_failed", {"reason": f"Fixer error: {e}"})
                emit("tick_error", {"status": "FAILED", "error": "fixer_error", "elapsed_ms": int((time.time() - t0) * 1000)})
                return {"ok": False, "task": db.get_task(task_id), "error": "fixer_error"}

        # неизвестный статус
        patch({"status": "FAILED", "progress": 100, "error": f"Unknown status: {status_before}"})
        emit("task_failed", {"reason": f"Unknown status: {status_before}"})
        task_after = db.get_task(task_id)
        emit("tick_finished", {"status": "FAILED", "elapsed_ms": int((time.time() - t0) * 1000)})
        return {"ok": False, "task": task_after, "error": "unknown_status"}

    except Exception as e:
        # Любая неожиданная ошибка — не валим сервер, фиксируем событие
        emit("tick_error", {"error": str(e), "elapsed_ms": int((time.time() - t0) * 1000)})
        return {"ok": False, "task": db.get_task(task_id), "error": "tick_exception", "detail": str(e)}
