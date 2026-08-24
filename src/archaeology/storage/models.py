from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from archaeology.storage.base import Base


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stage: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column()
    prompt_tokens: Mapped[int | None] = mapped_column()
    completion_tokens: Mapped[int | None] = mapped_column()
    eval_case_id: Mapped[str | None] = mapped_column(Text)
    repo_id: Mapped[int | None] = mapped_column()
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
