from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from .llm import chat_complete
from .prompts import build_prompts


def _repo_root() -> Path:
    # backend/agents/worker.py -> repo_root
    return Path(__file__).resolve().parents[2]


def _reports_dir(task_id: str) -> Path:
    return _repo_root() / "reports" / task_id


def _write_text(rel_path: str, content: str) -> str:
    """
    Пишем текст в repo_root/<rel_path>
    Возвращаем нормализованный относительный путь (для artifacts).
    """
    abs_path = _repo_root() / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return str(Path(rel_path)).replace("\\", "/")


def _write_json(rel_path: str, obj: Dict[str, Any]) -> str:
    return _write_text(rel_path, json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------
# Simple Markdown -> HTML
# ---------------------------
def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _md_to_html(md: str, title: str = "Report") -> str:
    """
    Мини-рендер Markdown в HTML (без внешних зависимостей).
    Поддержка:
      - # ## ### заголовки
      - списки "- " / "* "
      - ``` code blocks
      - обычные абзацы
    """
    lines = md.splitlines()
    out: List[str] = []
    in_code = False
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.rstrip("\n")

        if line.strip().startswith("```"):
            close_ul()
            if not in_code:
                in_code = True
                out.append("<pre><code>")
            else:
                in_code = False
                out.append("</code></pre>")
            continue

        if in_code:
            out.append(_escape_html(line))
            continue

        if line.startswith("### "):
            close_ul()
            out.append(f"<h3>{_escape_html(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            close_ul()
            out.append(f"<h2>{_escape_html(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            close_ul()
            out.append(f"<h1>{_escape_html(line[2:])}</h1>")
            continue

        if line.strip().startswith(("- ", "* ")):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_escape_html(line.strip()[2:])}</li>")
            continue

        if not line.strip():
            close_ul()
            out.append("<div style='height:10px'></div>")
            continue

        close_ul()
        out.append(f"<p>{_escape_html(line)}</p>")

    close_ul()

    body = "\n".join(out)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{_escape_html(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; background:#fff; color:#111; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 44px 18px 70px; }}
    h1 {{ font-size: 36px; margin: 0 0 12px; }}
    h2 {{ margin-top: 26px; }}
    h3 {{ margin-top: 18px; }}
    p {{ line-height: 1.55; }}
    pre {{ background:#0b1020; color:#dfe6ff; padding:14px; border-radius:14px; overflow:auto; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }}
    ul {{ padding-left: 20px; }}
    .meta {{ color:#666; font-size: 13px; margin-top: 10px; }}
    .card {{ border:1px solid #e6e6e6; border-radius: 14px; padding: 18px; margin-top: 16px; background:#fafafa; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {body}
      <div class="meta">Сгенерировано AgentHub (markdown → html)</div>
    </div>
  </div>
</body>
</html>"""


# ---------------------------
# Fallback templates (если LLM недоступен)
# ---------------------------
def _site_html_fallback(goal: str) -> str:
    title = "Landing Page"
    subtitle = goal.strip() or "Minimal landing page"
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:0; background:#fff; color:#111; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 48px 18px; }}
    .hero {{ padding: 56px 28px; border-radius: 16px; background: #111; color: #fff; }}
    .hero h1 {{ margin: 0 0 12px; font-size: 44px; line-height: 1.05; }}
    .hero p {{ margin: 0 0 22px; font-size: 18px; opacity: .9; max-width: 720px; }}
    .cta {{ display:inline-block; padding: 12px 18px; border-radius: 10px; background:#fff; color:#111; text-decoration:none; font-weight: 700; }}
    .grid {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }}
    .card {{ padding: 16px; border-radius: 12px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); }}
    .muted {{ opacity:.85; font-size:14px; margin-top: 10px; }}
    footer {{ padding: 24px 0; opacity: .7; font-size: 13px; }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns:1fr; }} .hero h1 {{ font-size: 34px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>{title}</h1>
      <p>{subtitle}</p>
      <a class="cta" href="#start">Начать</a>
      <div class="grid">
        <div class="card"><b>Быстро</b><div class="muted">Готовая структура без лишнего.</div></div>
        <div class="card"><b>Чисто</b><div class="muted">Аккуратные стили, легко расширять.</div></div>
        <div class="card"><b>Автономно</b><div class="muted">Supervisor + Reviewer контролируют качество.</div></div>
      </div>
      <div class="muted" id="start">Результат сохранён как result.html.</div>
    </section>
    <footer>© AgentHub</footer>
  </div>
</body>
</html>
"""


def _analytics_md_fallback(goal: str) -> str:
    g = goal.strip() or "Analytics report"
    return f"""# Аналитический отчёт

## Цель
{g}

## Executive Summary
Краткое резюме (3–6 предложений): о чём отчёт, главные выводы и что делать дальше.

## Key Findings
- Наблюдение №1 (факт/аргумент)
- Наблюдение №2 (факт/аргумент)
- Наблюдение №3 (факт/аргумент)

## Recommendations
- Рекомендация №1 (что сделать и почему)
- Рекомендация №2
- Рекомендация №3

## Risks / Limitations
- Ограничение данных / допущение
- Риск интерпретации
- Что стоит уточнить дальше

## Next Steps
- 1–3 конкретных шага продолжения
"""


def _llm_enabled() -> bool:
    """
    Можно выключить LLM, если нужно:
      set AGENTHUB_USE_LLM=0
    По умолчанию: включено.
    """
    v = (os.getenv("AGENTHUB_USE_LLM", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _looks_like_html(text: str) -> bool:
    t = (text or "").lower()
    return "<html" in t and "</html>" in t


def _meta(
    task_id: str,
    goal: str,
    mode: Dict[str, Any],
    artifacts: Dict[str, Any],
    llm_used: bool,
    model: str,
) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "goal": goal,
        "mode": mode,
        "generated_at": time.time(),
        "artifacts": artifacts,
        "llm_used": llm_used,
        "model": model,
    }


# ---------------------------
# Public API (called by Supervisor)
# ---------------------------
def worker_generate_artifacts(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Создаёт артефакты по типу продукта.
    Возвращает dict artifacts.
    """
    task_id = task.get("task_id")
    goal = task.get("goal") or ""
    mode = task.get("mode") or {}
    if not isinstance(mode, dict):
        mode = {}

    product = (mode.get("product") or "site").strip().lower()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    out_dir = _reports_dir(task_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts: Dict[str, Any] = {}

    # 1) Промпты
    prompts = build_prompts(task)

    # 2) Пробуем LLM (если включен)
    llm_text = None
    llm_used = False
    if _llm_enabled():
        llm_text = chat_complete(
            system=prompts.worker_system,
            user=prompts.worker_user,
        )
        llm_used = bool(llm_text and llm_text.strip())

    # Пишем “служебные” поля прямо в artifacts (чтобы UI мог показать без чтения файла)
    artifacts["_llm_used"] = llm_used
    artifacts["_model"] = model

    # -----------------------
    # SITE / VISUAL -> ожидаем HTML
    # -----------------------
    if product in ("site", "visual"):
        if llm_text and _looks_like_html(llm_text):
            html = llm_text.strip()
        else:
            html = _site_html_fallback(goal)

        artifacts["result_html"] = _write_text(f"reports/{task_id}/result.html", html)
        artifacts["meta_json"] = _write_json(
            f"reports/{task_id}/meta.json",
            _meta(task_id, goal, mode, artifacts, llm_used=llm_used, model=model),
        )
        return artifacts

    # -----------------------
    # ANALYTICS -> ожидаем markdown, затем HTML
    # -----------------------
    if product == "analytics":
        if llm_text and len(llm_text.strip()) > 50:
            md = llm_text.strip()
        else:
            md = _analytics_md_fallback(goal)

        artifacts["report_md"] = _write_text(f"reports/{task_id}/report.md", md)
        artifacts["result_html"] = _write_text(
            f"reports/{task_id}/result.html",
            _md_to_html(md, title="Analytics Report"),
        )
        artifacts["meta_json"] = _write_json(
            f"reports/{task_id}/meta.json",
            _meta(task_id, goal, mode, artifacts, llm_used=llm_used, model=model),
        )
        return artifacts

    # -----------------------
    # CODE -> стабильный шаблон (LLM можно расширить позже)
    # -----------------------
    if product == "code":
        proj_dir = out_dir / "project"
        proj_dir.mkdir(parents=True, exist_ok=True)

        readme_text = f"# Project\n\nGoal: {goal}\n\nGenerated by AgentHub.\n"
        main_py_text = 'print("Hello from AgentHub project")\n'

        if llm_text and len(llm_text.strip()) > 80:
            readme_text = f"# Project\n\nGoal: {goal}\n\n## Notes from LLM\n\n{llm_text.strip()}\n"

        (proj_dir / "README.md").write_text(readme_text, encoding="utf-8")
        (proj_dir / "main.py").write_text(main_py_text, encoding="utf-8")

        md = f"# Code Project\n\nСгенерирована папка `reports/{task_id}/project/`.\n\n- README.md\n- main.py\n"
        artifacts["project_dir"] = f"reports/{task_id}/project"
        artifacts["report_md"] = _write_text(f"reports/{task_id}/report.md", md)
        artifacts["result_html"] = _write_text(
            f"reports/{task_id}/result.html",
            _md_to_html(md, title="Code Project"),
        )
        artifacts["meta_json"] = _write_json(
            f"reports/{task_id}/meta.json",
            _meta(task_id, goal, mode, artifacts, llm_used=llm_used, model=model),
        )
        return artifacts

    # неизвестный product → fallback в site
    artifacts["result_html"] = _write_text(f"reports/{task_id}/result.html", _site_html_fallback(goal))
    artifacts["meta_json"] = _write_json(
        f"reports/{task_id}/meta.json",
        _meta(task_id, goal, mode, artifacts, llm_used=llm_used, model=model),
    )
    return artifacts


def worker_fix_artifacts(task: Dict[str, Any], review_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    MVP авто-фиксер:
    - для analytics добавляет недостающие секции
    - для остальных типов — регенерирует артефакты (там LLM тоже может участвовать)
    """
    task_id = task.get("task_id")
    goal = task.get("goal") or ""
    mode = task.get("mode") or {}
    if not isinstance(mode, dict):
        mode = {}

    product = (mode.get("product") or "site").strip().lower()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    artifacts = task.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    if product != "analytics":
        return worker_generate_artifacts(task)

    report_md_rel = artifacts.get("report_md") or f"reports/{task_id}/report.md"
    abs_md = _repo_root() / str(report_md_rel)

    if abs_md.exists():
        md = abs_md.read_text(encoding="utf-8")
    else:
        md = _analytics_md_fallback(goal)

    required = [
        ("## Цель", "## Цель\n" + (goal.strip() or "—") + "\n"),
        ("## Executive Summary", "## Executive Summary\nДобавь 3–6 предложений резюме.\n"),
        ("## Key Findings", "## Key Findings\n- Наблюдение №1\n- Наблюдение №2\n"),
        ("## Recommendations", "## Recommendations\n- Рекомендация №1\n- Рекомендация №2\n"),
        ("## Risks / Limitations", "## Risks / Limitations\n- Ограничения/риски\n"),
        ("## Next Steps", "## Next Steps\n- Следующий шаг №1\n"),
    ]

    fixed = md
    for marker, block in required:
        if marker.lower() not in fixed.lower():
            fixed = fixed.strip() + "\n\n" + block

    issues = review_report.get("issues") if isinstance(review_report, dict) else None
    if isinstance(issues, list) and issues:
        fixed += "\n\n## Auto Fix Log\n"
        for it in issues[:10]:
            msg = str(it.get("msg") or it)
            fixed += f"- {msg}\n"

    # При фиксе LLM не используем специально: фиксер детерминированный
    llm_used = False
    artifacts["_llm_used"] = llm_used
    artifacts["_model"] = model

    artifacts["report_md"] = _write_text(report_md_rel, fixed)
    artifacts["result_html"] = _write_text(
        f"reports/{task_id}/result.html",
        _md_to_html(fixed, title="Analytics Report"),
    )
    artifacts["meta_json"] = _write_json(
        f"reports/{task_id}/meta.json",
        _meta(task_id, goal, mode, artifacts, llm_used=llm_used, model=model),
    )
    return artifacts
