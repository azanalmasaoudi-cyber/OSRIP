"""Measures OSRIP against a running API, for the academic evaluation (repeatable).

    backend\\.venv\\Scripts\\python.exe tools\\evaluate_osrip.py \\
        --api http://127.0.0.1:8010/api/v1 --out docs\\evaluation --check-links

What it measures (nothing is estimated or invented; every number comes from a request made now):

1. Calculation correctness: for every indicator, area, breakdown and frequency the availability
   lists, the full published range is requested and each figure of the server's summary is
   recomputed here, independently, from the rows the table shows: period counts, first and last
   values, the change between them (absolute and percent), highest and lowest, and the total
   (only for a period total with every period published and exact). Also checked: rows in time
   order, missing periods never given as zero, and the CSV download holding the same values as
   the table.
2. Citation validity: every published figure (and year-to-date total) names a source with an
   address; every source cited by those rows has an https address, and its host is
   classed as the statistics office (ncsi.gov.om, data.gov.om), another government site
   (.gov.om) or another publisher (for example a news report, which the source registry marks as
   secondary); with --check-links each distinct address is requested once (HEAD, then GET) and its
   HTTP status recorded.
3. Response times of the API on this machine: availability, timeline and CSV (median, 95th
   percentile and maximum, milliseconds).

The results are written as JSON and Markdown with the date and the API address. Standard
library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

SECTIONS = ("electricity", "water", "food_security", "trade")
STATISTICAL_HOSTS = ("ncsi.gov.om", "data.gov.om")  # the statistics office and its data portal
TIMES: dict[str, list[float]] = {"availability": [], "timeline": [], "csv": []}


def get(url: str, kind: str) -> bytes:
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - our own API
        body = response.read()
    TIMES[kind].append((time.perf_counter() - started) * 1000)
    return body


def dec(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def check(self, ok: bool, label: str) -> None:
        if ok:
            self.passed += 1
        else:
            self.failed.append(label)


def verify(doc: dict[str, Any], value_type: str, label: str, checks: Checks) -> None:
    rows = [r for r in doc["rows"] if r["nature"] != "forecast"]
    starts = [r["period_start"] for r in rows]
    checks.check(
        starts == sorted(starts) and len(set(starts)) == len(starts), f"{label}: rows in time order"
    )
    checks.check(
        all(r["value"] is None for r in rows if r["nature"] == "missing"),
        f"{label}: missing never zero",
    )
    valued = [r for r in rows if r["value"] is not None]
    checks.check(
        all((r.get("source") or {}).get("url") for r in valued + doc.get("year_to_date", [])),
        f"{label}: every published figure has a source address",
    )
    s = doc.get("summary") or {}
    checks.check(s.get("periods") == len(rows), f"{label}: period count")
    checks.check(s.get("with_value") == len(valued), f"{label}: valued count")
    checks.check(s.get("missing") == len(rows) - len(valued), f"{label}: missing count")
    if not valued:
        return
    first, last = valued[0], valued[-1]
    checks.check(
        (s.get("first") or {}).get("period_start") == first["period_start"],
        f"{label}: first period",
    )
    checks.check(
        (s.get("last") or {}).get("period_start") == last["period_start"], f"{label}: last period"
    )
    a, b = dec(first["value"]), dec(last["value"])
    change = s.get("change")
    exact = not first["value_operator"] and not last["value_operator"]
    if first is not last and exact and change and change.get("absolute") is not None:
        checks.check(dec(change["absolute"]) == b - a, f"{label}: absolute change")  # type: ignore[operator]
        if a and change.get("percent") is not None:
            pct = ((b - a) / a * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)  # type: ignore[operator]
            checks.check(
                abs(dec(change["percent"]) - pct) <= Decimal("0.01"), f"{label}: percent change"
            )  # type: ignore[operator]
    exact_rows = [r for r in valued if not r["value_operator"]]
    if exact_rows:
        top = max(exact_rows, key=lambda r: Decimal(r["value"]))
        low = min(exact_rows, key=lambda r: Decimal(r["value"]))
        checks.check(
            dec((s.get("highest") or {}).get("value")) == Decimal(top["value"]), f"{label}: highest"
        )
        checks.check(
            dec((s.get("lowest") or {}).get("value")) == Decimal(low["value"]), f"{label}: lowest"
        )
    additive = (
        value_type == "period_total" and len(valued) == len(rows) and len(exact_rows) == len(valued)
    )
    if additive:
        total = sum((Decimal(r["value"]) for r in valued), Decimal(0))
        checks.check(dec(s.get("total")) == total, f"{label}: total of a flow")
    else:
        checks.check(s.get("total") is None, f"{label}: no total unless additive and complete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api", default="http://127.0.0.1:8010/api/v1")
    parser.add_argument("--mode", default="verified_source")
    parser.add_argument("--out", default="docs/evaluation")
    parser.add_argument("--check-links", action="store_true")
    args = parser.parse_args()
    checks = Checks()
    sources: dict[str, str] = {}
    series_count = 0
    csv_matches = 0
    for section in SECTIONS:
        q = urllib.parse.urlencode({"data_mode": args.mode, "section": section})
        availability = json.loads(get(f"{args.api}/series/availability?{q}", "availability"))
        for ind in availability["indicators"]:
            for entry in ind["series"]:
                for view, periods in entry["views"].items():
                    if not periods:
                        continue
                    params = {
                        "data_mode": args.mode,
                        "indicator": ind["code"],
                        "area": entry["area"]["code"],
                        "view": view,
                        "period_from": periods[0]["start"],
                        "period_to": periods[-1]["end"],
                    }
                    for key in ("commodity", "partner"):
                        if entry.get(key):
                            params[key] = entry[key]["code"]
                    if entry.get("flow"):
                        params["flow"] = entry["flow"]
                    query = urllib.parse.urlencode(params)
                    doc = json.loads(get(f"{args.api}/series/timeline?{query}", "timeline"))
                    label = f"{section}/{ind['code']}/{entry['area']['code']}/{view}"
                    if doc.get("status") != "ok":
                        checks.check(False, f"{label}: status {doc.get('status')}")
                        continue
                    series_count += 1
                    verify(doc, ind["value_type"], label, checks)
                    text = get(f"{args.api}/series/timeline.csv?{query}", "csv").decode("utf-8-sig")
                    lines = [
                        line for line in text.splitlines() if not line.lstrip('"').startswith("#")
                    ]
                    rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
                    table = [
                        (r["period_start"], r["value"] or "")
                        for r in doc["rows"] + doc["year_to_date"]
                    ]
                    same = [(r["period_start"], r["value"]) for r in rows] == table
                    csv_matches += same
                    checks.check(same, f"{label}: CSV equals table")
                    for r in doc["rows"]:
                        src = r.get("source") or {}
                        if src.get("url"):
                            sources[src["url"]] = src.get("dataset_title") or ""
    links: list[dict[str, Any]] = []
    for url, title in sorted(sources.items()):
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        if any(host == h or host.endswith("." + h) for h in STATISTICAL_HOSTS):
            kind = "statistics office"
        elif host.endswith(".gov.om"):
            kind = "government"
        else:
            kind = "other publisher"
        status: int | str | None = None
        if args.check_links:
            for method in ("HEAD", "GET"):
                try:
                    if parts.scheme not in ("http", "https"):
                        break
                    req = urllib.request.Request(  # noqa: S310 - http(s) only, checked above
                        url, method=method, headers={"User-Agent": "OSRIP-evaluation/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 - cited sources
                        status = response.status
                    break
                except urllib.error.HTTPError as exc:
                    status = exc.code
                    if exc.code not in (403, 405):
                        break
                except (urllib.error.URLError, TimeoutError) as exc:
                    status = f"error: {getattr(exc, 'reason', exc)}"
        links.append(
            {
                "url": url,
                "title": title,
                "https": parts.scheme == "https",
                "kind": kind,
                "status": status,
            }
        )

    def stats(values: list[float]) -> dict[str, float | int]:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
        return {
            "n": len(values),
            "median_ms": round(statistics.median(values), 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(max(values), 1),
        }

    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "api": args.api,
        "data_mode": args.mode,
        "series_checked": series_count,
        "checks_passed": checks.passed,
        "checks_failed": len(checks.failed),
        "failures": checks.failed,
        "csv_equal_to_table": f"{csv_matches}/{series_count}",
        "sources": links,
        "times": {k: stats(v) for k, v in TIMES.items()},
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = result["measured_at"][:10]
    (out / f"measurements-{stamp}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    md = [
        f"# Measurements, {stamp}",
        "",
        f"API `{args.api}`, data mode `{args.mode}`, measured {result['measured_at']} (UTC).",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Series checked (indicator × area × breakdown × frequency) | {series_count} |",
        f"| Calculation checks passed | {checks.passed} of {checks.passed + len(checks.failed)} |",
        f"| CSV download equal to the table | {csv_matches} of {series_count} |",
        f"| Cited sources with an https address | "
        f"{sum(1 for x in links if x['https'])} of {len(links)} |",
        f"| … on the statistics office (ncsi.gov.om, data.gov.om) | "
        f"{sum(1 for x in links if x['kind'] == 'statistics office')} of {len(links)} |",
    ]
    if args.check_links:
        ok = sum(1 for x in links if isinstance(x["status"], int) and 200 <= x["status"] < 400)
        md.append(f"| Cited sources answering 2xx/3xx | {ok} of {len(links)} |")
    md += [
        "",
        "| Request | n | Median (ms) | 95th percentile (ms) | Max (ms) |",
        "|---|---|---|---|---|",
    ]
    for kind, s in result["times"].items():
        if s.get("n"):
            md.append(f"| {kind} | {s['n']} | {s['median_ms']} | {s['p95_ms']} | {s['max_ms']} |")
    if checks.failed:
        md += ["", "## Failed checks", ""] + [f"- {f}" for f in checks.failed]
    md += ["", "## Cited sources", ""] + [
        f"- {x['title'] or x['url']} — {x['kind']}{'' if x['https'] else ', not https'}"
        + (f" — HTTP {x['status']}" if x["status"] is not None else "")
        for x in links
    ]
    (out / f"measurements-{stamp}.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8", newline="\n"
    )
    print("\n".join(md[:12]))
    return 0 if not checks.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
