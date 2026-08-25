from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from archaeology.classify.backfill import backfill_ast_features
from archaeology.config import DATABASE_URL
from archaeology.ingest.git import ingest_repository
from archaeology.ingest.tier2 import backfill_pull_requests
from archaeology.retrieval.embed import Embedder, embed_repo
from archaeology.retrieval.search import hybrid_search
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


def _cmd_embed(args: argparse.Namespace) -> int:
    engine = create_engine(args.database_url or DATABASE_URL)
    stats = embed_repo(engine, args.name, limit=args.limit, force=args.force)
    print(
        f"{args.name}: embedded {stats.chunks} chunks "
        f"({stats.skipped_existing} skipped) in {stats.duration_s:.1f}s [{stats.model}]"
    )
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    engine = create_engine(args.database_url or DATABASE_URL)
    result = hybrid_search(engine, Embedder(), args.name, args.query, top_n=args.n)
    if result.abstained_reason == "no_hits":
        print("ABSTAINED (no_hits): nothing in the index matches this question")
        return 0
    for rank, hit in enumerate(result.hits, start=1):
        stale = " [STALE]" if hit.stale else ""
        date = f" {hit.authored_at}" if hit.authored_at else ""
        liveness = f"{(hit.liveness_score or 0.0):.0%}"
        ranks = f"d{hit.dense_rank}/s{hit.sparse_rank}"
        print(f" {rank:>2}. {hit.sha}{date}{stale} liveness={liveness:<4} {ranks}  {hit.title}")
    if result.abstained_reason == "all_stale":
        print("NOTE (all_stale): every retrieved discussion concerns code largely absent at HEAD")
    return 0


def _cmd_backfill_prs(args: argparse.Namespace) -> int:
    engine = create_engine(args.database_url or DATABASE_URL)
    stats = backfill_pull_requests(engine, args.name, max_pages=args.max_pages)
    if stats.complete:
        print(f"{args.name}: tier-2 backfill complete")
    else:
        print(f"{args.name}: tier-2 backfill paused (resume with the same command)")
    print(
        f"  pages={stats.pages} fetched={stats.fetched} new={stats.stored_new} "
        f"rate_left={stats.rate_remaining} in {stats.duration_s:.1f}s"
    )
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

    p_emb = subparsers.add_parser("embed", help="chunk + embed commit messages (Path B)")
    p_emb.add_argument("--name", required=True)
    p_emb.add_argument("--limit", type=int, default=None)
    p_emb.add_argument("--force", action="store_true")
    p_emb.add_argument("--database-url", default=None)
    p_emb.set_defaults(func=_cmd_embed)

    p_ask = subparsers.add_parser("ask", help="hybrid retrieval over the chunk corpus")
    p_ask.add_argument("name")
    p_ask.add_argument("query", help="natural-language question")
    p_ask.add_argument("-n", type=int, default=10)
    p_ask.add_argument("--database-url", default=None)
    p_ask.set_defaults(func=_cmd_ask)

    p_prs = subparsers.add_parser(
        "backfill-prs", help="tier-2: fetch merged PRs + discussions via GitHub GraphQL"
    )
    p_prs.add_argument("--name", required=True, help="repo name as ingested, owner/name")
    p_prs.add_argument("--max-pages", type=int, default=None)
    p_prs.add_argument("--database-url", default=None)
    p_prs.set_defaults(func=_cmd_backfill_prs)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
