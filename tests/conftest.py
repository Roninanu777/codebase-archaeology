from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pygit2
import pytest

_AUTHOR = pygit2.Signature("Test Author", "author@example.com", 1700000000, 0)

INITIAL_APP = (
    "import os\n\ndef add(a, b):\n    # sums two numbers\n    result = a + b\n    return result\n"
)
WHITESPACE_APP = (
    "import os\n\ndef add(a, b):\n\t# sums two numbers\n\tresult = a + b\n\treturn result   \n"
)
COMMENT_APP = (
    "import os\n\ndef add(a, b):\n\t# sums two numbers\n\tresult = a + b\n\treturn result   \n"
    "# NOTE: added later\n"
)
CHANGED_APP = COMMENT_APP.replace("result = a + b\n", "result = a + b + 1\n")
RENAMED_APP = CHANGED_APP


class SyntheticRepo:
    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.repo = pygit2.init_repository(str(workdir))
        self.shas: list[str] = []

    def commit(self, message: str, files: dict[str, str | None]) -> str:
        for rel, content in files.items():
            target = self.workdir / rel
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
        index = self.repo.index
        index.add_all()
        tree = index.write_tree()
        parents: list[pygit2.Oid] = []
        if not self.repo.head_is_unborn:
            parents.append(pygit2.Oid(hex=str(self.repo.head.target)))
        else:
            self.repo.set_head("refs/heads/main")
        sha = str(
            self.repo.create_commit("refs/heads/main", _AUTHOR, _AUTHOR, message, tree, parents)
        )
        index.write()
        self.shas.append(sha)
        return sha


@pytest.fixture()
def synthetic_repo(tmp_path: Path) -> Generator[SyntheticRepo, None, None]:
    built = SyntheticRepo(tmp_path / "repo")
    built.commit("initial app", {"app.py": INITIAL_APP})
    built.commit("reindent only", {"app.py": WHITESPACE_APP})
    built.commit("add comment", {"app.py": COMMENT_APP})
    built.commit("change logic", {"app.py": CHANGED_APP})
    built.commit("rename app to calc", {"app.py": None, "calc.py": RENAMED_APP})
    yield built
