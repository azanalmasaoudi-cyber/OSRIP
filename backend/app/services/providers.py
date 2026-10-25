"""External AI and search providers: what is configured, metering, limits and readiness.

Providers (each through its official API; consumer chat websites are never automated, and a
consumer subscription is not API access):

* anthropic: Claude, Messages API (answering).
* openai: Responses API: function tools (answering) and the ``web_search`` tool (search route).
* gemini: Interactions API: function tools (answering) and Grounding with Google Search
  (search route; its results are shown to the person verbatim with the Search Suggestions
  and never given to another model, as the Gemini API terms require).
* brave: Brave Search API (search route).
* firecrawl: Firecrawl v2 (/scrape, /map): page retrieval for background studies, billed in
  credits (1 per page, plus 1 per PDF page parsed).
* deepseek: DeepSeek Chat Completions API: function tools (answering). Usage-billed; used only
  with OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED=true (never switched to silently).

Every call is recorded in ``provider_call`` (outcome, time, tokens, estimated cost; never the
question or the answer). Before each call ``meter.check`` enforces the daily request limit and,
when prices are configured, the daily budget per provider. Readiness reports, per provider:

* unavailable: not chosen, or a required setting is missing (names only, never values);
* configured: settings present, never tested (a key alone proves nothing);
* tested: the latest test or call succeeded;
* failed: the latest test or call failed (with its code).
"""

from __future__ import annotations

import contextvars
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import desc, func, select

from app.core.config import get_settings

log = logging.getLogger("osrip.providers")


@dataclass(frozen=True)
class Spec:
    name: str
    label: str
    capabilities: tuple[str, ...]
    docs: str
    # How use is paid for (from the provider's own price page; shown in Settings):
    # usage_billed | free_tier_available | plan | credits
    billing: str = "usage_billed"


CATALOG: dict[str, Spec] = {
    "anthropic": Spec(
        "anthropic", "Anthropic Claude (Messages API)", ("answer",),
        "https://docs.anthropic.com/en/api/messages",
    ),
    "openai": Spec(
        "openai", "OpenAI (Responses API)", ("answer", "search"),
        "https://developers.openai.com/api/docs/guides/tools-web-search",
    ),
    "gemini": Spec(
        "gemini", "Google Gemini (Interactions API, Grounding with Google Search)",
        ("answer", "search"), "https://ai.google.dev/gemini-api/docs/google-search",
        "free_tier_available",
    ),
    "brave": Spec(
        "brave", "Brave Search API", ("search",),
        "https://api-dashboard.search.brave.com/app/documentation", "plan",
    ),
    "firecrawl": Spec(
        "firecrawl", "Firecrawl (page retrieval for studies)", ("retrieve",),
        "https://docs.firecrawl.dev/api-reference/endpoint/scrape", "credits",
    ),
    "deepseek": Spec(
        "deepseek", "DeepSeek (Chat Completions, Search and Fetch APIs, usage-billed)",
        ("answer", "search", "retrieve"), "https://api-docs.deepseek.com/guides/search",
    ),
}  # fmt: skip

FAKES = {"fake", "fake-openai", "fake-gemini"}


class LimitReached(Exception):
    """A daily request limit or budget stops the call (the code is the str)."""


# ------------------------------------------------------------------ settings and roles


def missing(name: str, capability: str) -> list[str]:
    """Names of the settings a provider still needs for a capability (never their values)."""
    s = get_settings()
    out: list[str] = []
    if name == "anthropic":
        if not s.anthropic_api_key:
            out.append("OSRIP_ANTHROPIC_API_KEY")
        if not s.assistant_model:
            out.append("OSRIP_ASSISTANT_MODEL")
    elif name == "openai":
        if not s.openai_api_key:
            out.append("OSRIP_OPENAI_API_KEY")
        model = s.openai_model if capability == "answer" else s.openai_search_model
        if not model:
            out.append(
                "OSRIP_OPENAI_MODEL" if capability == "answer" else "OSRIP_OPENAI_SEARCH_MODEL"
            )
    elif name == "gemini":
        if not s.gemini_api_key:
            out.append("OSRIP_GEMINI_API_KEY")
        model = s.gemini_model if capability == "answer" else s.gemini_search_model
        if not model:
            out.append(
                "OSRIP_GEMINI_MODEL" if capability == "answer" else "OSRIP_GEMINI_SEARCH_MODEL"
            )
    elif name == "deepseek":
        if not s.deepseek_api_key:
            out.append("OSRIP_DEEPSEEK_API_KEY")
        if capability == "answer" and not s.deepseek_model:
            out.append("OSRIP_DEEPSEEK_MODEL")
        if not s.deepseek_billing_acknowledged:
            out.append("OSRIP_DEEPSEEK_BILLING_ACKNOWLEDGED")
    elif name == "brave":
        if not s.research_api_key:
            out.append("OSRIP_RESEARCH_API_KEY")
    elif name == "firecrawl":
        if not s.firecrawl_api_key:
            out.append("OSRIP_FIRECRAWL_API_KEY")
    return out


