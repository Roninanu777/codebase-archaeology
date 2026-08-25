from __future__ import annotations

from pathlib import Path

import pygit2
import pytest

from archaeology.classify.features import extract_features, make_diff
from archaeology.classify.labels import (
    INSIGNIFICANT_COMMENT,
    INSIGNIFICANT_WHITESPACE,
    SIGNIFICANT,
    label_from_features,
)
from tests.conftest import SyntheticRepo


@pytest.mark.parametrize(
    ("commit_index", "expected"),
    [
        (0, SIGNIFICANT),
        (1, INSIGNIFICANT_WHITESPACE),
        (2, INSIGNIFICANT_COMMENT),
        (3, SIGNIFICANT),
        (4, SIGNIFICANT),
    ],
)
def test_floor_labels(synthetic_repo: SyntheticRepo, commit_index: int, expected: str) -> None:
    repo = synthetic_repo.repo
    commit = repo[synthetic_repo.shas[commit_index]]
    diff = make_diff(repo, commit)
    features = extract_features(diff)
    assert label_from_features(features) == expected


def test_rename_recorded(synthetic_repo: SyntheticRepo) -> None:
    repo = synthetic_repo.repo
    rename_commit = repo[synthetic_repo.shas[4]]
    features = extract_features(make_diff(repo, rename_commit))
    assert features.renamed_files == 1
    assert features.pure_rename is True
    renamed_file = next(f for f in features.per_file if f.status == "renamed")
    assert renamed_file.path == "calc.py"
    assert renamed_file.old_path == "app.py"


def test_whitespace_commit_feature_flags(synthetic_repo: SyntheticRepo) -> None:
    repo = synthetic_repo.repo
    ws_commit = repo[synthetic_repo.shas[1]]
    features = extract_features(make_diff(repo, ws_commit))
    assert features.whitespace_only is True
    assert features.comment_only is False
    assert features.additions == features.deletions


def test_comment_commit_ignores_markdown_headings(tmp_path: Path) -> None:
    builder_repo = pygit2.init_repository(str(tmp_path))
    author = pygit2.Signature("T", "t@example.com", 1700000000, 0)
    readme_v1 = tmp_path / "README.md"
    readme_v1.write_text("# Title\n\nbody text here\n")
    builder_repo.index.add_all()
    tree = builder_repo.index.write_tree()
    first_sha = str(builder_repo.create_commit("refs/heads/main", author, author, "docs", tree, []))
    readme_v1.write_text("# Renamed Title\n\nbody text here\n")
    builder_repo.index.add_all()
    tree2 = builder_repo.index.write_tree()
    first_commit = builder_repo.get(first_sha)
    assert first_commit is not None
    second_sha = str(
        builder_repo.create_commit(
            "refs/heads/main", author, author, "heading edit", tree2, [first_commit.id]
        )
    )
    second_commit = builder_repo.get(second_sha)
    assert second_commit is not None
    features = extract_features(make_diff(builder_repo, second_commit))
    assert label_from_features(features) == SIGNIFICANT
