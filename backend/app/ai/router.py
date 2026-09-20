from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.copilot import answer_question
from app.ai.safety import sanitize_question
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.permissions import require_permission
from app.core.responses import ValidationAppError
from app.core.schemas import CopilotAnswer, CopilotAsk
from app.models import User

router = APIRouter(prefix="/copilot", tags=["ai"])


@router.get("/status")
def copilot_status(_: User = Depends(get_current_user)):
    settings = get_settings()
    return {
        "ai_enabled": settings.ai_enabled,
        "mode": "llm" if settings.ai_enabled else "local-data",
        "message": (
            "Cloud AI is configured. Answers may be summarized by the model using live pharmacy data."
            if settings.ai_enabled
            else "Cloud AI is not configured. The copilot answers from this computer's inventory and sales only."
        ),
    }


@router.post("/ask", response_model=CopilotAnswer)
def copilot(body: CopilotAsk, db: Session = Depends(get_db), _: User = Depends(require_permission("ai.use"))):
    try:
        question = sanitize_question(body.question)
    except ValueError as exc:
        raise ValidationAppError(str(exc)) from exc
    return answer_question(db, question)
