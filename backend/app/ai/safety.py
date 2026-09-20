MAX_QUESTION_CHARS = 2000


def sanitize_question(question: str) -> str:
    text = (question or "").strip()
    if not text:
        raise ValueError("Question is required")
    if len(text) > MAX_QUESTION_CHARS:
        raise ValueError("Question is too long")
    return text
