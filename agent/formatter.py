import html
from .answerer import StructuredAnswer

def _escape(text: str) -> str:
    return html.escape(text, quote=False).replace("&amp;", "&")


def to_blocks(ans: StructuredAnswer) -> list[dict]:
    blocks: list[dict] = []

    # Header
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*패턴*: {_escape(ans.pattern)}"},
    })

    # Rationale + Best for
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*이유*\n{_escape(ans.rationale)}"},
            {"type": "mrkdwn", "text": f"*적합한 상황*\n{_escape(ans.best_for)}"},
        ],
    })

    # Pros
    if ans.pros:
        pros_text = "\n".join(f"• {_escape(p)}" for p in ans.pros)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*장점*\n{pros_text}"},
        })

    # Cons
    if ans.cons:
        cons_text = "\n".join(f"• {_escape(c)}" for c in ans.cons)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*단점*\n{cons_text}"},
        })

    # Confidence + file refs
    confidence_pct = int(ans.confidence * 100)
    refs = " ".join(f"`{r}`" for r in ans.code_refs) if ans.code_refs else "_없음_"
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"신뢰도: *{confidence_pct}%*  |  파일: {refs}"},
        ],
    })

    return blocks


def to_fallback_text(ans: StructuredAnswer) -> str:
    confidence_pct = int(ans.confidence * 100)
    refs = ", ".join(ans.code_refs) if ans.code_refs else "없음"
    return (
        f"패턴: {ans.pattern}\n"
        f"이유: {ans.rationale}\n"
        f"장점: {', '.join(ans.pros)}\n"
        f"단점: {', '.join(ans.cons)}\n"
        f"적합한 상황: {ans.best_for}\n"
        f"신뢰도: {confidence_pct}%\n"
        f"파일: {refs}"
    )
