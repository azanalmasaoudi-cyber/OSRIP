"""Generated illustrations: original pictures, infographic-style visuals and concept images that
a signed-in person asks the assistant for (migration 0029).

* Off unless ``OSRIP_IMAGES_PROVIDER`` names a provider: ``openai`` (the Images API with
  ``gpt-image-2.5-flare``, or ``gpt-image-2.5-sunburst`` for detailed work; billed per image) or
  ``fake`` (a drawn stand-in, outside production, for tests).
* Never statistics: every image is labelled as an AI illustration, and the prompt asks for no
  figures, charts or text. Statistical charts come only from validated figures
  (assistant/web_analysis.py, datatable.py).
* Bounded cost: two images per answer at most, ``images_daily_limit_per_user`` per person per
  day, and the providers' shared daily limits and budget (providers.check), with each call
  metered (capability ``image``). Guests cannot have images made.
* Stored for their owner only (generated_image); served by GET /assistant/images/{id}.
"""

from __future__ import annotations

import base64
import io
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import session_factory
from app.models import GeneratedImage
from app.services import providers as registry

log = logging.getLogger("osrip.images")

PURPOSES = ("illustration", "infographic", "concept", "diagram_art")
MAX_PER_ANSWER = 2
# What every request asks for, before the person's description.
STYLE = {
    "illustration": "An original, tasteful editorial illustration.",
    "infographic": "An original infographic-style visual with icons and shapes only.",
    "concept": "An original concept image.",
    "diagram_art": "A clean, original explanatory illustration with simple shapes.",
}
GUARD = (
    "Do not draw numbers, statistics, charts, maps with figures, logos, flags of organisations or "
    "readable text. Subject:"
)


class Generator(Protocol):
    name: str

    def generate(self, prompt: str, model: str, size: str) -> tuple[bytes, str]: ...


class OpenAIImages:
    """The OpenAI Images API (POST /v1/images/generations) through the official SDK."""

    name = "openai"

    def __init__(self, api_key: str, timeout: float) -> None:
        self._key = api_key
        self._timeout = timeout

    def generate(self, prompt: str, model: str, size: str) -> tuple[bytes, str]:
        from app.services import openai_api

        with httpx.Client(timeout=self._timeout) as http:
            result = openai_api.client(self._key, http, self._timeout).images.generate(
                model=model,
                prompt=prompt,
                size=size,
                n=1,  # type: ignore[arg-type]
            )
        first = (result.data or [None])[0]
        encoded = getattr(first, "b64_json", None)
        if not encoded:
            raise RuntimeError("the image service returned no image")
        return base64.b64decode(encoded), "image/png"


class FakeImages:
    """A drawn stand-in for tests and demonstrations (never in production): a warm gradient."""

    name = "fake"

    def generate(self, prompt: str, model: str, size: str) -> tuple[bytes, str]:
        from PIL import Image

        width, height = 256, 160
        image = Image.new("RGB", (width, height))
        pixels = image.load()
        for x in range(width):
            for y in range(height):
                pixels[x, y] = (242 - y // 4, 168 - x // 6 + y // 8, 117 + x // 5)  # type: ignore[index]
        out = io.BytesIO()
        image.save(out, "PNG")
        return out.getvalue(), "image/png"


def generator() -> Generator | None:
    s = get_settings()
    if s.images_provider == "fake" and s.environment != "production":
        return FakeImages()
    if s.images_provider == "openai" and s.openai_api_key:
        return OpenAIImages(
            s.openai_api_key.get_secret_value(), max(60.0, s.openai_timeout_seconds)
        )
    return None


def available() -> bool:
    """Whether illustrations can be made on this server."""
    return generator() is not None


def used_today(user_id: uuid.UUID) -> int:
    since = datetime.now(UTC) - timedelta(days=1)
    with session_factory()() as s, s.begin():
        return int(
            s.scalar(
                select(func.count())
                .select_from(GeneratedImage)
                .where(GeneratedImage.user_id == user_id, GeneratedImage.created_at >= since)
            )
            or 0
        )


def _refuse(message: str) -> dict[str, Any]:
    return {"status": "refused", "message": message}


def generate_for_answer(ledger: Any, prompt: str, purpose: str, quality: str) -> dict[str, Any]:
    """Make one illustration for this answer and store it for its owner (outside the answer's
    read-only transaction, in its own short one)."""
    s = get_settings()
    owner = ledger.image_owner
    if owner is None:
        return _refuse("Illustrations are made only for signed-in users. Say so.")
    maker = generator()
    if maker is None:
        return _refuse(
            "No image service is configured here. Say so; never describe an image as made."
        )
    if len(ledger.images) >= MAX_PER_ANSWER:
        return _refuse("Two illustrations is the most for one answer.")
    if used_today(owner) >= s.images_daily_limit_per_user:
        return _refuse("Today's limit of illustrations for this person is reached. Say so.")
    text = " ".join(str(prompt).split())[:3000]
    if not text:
        return _refuse("Describe the picture.")
    purpose = purpose if purpose in PURPOSES else "illustration"
    model = s.images_detailed_model if quality == "detailed" else s.images_model
    if maker.name != "fake":
        try:
            registry.check(maker.name, "image", model)
        except registry.LimitReached as exc:
            return _refuse(f"The image service's daily limit or budget is reached ({exc}). Say so.")
    started = time.monotonic()
    try:
        data, mime = maker.generate(f"{STYLE[purpose]} {GUARD} {text}", model, s.images_size)
    except Exception as exc:  # noqa: BLE001 - any provider failure is reported, never invented around
        log.warning(
            "image generation failed provider=%s model=%s error=%s",
            maker.name,
            model,
            type(exc).__name__,
        )
        registry.record(maker.name, "image", model, "failed", started)
        return _refuse("The image service did not make the picture. Say so; do not describe one.")
    registry.record(maker.name, "image", model, "ok", started)
    with session_factory()() as session, session.begin():
        row = GeneratedImage(
            user_id=owner,
            prompt=text,
            purpose=purpose,
            provider=maker.name,
            model=model,
            mime=mime,
            data=data,
        )
        session.add(row)
        session.flush()
        image_id = str(row.id)
    ledger.images.append({"id": image_id, "purpose": purpose, "model": model, "prompt": text[:300]})
    return {
        "status": "ok",
        "image_id": image_id,
        "message": "Made. It is shown under your reply, labelled as an AI illustration (not data).",
    }


def get_for_user(image_id: uuid.UUID, user_id: uuid.UUID) -> GeneratedImage | None:
    """The stored image, for its owner only."""
    with session_factory()() as s, s.begin():
        row = s.get(GeneratedImage, image_id)
        if row is None or row.user_id != user_id:
            return None
        s.expunge(row)
        return row
