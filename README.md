# AgentHub MVP

Backend MVP на FastAPI: агентная система (Supervisor → Worker → Reviewer), которая принимает цель (goal), прогоняет lifecycle задачи и сохраняет результат как HTML-артефакт, доступный через API и Web UI.

## Возможности (MVP)
- Создание задач: `POST /tasks`
- Прогресс и статусы задач: `GET /tasks/{task_id}`
- Supervisor orchestration: `POST /tasks/{task_id}/tick`
- Timeline событий по задаче: `GET /tasks/{task_id}/events`
- Результат задачи (HTML): `GET /tasks/{task_id}/result`
- Статика: `/reports/<task_id>/result.html`
- UI: `/ui`

## Запуск (Windows PowerShell — рекомендовано)
> Самый стабильный способ: задавать переменные окружения напрямую (без .env).

1) Перейди в корень проекта:
```powershell
cd C:\Users\alexs\OneDrive\Рабочий стол\amc-site\agenthub-mvp