def model_for(name: str, capability: str) -> str | None:
    s = get_settings()
    return {
        ("anthropic", "answer"): s.assistant_model,
        ("openai", "answer"): s.openai_model,
        ("openai", "search"): s.openai_search_model,
        ("gemini", "answer"): s.gemini_model,
        ("gemini", "search"): s.gemini_search_model,
        ("deepseek", "answer"): s.deepseek_model,
        ("deepseek", "search"): "search-api",
        ("deepseek", "retrieve"): "fetch-api",
    }.get((name, capability))


def roles() -> dict[str, list[str]]:
    """Which role each provider plays: answer/search, primary/fallback."""
    s = get_settings()
    out: dict[str, list[str]] = {}
    for role, value in (
        ("answer_primary", s.assistant_provider),
        ("answer_fallback", s.assistant_fallback_provider),
        ("search_primary", s.research_provider),
        ("search_fallback", s.research_fallback_provider),
    ):
        if value:
            out.setdefault(value, []).append(role)
    if s.firecrawl_api_key:
        out.setdefault("firecrawl", []).append("retrieve_primary")
    if s.research_fetch_provider == "deepseek":
        out.setdefault("deepseek", []).append("retrieve_pages")
    return out


# ------------------------------------------------------------------ metering and limits


def estimate_cost(
    provider: str,
    input_tokens: int | None,
    output_tokens: int | None,
    searches: int | None,
    credits: int | None = None,
) -> Decimal | None:
    """Cost from the configured prices only (OSRIP_PROVIDER_PRICES); None when unknown."""
    prices = get_settings().provider_prices.get(provider)
    if not prices:
        return None
    total = Decimal(0)
    for count, key, per in (
        (input_tokens, "input_per_mtok", Decimal(1_000_000)),
        (output_tokens, "output_per_mtok", Decimal(1_000_000)),
        (searches, "per_search", Decimal(1)),
        (credits, "per_credit", Decimal(1)),
    ):
        if count and key in prices:
            total += Decimal(str(prices[key])) * Decimal(count) / per
    return total.quantize(Decimal("0.000001"))


class Meter(Protocol):
    def usage_today(self, provider: str) -> dict[str, Any]: ...

    def record(self, row: dict[str, Any]) -> None: ...

    def latest(self, provider: str) -> dict[str, Any] | None: ...


