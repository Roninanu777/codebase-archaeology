from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
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


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    url: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(Text)
    head_sha: Mapped[str | None] = mapped_column(Text)
    indexed_through_sha: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (Index("ix_commits_repo_committed", "repo_id", "committed_at"),)

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    sha: Mapped[str] = mapped_column(Text, primary_key=True)
    author_name: Mapped[str | None] = mapped_column(Text)
    author_email: Mapped[str | None] = mapped_column(Text)
    authored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committer_name: Mapped[str | None] = mapped_column(Text)
    committer_email: Mapped[str | None] = mapped_column(Text)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)


class CommitParent(Base):
    __tablename__ = "commit_parents"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    child_sha: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_sha: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[int] = mapped_column()


class FileChange(Base):
    __tablename__ = "file_changes"
    __table_args__ = (Index("ix_file_changes_repo_path", "repo_id", "path"),)

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    sha: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    old_path: Mapped[str | None] = mapped_column(Text)
    additions: Mapped[int | None] = mapped_column()
    deletions: Mapped[int | None] = mapped_column()


class CommitFeature(Base):
    __tablename__ = "commit_features"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    sha: Mapped[str] = mapped_column(Text, primary_key=True)
    files_changed: Mapped[int | None] = mapped_column()
    additions: Mapped[int | None] = mapped_column()
    deletions: Mapped[int | None] = mapped_column()
    binary_files: Mapped[int | None] = mapped_column()
    renamed_files: Mapped[int | None] = mapped_column()
    whitespace_only: Mapped[bool | None] = mapped_column()
    comment_only: Mapped[bool | None] = mapped_column()
    pure_rename: Mapped[bool | None] = mapped_column()
    extractor_version: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CommitSignificance(Base):
    __tablename__ = "commit_significance"
    __table_args__ = (Index("ix_significance_repo_label", "repo_id", "label"),)

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    sha: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(Text)


class LineageCache(Base):
    __tablename__ = "lineage_cache"

    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), primary_key=True)
    file: Mapped[str] = mapped_column(Text, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    head_sha: Mapped[str] = mapped_column(Text, primary_key=True)
    commit_shas: Mapped[list[Any] | None] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("run_key", name="uq_jobs_run_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(Text, default="pending")
    run_key: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
