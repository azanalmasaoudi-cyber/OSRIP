"""Measure where a live research answer spends its time: model calls, web searches, page
reads and the other tools, then the answer checks. It calls the real configured providers
(paid; a few calls per question), so run it only deliberately, against a development
database:

    .venv\\Scripts\\python.exe scripts\\research_timing.py --label before --fresh
    .venv\\Scripts\\python.exe scripts\\research_timing.py --label cached

``--fresh`` switches the search and document caches off for the run (OSRIP_RESEARCH_CACHE_HOURS
=0) so two runs compare the same amount of work. Timings are appended as JSON lines to
docs/evaluation/research-timing.jsonl. Only durations, counts and statuses are written: no
question text beyond the fixed test questions below, no answers, prompts or keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "water_en": "What is the latest officially published total desalinated water production in "
    "Oman, and which official source reports it? Search the web.",
    "power_ar": "ما أحدث رقم منشور رسمياً لإجمالي إنتاج الكهرباء في سلطنة عُمان، وما مصدره الرسمي؟ "
    "ابحث في الإنترنت.",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--fresh", action="store_true", help="no search or document cache")
    parser.add_argument("--only", choices=sorted(QUESTIONS), action="append")
    args = parser.parse_args()
    if args.fresh:
        os.environ["OSRIP_RESEARCH_CACHE_HOURS"] = "0"
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    from app.domain.enums import DataMode
    from app.services.assistant import service, tools
    from app.services.assistant.provider import get_provider

    provider = get_provider()
    if provider is None:
        print("No answer provider is configured.")
        return 2
    timings: dict[str, list[float]] = defaultdict(list)

    original_complete = type(provider).complete

    def timed_complete(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        t0 = time.perf_counter()
        try:
            return original_complete(self, *a, **k)
        finally:
            timings["model"].append(time.perf_counter() - t0)

    original_run_tool = tools.run_tool

    def timed_run_tool(t, name, arguments):  # noqa: ANN001, ANN202
        t0 = time.perf_counter()
        try:
            return original_run_tool(t, name, arguments)
        finally:
            timings[f"tool:{name}"].append(time.perf_counter() - t0)

    from app.services.research import parallel

    def timed(name, fn):  # noqa: ANN001, ANN202
        def wrapper(*a, **k):  # noqa: ANN002, ANN003, ANN202
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                timings[name].append(time.perf_counter() - t0)

        return wrapper

    type(provider).complete = timed_complete
    service.run_tool = timed_run_tool
    # Searches and pages fetched at the same time before their tools run (after the change).
    if hasattr(parallel, "prefetch_reads"):
        parallel.prefetch_reads = timed("parallel_reads", parallel.prefetch_reads)
        parallel.prefetch_searches = timed("parallel_searches", parallel.prefetch_searches)
    out = BACKEND.parent / "docs" / "evaluation" / "research-timing.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    for key in args.only or sorted(QUESTIONS):
        timings.clear()
        language = "ar" if key.endswith("_ar") else "en"
        t0 = time.perf_counter()
        status = "ok"
        evidence: dict[str, int] = {}
        try:
            answer, ledger, model = service._run_model(
                QUESTIONS[key], [], language, DataMode.VERIFIED_SOURCE, web=True, mode="research"
            )
            items = list(ledger.by_id().values())
            evidence = {
                "web_items": sum(1 for i in items if i.get("kind") == "web"),
                "pages_read": ledger.pages,
                "searches": ledger.searches,
                "cached_items": sum(1 for i in items if i.get("cached")),
            }
            checking0 = time.perf_counter()
            # The answer checks (every number against the evidence), as the service runs them.
            from app.services.assistant import grounding

            text = str(answer.get("text", "")).strip()
            cited = [str(c) for c in answer.get("citations") or []]
            cited += grounding.inline_markers(text)
            visible = [i for i in ledger.items if i.get("kind") != "grounded_context"]
            verdict = grounding.validate(text, cited, visible)
            if verdict.ok:
                grounding.validate_structured(
                    answer, visible, question=QUESTIONS[key], mode="research"
                )
            timings["checking"].append(time.perf_counter() - checking0)
            evidence["answer_verified"] = int(bool(verdict.ok and text))
        except Exception as exc:  # noqa: BLE001
            status = f"{type(exc).__name__}: {str(exc)[:80]}"
            model = getattr(provider, "name", "?")
        wall = time.perf_counter() - t0
        row = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "label": args.label,
            "fresh": args.fresh,
            "question": key,
            "provider": provider.vendor,
            "model": model,
            "status": status,
            "wall_s": round(wall, 2),
            "model_calls": len(timings["model"]),
            "model_s": round(sum(timings["model"]), 2),
            **{
                k.replace("tool:", "") + "_s": round(sum(v), 2)
                for k, v in timings.items()
                if k.startswith(("tool:", "parallel_")) or k == "checking"
            },
            **{
                k.replace("tool:", "") + "_n": len(v)
                for k, v in timings.items()
                if k.startswith(("tool:", "parallel_"))
            },
            **evidence,
        }
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
