#!/usr/bin/env bash
# Hugging Face Space entrypoint: migrate, warm clones in the background, serve.
set -euo pipefail

cd /app

echo "== alembic upgrade head"
uv run --no-dev alembic upgrade head || echo "WARN: migration step failed; continuing"

echo "== background repo clone warmup"
(
  uv run --no-dev python - <<'PY' || echo "WARN: clone warmup failed"
import os
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from archaeology.config import DATABASE_URL, CLONES_DIR
from archaeology.ingest.provision import provision_clone
from archaeology.storage.models import Repo

engine = create_engine(DATABASE_URL)
with Session(engine) as session:
    rows = session.execute(select(Repo.name, Repo.url)).all()
targets = [(name, url) for name, url in rows if name.lower() != "t/js"]
for name, _url in targets:
    try:
        res = provision_clone(name, CLONES_DIR, int(os.environ.get("ARCHAEOLOGY_MAX_COMMIT_COUNT", "50000")))
        print(f"  clone ready: {name} (reused={res.reused}, {res.commit_count} commits)")
    except Exception as exc:
        print(f"  clone failed for {name}: {exc}")
PY
) &

echo "== starting uvicorn on :7860"
exec uv run --no-dev uvicorn archaeology.api.main:app --host 0.0.0.0 --port 7860