class DbMeter:
    """provider_call rows in their own short transactions (never the caller's)."""

    def _day_start(self) -> datetime:
        now = datetime.now(UTC)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def usage_today(self, provider: str) -> dict[str, Any]:
        from app.db.session import session_factory
        from app.models import ProviderCall

        with session_factory()() as session, session.begin():
            calls, cost = session.execute(
                select(
                    func.count(), func.coalesce(func.sum(ProviderCall.estimated_cost_usd), 0)
                ).where(
                    ProviderCall.provider == provider,
                    ProviderCall.created_at >= self._day_start(),
                    ProviderCall.status != "budget_exhausted",
                    ProviderCall.status != "daily_limit",
                )
            ).one()
            errors = session.scalar(
                select(func.count()).where(
                    ProviderCall.provider == provider,
                    ProviderCall.created_at >= self._day_start(),
                    ProviderCall.status != "ok",
                )
            )
        return {"calls": int(calls), "errors": int(errors or 0), "cost_usd": Decimal(cost)}

    def record(self, row: dict[str, Any]) -> None:
        from app.db.session import session_factory
        from app.models import ProviderCall

        try:
            with session_factory()() as session, session.begin():
                session.add(ProviderCall(**row))
        except Exception:  # noqa: BLE001 - metering must never break an answer
            log.exception("could not record a provider call")

    def latest(self, provider: str) -> dict[str, Any] | None:
        from app.db.session import session_factory
        from app.models import ProviderCall

        with session_factory()() as session, session.begin():
            rows = {}
            for kind, caps in (
                ("test", ("test_answer", "test_search", "test_retrieve")),
                ("call", ("answer", "search", "retrieve")),
            ):
                row = session.scalar(
                    select(ProviderCall)
                    .where(ProviderCall.provider == provider, ProviderCall.capability.in_(caps))
                    .order_by(desc(ProviderCall.created_at))
                    .limit(1)
                )
                if row is not None:
                    rows[kind] = {
                        "status": row.status,
                        "capability": row.capability,
                        "model": row.model,
                        "at": row.created_at.isoformat(),
                        "duration_ms": row.duration_ms,
                    }
        return rows or None


class MemoryMeter:
    """In-memory meter for unit tests (no database)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def usage_today(self, provider: str) -> dict[str, Any]:
        mine = [
            r for r in self.rows
            if r["provider"] == provider and r["status"] not in ("budget_exhausted", "daily_limit")
        ]  # fmt: skip
        cost = sum((r.get("estimated_cost_usd") or Decimal(0)) for r in mine)
        errors = sum(1 for r in self.rows if r["provider"] == provider and r["status"] != "ok")
        return {"calls": len(mine), "errors": errors, "cost_usd": Decimal(cost)}

    def record(self, row: dict[str, Any]) -> None:
        self.rows.append({**row, "created_at": datetime.now(UTC)})

    def latest(self, provider: str) -> dict[str, Any] | None:
        out: dict[str, Any] = {}
        for kind, caps in (
            ("test", ("test_answer", "test_search", "test_retrieve")),
            ("call", ("answer", "search", "retrieve")),
        ):
            rows = [r for r in self.rows if r["provider"] == provider and r["capability"] in caps]
            if rows:
                r = rows[-1]
                out[kind] = {
                    "status": r["status"], "capability": r["capability"], "model": r.get("model"),
                    "at": r["created_at"].isoformat(), "duration_ms": r.get("duration_ms", 0),
                }  # fmt: skip
        return out or None


# Replaced by a MemoryMeter in unit tests.
meter: Meter = DbMeter()


def calls_today(provider: str, capability: str) -> int:
    """Calls made today (UTC) for one capability of a provider (the research daily limits
    for paid search and fetch calls); 0 without the database."""
    from app.db.session import session_factory
    from app.models import ProviderCall

    if isinstance(meter, MemoryMeter):  # tests without a database
        return sum(
            1
            for r in meter.rows
            if r["provider"] == provider
            and r["capability"] == capability
            and r["status"] not in ("daily_limit", "budget_exhausted")
        )
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        with session_factory()() as session, session.begin():
            return int(
                session.scalar(
                    select(func.count()).where(
                        ProviderCall.provider == provider,
                        ProviderCall.capability == capability,
                        ProviderCall.created_at >= start,
                        ProviderCall.status.not_in(("daily_limit", "budget_exhausted")),
                    )
                )
                or 0
            )
    except Exception:  # noqa: BLE001 - nothing to count without the database
        return 0


def check(provider: str, capability: str, model: str | None) -> None:
    """Refuse a call that would pass today's request limit or budget (and record the refusal)."""
    s = get_settings()
    if provider in FAKES:
        return
    usage = meter.usage_today(provider)
    code = None
    if usage["calls"] >= s.provider_daily_call_limit:
        code = "daily_limit"
    elif (
        s.provider_daily_budget_usd is not None
        and get_settings().provider_prices.get(provider)
        and usage["cost_usd"] >= Decimal(str(s.provider_daily_budget_usd))
    ):
        code = "budget_exhausted"
    if code:
        meter.record(
            {
                "provider": provider,
                "capability": capability,
                "model": model,
                "status": code,
                "duration_ms": 0,
            }
        )
        raise LimitReached(code)


