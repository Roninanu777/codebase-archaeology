from __future__ import annotations

import os
from typing import Any

RERANKER_MODEL_DEFAULT = "BAAI/bge-reranker-base"


def _model_name() -> str:
    return os.environ.get("ARCHAEOLOGY_RERANKER_MODEL", RERANKER_MODEL_DEFAULT)


class Reranker:
    def __init__(self, model_name: str | None = None) -> None:
        self._model: Any = None
        self.model_name = model_name or _model_name()

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            try:
                self._model = CrossEncoder(self.model_name, device="mps")
            except Exception:
                self._model = CrossEncoder(self.model_name, device="cpu")
        return self._model

    def scores(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        model = self._load()
        pairs = [(query, text) for text in texts]
        raw = model.predict(pairs, show_progress_bar=False)
        return [float(s) for s in raw]


def rerank_order(
    query: str,
    texts_by_id: dict[int, str],
    reranker: Reranker | None = None,
) -> list[tuple[int, float]]:
    """Return (id, score) sorted best-first. Unscorable ids keep original trailing order."""
    reranker = reranker or Reranker()
    ids = list(texts_by_id.keys())
    scored = reranker.scores(query, [texts_by_id[i] for i in ids])
    pairs = list(zip(ids, scored, strict=True))
    pairs.sort(key=lambda p: -p[1])
    return pairs
