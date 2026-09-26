from __future__ import annotations

import json
import logging
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.schemas import CopilotAnswer
from app.modules.inventory.service import expiring, low_stock, to_product_out
from app.modules.reports.service import sales_report

logger = logging.getLogger("aetherqore.ai")


def _cedi(n: object) -> str:
    return f"GH₵{float(n):,.2f}"


class AIProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class DisabledProvider:
    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("AI provider is not configured")


class OpenAICompatibleProvider:
    def complete(self, system: str, user: str) -> str:
        settings = get_settings()
        response = httpx.post(
            f"{settings.ai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            json={
                "model": settings.ai_model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=8.0,
            trust_env=False,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def get_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_enabled:
        return OpenAICompatibleProvider()
    return DisabledProvider()


def answer_question(db, question: str) -> CopilotAnswer:
    q = question.lower()
    low = low_stock(db)
    exp = expiring(db, 30)
    sales = sales_report(db, "daily")
    weekly = sales_report(db, "weekly")

    if "expir" in q:
        rows = [[b.product.name if b.product else "", b.batch_number, b.expiry_date.isoformat(), str(b.quantity)] for b in exp[:8]]
        text = f"{len(exp)} medicines expire within the next 30 days. Highest write-off risk is listed below."
        table = {"head": ["Medicine", "Batch", "Expiry", "Qty"], "rows": rows} if rows else None
        answer = CopilotAnswer(
            text=text if rows else "No batches expire in the next 30 days.",
            table=table,
            actions=["Create clearance promotion", "Export list"] if rows else [],
            followups=["Which supplier can take returns?", "Estimate the write-off value"],
            source="inventory",
            llm_used=False,
        )
    elif "reorder" in q or "low stock" in q or "stockout" in q:
        rows = [
            [p.name, str(p.quantity_on_hand), str(p.reorder_threshold), str(max(p.reorder_threshold * 2 - p.quantity_on_hand, p.reorder_threshold))]
            for p in low[:8]
        ]
        answer = CopilotAnswer(
            text=f"{len(low)} medicines are at or below reorder point." if low else "All medicines are above their reorder points.",
            table={"head": ["Medicine", "In stock", "Reorder", "Suggested"], "rows": rows} if rows else None,
            actions=["Draft purchase orders"] if rows else [],
            followups=["Group by supplier", "Which supplier is cheapest?"],
            source="inventory",
        )
    elif "revenue" in q or "today" in q or "sales" in q:
        answer = CopilotAnswer(
            text=(
                f"Today's revenue is {_cedi(sales['revenue'])} across {sales['transactions']} transactions. "
                f"This week totals {_cedi(weekly['revenue'])}."
            ),
            actions=["Open full report"],
            followups=["Top selling medicines", "Which medicines should be reordered?"],
            source="sales",
        )
    elif "supplier" in q:
        answer = CopilotAnswer(
            text="Open Suppliers for on-time rates and outstanding balances. Shift volume away from any supplier marked Needs review.",
            actions=["Open suppliers"],
            followups=["Which medicines should be reordered?"],
            source="suppliers",
        )
    else:
        names = ", ".join(p.name for p in low[:3]) or "none"
        answer = CopilotAnswer(
            text=(
                f"I can answer from live inventory and sales. "
                f"Low stock right now: {names}. Ask about expiry, reorders, or today's revenue."
            ),
            followups=["Show medicines expiring next month", "Which medicines should be reordered?", "How much revenue did we make today?"],
            source="general",
        )

    settings = get_settings()
    if settings.ai_enabled:
        try:
            context = json.dumps(
                {
                    "low_stock": [to_product_out(p, db).model_dump(mode="json") for p in low[:12]],
                    "expiring": [
                        {"name": b.product.name if b.product else "", "batch": b.batch_number, "expiry": str(b.expiry_date), "qty": b.quantity}
                        for b in exp[:12]
                    ],
                    "today": sales,
                },
                default=str,
            )
            prose = get_provider().complete(
                "You are AetherQore Copilot. Use only the provided JSON. Do not invent stock numbers. All money is Ghanaian cedis (GHS / GH₵). Never use dollars or $. Keep the answer under 120 words.",
                f"Question: {question}\nData: {context}",
            )
            answer.text = prose
            answer.source = "ai+data"
            answer.llm_used = True
        except Exception:
            logger.warning("cloud AI request failed; using local pharmacy data", exc_info=True)
            answer.llm_used = False
    return answer