_TEST_CALL: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "osrip_provider_test", default=False
)


def record(
    provider: str,
    capability: str,
    model: str | None,
    status: str,
    started: float,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    searches: int | None = None,
    credits: int | None = None,
) -> None:
    if _TEST_CALL.get() and not capability.startswith("test_"):
        capability = f"test_{capability}"
    meter.record(
        {
            "provider": provider,
            "capability": capability,
            "model": (model or None) and str(model)[:120],
            "status": status[:40],
            "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "searches": searches,
            "credits": credits,
            "estimated_cost_usd": estimate_cost(
                provider, input_tokens, output_tokens, searches, credits
            )
            if status == "ok"
            else None,
        }
    )


# ------------------------------------------------------------------ live tests


TEST_TOOL = {
    "name": "final_answer",
    "description": "Report the result of the health check.",
    "input_schema": {
        "type": "object",
        "properties": {"status": {"type": "string"}, "text": {"type": "string"}},
        "required": ["status", "text"],
    },
}


def run_test(name: str, capability: str) -> dict[str, Any]:
    """One minimal live call (an administrator's action; it may cost a little). The outcome is
    recorded as a test call, so readiness shows "tested" only after a call really worked."""
    from app.services.assistant.provider import ProviderError, build_provider, failure_category
    from app.services.research.firecrawl import FirecrawlError
    from app.services.research.search import SearchError, build_search_provider

    if name not in CATALOG or capability not in CATALOG[name].capabilities:
        return {"provider": name, "capability": capability, "status": "unsupported"}
    if missing(name, capability):
        return {
            "provider": name,
            "capability": capability,
            "status": "not_configured",
            "missing": missing(name, capability),
        }
    token = _TEST_CALL.set(True)
    started = time.monotonic()
    detail: str | None = None
    try:
        if capability == "answer":
            provider = build_provider(name)
            if provider is None:
                return {"provider": name, "capability": capability, "status": "not_configured"}
            result = provider.complete(
                "This is a health check. Call final_answer with status 'answered' and text 'OK'.",
                [{"role": "user", "content": "Health check."}],
                [TEST_TOOL],
            )
            ok = any(b.get("type") in ("tool_use", "text") for b in result.get("content") or [])
            status = "ok" if ok else "invalid_response"
        elif capability == "retrieve":
            from app.services.research import firecrawl

            client = firecrawl.client()
            if client is None:
                return {"provider": name, "capability": capability, "status": "not_configured"}
            # One official page (robots.txt is checked first, as for every study).
            from app.services.research.robots import RobotsCache

            page = "https://www.ncsi.gov.om/"
            if not RobotsCache().allows(page):
                status = "robots_disallowed"
            else:
                client.scrape(page, max_pdf_pages=1)
                status = "ok"
        else:
            route = build_search_provider(name)
            if route is None:
                return {"provider": name, "capability": capability, "status": "not_configured"}
            query = "National Centre for Statistics and Information Oman"
            if getattr(route, "display_only", False):
                route.ground(query, language="en")
            else:
                route.search(query, language="en", count=1)
            status = "ok"
    except (ProviderError, SearchError, LimitReached, FirecrawlError) as exc:
        status = str(exc)[:40] or "failed"
        detail = getattr(exc, "detail", None)
    finally:
        _TEST_CALL.reset(token)
    return {
        "provider": name,
        "capability": capability,
        "status": status,
        # What kind of failure (authentication, model_unavailable, timeout ...) and the
        # service's own error type, never its message.
        "category": None if status == "ok" else failure_category(status, detail),
        "detail": detail,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def check_answering(name: str) -> dict[str, Any]:
    """The command line's check of one answering provider with the server's own settings
    (``python -m app.cli provider-check``): which settings are missing (names only); for
    DeepSeek, whether the configured model is among the models this key can use; then one
    minimal live call through ``run_test`` (recorded like the administrators' Test button).
    Never a key, a message text or an answer."""
    from app.services.assistant.provider import (
        DeepSeekProvider,
        ProviderError,
        build_provider,
        failure_category,
    )

    s = get_settings()
    out: dict[str, Any] = {
        "provider": name,
        "chosen": s.assistant_provider == name,
        "model": model_for(name, "answer"),
        "missing": missing(name, "answer"),
    }
    if out["missing"]:
        return {**out, "status": "not_configured", "category": "not_configured", "step": "settings"}
    provider = build_provider(name)
    if isinstance(provider, DeepSeekProvider):
        try:
            out["models"] = provider.models()
        except ProviderError as exc:
            return {
                **out, "status": str(exc), "category": failure_category(str(exc), exc.detail),
                "detail": exc.detail, "step": "models",
            }  # fmt: skip
        if out["model"] not in out["models"]:
            return {
                **out, "status": "model_not_listed", "category": "model_unavailable",
                "step": "models",
            }  # fmt: skip
    test = run_test(name, "answer")
    outcome = {k: test.get(k) for k in ("status", "category", "detail", "duration_ms")}
    return {**out, **outcome, "step": "chat"}


# ------------------------------------------------------------------ readiness


def state(name: str) -> dict[str, Any]:
    """One provider's readiness (no secret values)."""
    s = get_settings()
    spec = CATALOG[name]
    my_roles = roles().get(name, [])
    capabilities = {
        cap: {
            "missing": missing(name, cap),
            "model": model_for(name, cap),
            "chosen": any(r.startswith(cap) for r in my_roles),
        }
        for cap in spec.capabilities
    }
    configured = any(not c["missing"] for c in capabilities.values())
    # A provider in use is judged by the capabilities it is used for; another by any.
    relevant = [c for c in capabilities.values() if c["chosen"]] or list(capabilities.values())
    try:
        latest = meter.latest(name) or {}
        usage = meter.usage_today(name)
    except Exception:  # noqa: BLE001 - readiness must render without the log
        latest, usage = {}, {"calls": 0, "errors": 0, "cost_usd": Decimal(0)}
    events = [e for e in (latest.get("test"), latest.get("call")) if e]
    newest = max(events, key=lambda e: e["at"]) if events else None
    if not any(not c["missing"] for c in relevant):
        status = "unavailable"
    elif newest is None:
        status = "configured"
    elif newest["status"] == "ok":
        status = "tested"
    else:
        status = "failed"
    return {
        "provider": name,
        "label": spec.label,
        "docs": spec.docs,
        "billing": spec.billing,
        "roles": my_roles,
        "in_use": bool(my_roles),
        "capabilities": capabilities,
        "configured": configured,
        "status": status,
        "last_test": latest.get("test"),
        "last_call": latest.get("call"),
        "today": {
            "calls": usage["calls"],
            "errors": usage["errors"],
            "estimated_cost_usd": float(usage["cost_usd"]) if s.provider_prices.get(name) else None,
        },
        "limits": {
            "daily_calls": s.provider_daily_call_limit,
            "daily_budget_usd": s.provider_daily_budget_usd,
            "prices_configured": bool(s.provider_prices.get(name)),
        },
    }


def readiness() -> dict[str, Any]:
    s = get_settings()
    return {
        "providers": [state(name) for name in CATALOG],
        "routing": {
            "answer": {
                "primary": s.assistant_provider or None,
                "fallback": s.assistant_fallback_provider or None,
            },
            "search": {
                "primary": s.research_provider or None,
                "fallback": s.research_fallback_provider or None,
            },
        },
        "policy": POLICY,
    }


POLICY = {
    "en": (
        "Numerical questions start with approved OSRIP data; the web is searched only when the "
        "data are missing or the question is about recent events. One provider answers each "
        "question; a second is used only as a fallback or for a cross-check the person asks "
        "for. Agreement between two models is not independent evidence."
    ),
    "ar": (
        "تبدأ الأسئلة الرقمية ببيانات OSRIP المعتمدة، ولا يُبحث في الإنترنت إلا عند غياب "
        "البيانات أو إذا كان السؤال عن أحداث حديثة. يجيب عن كل سؤال مزوّد واحد، ولا يُستخدم "
        "مزوّد ثانٍ إلا بديلاً عند التعذّر أو للتحقق المتقاطع الذي يطلبه الشخص. اتفاق نموذجين "
        "ليس دليلاً مستقلاً."
    ),
}
