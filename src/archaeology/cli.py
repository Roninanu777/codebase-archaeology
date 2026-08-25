from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from archaeology.classify.backfill import backfill_ast_features
from archaeology.config import DATABASE_URL
from archaeology.ingest.git import ingest_repository
from archaeology.routes.path_a import PathAResult, why_symbol
from archaeology.storage.models import CommitSignificance, Repo


def _cmd_ingest(args: argparse.Namespace) -> int:
    engine = create_engine(args.database_url or DATABASE_URL)
    stats = ingest_repository(engine, args.path, name=args.name, url=args.url)
    if stats.skipped:
        print(f"{args.name}: already indexed through HEAD ({stats.duration_s:.1f}s)")
    else:
        total_commits = max(sum(stats.label_counts.values()), 1)
        print(
            f"{args.name}: {stats.commits} commits, "
            f"{stats.file_changes} file changes in {stats.duration_s:.1f}s"
        )
        for label, count in sorted(stats.label_counts.items(), key=lambda kv: -kv[1]):
            print(f"  {label:<28} {count:>7}  ({count / total_commits:.1%})")
    with Session(engine) as session:
        repo_row = session.scalars(select(Repo).where(Repo.name == args.name)).first()
        rows = session.scalar(select(func.count()).select_from(CommitSignificance))
        head = repo_row.head_sha if repo_row else None
    print(f"head={head} significance_rows={rows}")
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    engine = create_engine(args.database_url or DATABASE_URL)
    stats = backfill_ast_features(
        engine,
        args.name,
        force=args.force,
        limit=args.limit,
    )
    print(
        f"{args.name}: classified {stats.processed} commits "
        f"({stats.relabeled} relabeled) in {stats.duration_s:.1f}s"
    )
    for label, count in sorted(stats.label_counts.items(), key=lambda kv: -kv[1]):
        total = max(sum(stats.label_counts.values()), 1)
        print(f"  {label:<28} {count:>7}  ({count / total:.1%})")
    return 0


def _render_why(result: PathAResult) -> None:
    if result.status == "abstained":
        print(f"ABSTAINED ({result.reason}): no reliable answer for '{result.symbol}'")
        return

    span = result.span
    assert span is not None
    print(f"{result.symbol} @ {result.rel_path}:{span.start_line}-{span.end_line} ({span.kind})")

    for ev in result.timeline:
        prs = f" #{','.join(str(r) for r in ev.pr_refs)}" if ev.pr_refs else ""
        date = f" {ev.committed_at}" if ev.committed_at else ""
        author = f" {ev.author}" if ev.author else ""
        marker = "*" if ev.role == "introduced" else "-"
        print(f"  {marker} {ev.sha}{date}{author}{prs}  {ev.subject}")

    cache = "hit" if result.cache_hit else "miss"
    print(f"noise dropped (floor): {result.noise_dropped} commit(s); cache={cache}")
    if result.status == "low_confidence":
        print(f"LOW CONFIDENCE ({result.reason}): evidence is thin; treat as partial")


def _cmd_why(args: argparse.Namespace) -> int:
    engine = create_engine(args.database_url or DATABASE_URL)
    result = why_symbol(
        engine,
        args.name,
        args.symbol,
        rel_path=args.file,
        repo_path_override=args.repo_path,
    )
    _render_why(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archaeology")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ingest = subparsers.add_parser("ingest", help="tier-1 git ingest of a local clone")
    p_ingest.add_argument("path", help="path to a git working tree")
    p_ingest.add_argument("--name", required=True, help="canonical name, e.g. facebook/react")
    p_ingest.add_argument("--url", default=None, help="remote URL to record")
    p_ingest.add_argument("--database-url", default=None, help="override DATABASE URL")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_why = subparsers.add_parser("why", help="symbol-anchored history question (Path A)")
    p_why.add_argument("name", help="repo name as ingested, e.g. facebook/react")
    p_why.add_argument("symbol", help="function/class/const name to trace")
    p_why.add_argument("--file", default=None, help="limit resolution to this file (faster)")
    p_why.add_argument("--repo-path", default=None, help="local clone path override")
    p_why.add_argument("--database-url", default=None, help="override DATABASE URL")
    p_why.set_defaults(func=_cmd_why)

    p_cls = subparsers.add_parser(
        "classify", help="apply the AST significance layer to an ingested repo"
    )
    p_cls.add_argument("--name", required=True, help="repo name as ingested")
    p_cls.add_argument("--force", action="store_true", help="recompute already-classified commits")
    p_cls.add_argument("--limit", type=int, default=None, help="cap number of commits")
    p_cls.add_argument("--database-url", default=None, help="override DATABASE URL")
    p_cls.set_defaults(func=_cmd_classify)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
