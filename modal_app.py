"""Modal deployment adapter.

Serves the existing FastAPI app (REST + MCP) as an ASGI app, using the
verified Dockerfile as the image so the runtime is identical to local and to
the container smoke tests: uv venv, models baked in, HF offline envs.

Deploy:  uv run modal deploy modal_app.py
Secret:  uvx modal secret create archaeology-secrets KEY=value ...
"""

from __future__ import annotations

import subprocess
import threading

import modal

APP_NAME = "codebase-archaeology"
SECRET_NAME = "archaeology-secrets"

image = modal.Image.from_dockerfile("Dockerfile").env(
    {
        # MCP over a public host: Modal's proxied Host does not match an
        # allowlist entry, and the MCP tools are read-only over public data.
        "ARCHAEOLOGY_MCP_DNS_REBINDING": "0",
    }
)

volume = modal.Volume.from_name("archaeology-data", create_if_missing=True)

app = modal.App(APP_NAME)


def _warmup() -> None:
    """Migrate, then fetch missing repos in the background (idempotent)."""
    import os

    print(
        "startup env: "
        f"mcp_dns_rebinding={os.environ.get('ARCHAEOLOGY_MCP_DNS_REBINDING')!r} "
        f"halvec={os.environ.get('ARCHAEOLOGY_HALFVEC')!r} "
        f"db_set={bool(os.environ.get('ARCHAEOLOGY_DATABASE_URL'))}"
    )
    try:
        subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd="/app",
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"migration step failed (continuing): {exc}")

    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from archaeology.config import CLONES_DIR, DATABASE_URL
        from archaeology.ingest.provision import provision_clone
        from archaeology.storage.models import Repo

        engine = create_engine(DATABASE_URL)
        with Session(engine) as session:
            rows = session.execute(select(Repo.name)).all()
        names = [name for (name,) in rows if name.lower() != "t/js"]

        def clone_all() -> None:
            from archaeology.storage.models import Repo

            for name in names:
                try:
                    result = provision_clone(name, CLONES_DIR)
                    with Session(engine) as session:
                        row = session.scalars(select(Repo).where(Repo.name == name)).first()
                        if row is not None and row.local_path != str(result.path):
                            row.local_path = str(result.path)
                            session.commit()
                    print(f"clone ready: {name} ({result.commit_count} commits)")
                except Exception as exc:  # noqa: BLE001
                    print(f"clone failed for {name}: {exc}")
            volume.commit()

        threading.Thread(target=clone_all, daemon=True, name="clone-warmup").start()
    except Exception as exc:  # noqa: BLE001
        print(f"clone warmup failed (continuing): {exc}")


@app.cls(
    image=image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    cpu=2.0,
    memory=4096,
    timeout=600,
    scaledown_window=900,
    max_containers=1,
)
class Web:
    @modal.enter()
    def start(self) -> None:
        _warmup()

    @modal.asgi_app()
    def fastapi_app(self):  # type: ignore[no-untyped-def]
        from archaeology.api.main import create_app

        return create_app()
