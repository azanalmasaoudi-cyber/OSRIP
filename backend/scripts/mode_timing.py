"""Measure the answer modes with the scripted stand-ins: no provider is called, nothing is billed.

The scripted model and web search are given fixed, realistic delays (a model call, a search),
so the measurement shows what the modes' own design costs or saves: how many model rounds and
searches each mode makes, and how much fetching several searches of one step at the same time
saves against fetching them one after another. Quality is measured on the same runs: whether
the answer passed the evidence checks, the tables, charts and diagrams built, and whether any
of OSRIP's internal data tools was used (it must not be, in the internet modes).

    set OSRIP_TEST_ADMIN_URL=...   (python scripts/devdb.py url)
    .venv\\Scripts\\python.exe scripts\\mode_timing.py --runs 3

Uses a throwaway database (osrip_mode_timing), dropped and recreated each run. Results are
written to docs/evaluation/mode-timing.json and printed as a table. Live timings with real
providers (paid) are taken separately with scripts/research_timing.py.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_NAME = "osrip_mode_timing"
# Never read a developer's backend/.env (real provider keys) here.
os.environ["OSRIP_ENV_FILE"] = "none"
for _name in (
    "OSRIP_ANTHROPIC_API_KEY", "OSRIP_OPENAI_API_KEY", "OSRIP_GEMINI_API_KEY",
    "OSRIP_DEEPSEEK_API_KEY", "OSRIP_RESEARCH_API_KEY",
):  # fmt: skip
    os.environ.pop(_name, None)

# Delays given to the stand-ins (seconds): typical of a hosted model turn and a web search.
MODEL_DELAY = 0.6
SEARCH_DELAY = 0.8
INTERNAL = {
    "list_indicators", "list_areas", "get_observations", "latest_period", "compare_periods",
    "explain_calculation", "get_forecast", "scenario_projection", "make_table", "make_chart",
    "balance_analysis", "growth_rate", "share_of_total", "compare_areas", "run_study",
    "data_quality_notes",
}  # fmt: skip
CASES = [
    # (name, question, language, mode, parallel fetches)
    ("quick_en", "web electricity generation 2023", "en", "quick", 3),
    ("deep_en_sequential", "Write a report on electricity generation in 2023", "en", "research", 1),
    ("deep_en_parallel", "Write a report on electricity generation in 2023", "en", "research", 3),
    ("deep_ar_parallel", "اكتب تقريرا عن توليد الكهرباء في 2023", "ar", "research", 3),
]


def _database() -> None:
    admin = make_url(os.environ["OSRIP_TEST_ADMIN_URL"])
    plain = admin.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    os.environ["OSRIP_DATABASE_URL"] = admin.set(database=DB_NAME).render_as_string(
        hide_password=False
    )
    os.environ["OSRIP_ASSISTANT_PROVIDER"] = "fake"
    os.environ["OSRIP_ASSISTANT_FALLBACK_PROVIDER"] = ""
    os.environ["OSRIP_RESEARCH_PROVIDER"] = "fake"
    os.environ["OSRIP_RESEARCH_FALLBACK_PROVIDER"] = ""
    os.environ["OSRIP_RESEARCH_CACHE_HOURS"] = "0"  # every run searches afresh

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    from app.db.session import session_factory
    from app.services.fixtures import seed_booklet_fixtures

    with session_factory()() as session:
        seed_booklet_fixtures(session)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    _database()

    from app.core.config import get_settings
    from app.domain.enums import DataMode
    from app.services.assistant import grounding, service
    from app.services.assistant.provider import FakeProvider
    from app.services.research.search import FakeSearch

    calls: dict[str, int] = {}
    tools_used: list[str] = []
    real_complete, real_search, real_run_tool = (
        FakeProvider.complete, FakeSearch.search, service.run_tool,
    )  # fmt: skip

    def slow_complete(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        calls["model"] = calls.get("model", 0) + 1
        time.sleep(MODEL_DELAY)
        return real_complete(self, *a, **k)

    def slow_search(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        calls["search"] = calls.get("search", 0) + 1
        time.sleep(SEARCH_DELAY)
        return real_search(self, *a, **k)

    def counted_run_tool(tools, name, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        tools_used.append(name)
        return real_run_tool(tools, name, *a, **k)

    FakeProvider.complete = slow_complete  # type: ignore[method-assign]
    FakeSearch.search = slow_search  # type: ignore[method-assign]
    service.run_tool = counted_run_tool
    s = get_settings()
    rows = []
    for name, question, language, mode, fetches in CASES:
        s.research_parallel_fetches = fetches
        walls: list[float] = []
        for _ in range(args.runs):
            calls.clear()
            tools_used.clear()
            t0 = time.perf_counter()
            final, ledger, _model = service._run_model(
                question, [], language, DataMode.SYNTHETIC, web=True, mode=mode
            )
            walls.append(time.perf_counter() - t0)
            text = str(final.get("text", ""))
            cited = [str(c) for c in final.get("citations") or []] + grounding.inline_markers(text)
            verdict = grounding.validate(text, cited, ledger.items)
        rows.append(
            {
                "case": name,
                "mode": mode,
                "language": language,
                "parallel_fetches": fetches,
                "runs": args.runs,
                "wall_s_median": round(statistics.median(walls), 2),
                "wall_s_min": round(min(walls), 2),
                "model_calls": calls.get("model", 0),
                "searches": calls.get("search", 0),
                "tools": len(tools_used),
                "internal_tools": sorted(set(tools_used) & INTERNAL),
                "answer_verified": bool(verdict.ok and text),
                "status": final.get("status"),
                "research_table_rows": sum(len(t["rows"]) for t in ledger.research_tables),
                "research_charts": len(ledger.research_charts),
                "diagrams": len(ledger.diagrams),
                "plan_questions": len(ledger.meta.get("plan") or []),
            }
        )
        print(json.dumps(rows[-1], ensure_ascii=False))
    out = BACKEND.parent / "docs" / "evaluation" / "mode-timing.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "stand_ins": {"model_delay_s": MODEL_DELAY, "search_delay_s": SEARCH_DELAY},
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwritten {out.relative_to(BACKEND.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
