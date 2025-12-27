from backend import db
import time

AGENT_ID = "reviewer"

def run():
    print("Reviewer agent started")

    while True:
        state = db.read_state()
        tasks = state.get("tasks", [])

        changed = False

        for task in tasks:
            if task.get("status") == "completed" and not task.get("reviewed", False):
                task_id = task.get("id")
                title = task.get("title")

                print(f"[REVIEW] completed task: {task_id} - {title}")

                # 1. помечаем как проверенную
                task["reviewed"] = True
                changed = True

                # 2. пишем событие
                db.add_event({
                    "type": "task_reviewed",
                    "task_id": task_id,
                    "title": title,
                    "agent": AGENT_ID,
                })

        if changed:
            db.write_state(state)

        time.sleep(5)


if __name__ == "__main__":
    run()
