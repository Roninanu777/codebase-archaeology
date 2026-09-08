import os
from pathlib import Path

DATABASE_URL: str = os.environ.get(
    "ARCHAEOLOGY_DATABASE_URL",
    "postgresql+psycopg://archaeology:archaeology@localhost:5433/archaeology",
)

CLONES_DIR: Path = Path(os.environ.get("ARCHAEOLOGY_CLONES_DIR", "../.scratch/")).resolve()

MAX_COMMIT_COUNT: int = int(os.environ.get("ARCHAEOLOGY_MAX_COMMIT_COUNT", "50000"))
