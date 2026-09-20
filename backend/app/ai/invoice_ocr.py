from __future__ import annotations

import json
import logging
from typing import Any

from app.ai.copilot import get_provider
from app.core.config import get_settings

logger = logging.getLogger("aetherqore.ocr")


def extract_invoice_with_model(text: str) -> list[dict[str, Any]]:
    if not get_settings().ai_enabled:
        return []
    try:
        provider = get_provider()
        raw = provider.complete(
            "Extract invoice line items as JSON array with keys: name, quantity, unit_cost, batch, expiry. "
            "Expiry must be YYYY-MM-DD with a four-digit year (e.g. 2027-09-16), never 0027 or 27. No markdown.",
            text,
        )
    except Exception:
        logger.warning("invoice OCR provider failed", exc_info=True)
        return []
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invoice OCR returned invalid JSON")
        return []
    if isinstance(data, dict):
        data = data.get("items", [])
    return data if isinstance(data, list) else []
