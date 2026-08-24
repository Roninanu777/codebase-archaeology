from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from archaeology.storage.models import Trace


def trace_call(
    session: Session,
    *,
    stage: str,
    model: str | None,
    prompt: str,
    response: str | None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    eval_case_id: str | None = None,
    repo_id: int | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Trace:
    row = Trace(
        stage=stage,
        model=model,
        prompt=prompt,
        response=response,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        eval_case_id=eval_case_id,
        repo_id=repo_id,
        extra=dict(extra) if extra is not None else None,
    )
    session.add(row)
    return row
