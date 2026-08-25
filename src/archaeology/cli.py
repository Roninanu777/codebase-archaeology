from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from archaeology.config import DATABASE_URL
from archaeology.ingest.git import ingest_repository
from archaeology.storage.models import CommitSignificance, Repo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archaeology")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ingest = subparsers.add_parser("ingest", help="tier-1 git ingest of a local clone")
    p_ingest.add_argument("path", help="path to a git working tree")
    p_ingest.add_argument("--name", required=True, help="canonical name, e.g. facebook/react")
    p_ingest.add_argument("--url", default=None, help="remote URL to record")
    p_ingest.add_argument("--database-url", default=None, help="override DATABASE_URL")

    args = parser.parse_args(argv)

    if args.command == "ingest":
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


if __name__ == "__main__":
    sys.exit(main())
