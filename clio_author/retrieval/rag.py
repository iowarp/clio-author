# Clean-room re-implementation. The phagocyte ingestor's retrieval processor
# (LanceDB vector store with Qwen3 / OpenCLIP / bge embeddings),
# https://github.com/iowarp/phagocyte, was consulted as a *behavior* reference
# only -- no source was copied. The embed -> vector -> cosine shape here is
# generic public-API usage.
"""Retrieval over :class:`~clio_author.ingest.blocks.MemoryBlocks`.

Each :class:`~clio_author.ingest.blocks.Block` is embedded as one vector (from
its ``to_context("full")`` rendering) and ranked against a query by cosine
similarity. The hermetic default :class:`HashingEmbedder` (hashed
term-frequency, L2-normalized) is pure stdlib -- no numpy, no network -- so
rankings are deterministic and the :class:`RagRetriever` code path is identical
hermetic vs. live.

Granularity is one vector per block; sub-chunking long sections is deferred.

The optional :class:`SentenceTransformerEmbedder` / :class:`LanceDbRetriever`
backend lives behind the ``rag`` extra. Every heavy import (``lancedb``,
``sentence_transformers``, ``numpy``) is performed lazily *inside* a method, so
importing this module is always cheap and hermetic.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from clio_author.ingest.blocks import Block, BlockKind, Detail, MemoryBlocks

if TYPE_CHECKING:  # pragma: no cover - typing only, no heavy import at runtime
    pass

# Default dimensionality for the hashing embedder's term-frequency vectors.
_HASH_DIM = 256

_TOKEN_RE = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class RetrievalDependencyError(RuntimeError):
    """A required optional retrieval dependency is missing.

    The ``rag`` extra installs the heavy backend::

        uv sync --extra rag

    (``sentence-transformers`` additionally downloads model weights on first use.)
    """


# --------------------------------------------------------------------------- #
# Embedders
# --------------------------------------------------------------------------- #
@runtime_checkable
class Embedder(Protocol):
    """Maps texts to dense vectors of a fixed dimensionality."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


def _tokenize(text: str) -> list[str]:
    """Lowercase and split ``text`` into alphanumeric tokens."""
    return _TOKEN_RE.findall(text.lower())


class HashingEmbedder:
    """Deterministic hashed term-frequency embedder (pure stdlib).

    Tokens are lowercased, hashed into a fixed-dimension bucket, accumulated as
    term frequencies, then the vector is L2-normalized. No numpy, no network,
    fully reproducible -- the hermetic default.

    Matching is purely lexical (shared surface tokens); a query sharing no
    tokens with a block scores 0.0, so synonym/semantic matching requires the
    live :class:`SentenceTransformerEmbedder` backend.
    """

    def __init__(self, dim: int = _HASH_DIM) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _tokenize(text):
            # Stable, process-independent, well-distributed bucket (avoids
            # PYTHONHASHSEED dependence and the heavy collisions a raw byte-int
            # would give short tokens).
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "little") % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0.0:
            vector = [value / norm for value in vector]
        return vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized hashed term-frequency vector per text."""
        return [self._embed_one(text) for text in texts]


class SentenceTransformerEmbedder:
    """Real dense embeddings via ``sentence-transformers`` (``rag`` extra).

    Lazy-imports ``sentence_transformers`` inside :meth:`embed` so importing
    this module stays hermetic. Never exercised by the default test suite.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: object | None = None

    def _load(self) -> object:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - only without the extra
                raise RetrievalDependencyError(
                    "sentence-transformers is required for SentenceTransformerEmbedder. "
                    "Install with: uv sync --extra rag (downloads model weights on first use)."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return normalized embeddings for ``texts`` via the loaded model."""
        model = self._load()
        vectors = model.encode(  # type: ignore[attr-defined]
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return [list(map(float, row)) for row in vectors]


# --------------------------------------------------------------------------- #
# Scored results
# --------------------------------------------------------------------------- #
class ScoredBlock(BaseModel):
    """A retrieved :class:`Block` paired with its similarity ``score``.

    The polymorphic ``block`` is held in memory but is **not** serialized;
    :meth:`to_dict` emits only the JSON-safe ``{block_id, kind, score}``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    block: Block
    score: float

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe ``{block_id, kind, score}`` summary."""
        return {
            "block_id": self.block.block_id,
            "kind": self.block.kind,
            "score": self.score,
        }


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------- #
# Retrievers
# --------------------------------------------------------------------------- #
class RagRetriever:
    """In-memory cosine retriever over memory blocks (hermetic default).

    Embeds each block's ``to_context("full")`` with :class:`HashingEmbedder`
    (or a supplied :class:`Embedder`), stores the vectors in memory, and ranks
    queries by cosine similarity. No persistence, no heavy deps.
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder: Embedder = embedder or HashingEmbedder()
        self._blocks: list[Block] = []
        self._vectors: list[list[float]] = []

    def index(self, blocks: MemoryBlocks) -> None:
        """Embed and store every block in ``blocks`` (replacing any prior index)."""
        items = blocks.all_blocks()
        texts = [block.to_context("full") for block in items]
        self._blocks = items
        self._vectors = self.embedder.embed(texts) if texts else []

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        kinds: list[BlockKind] | None = None,
    ) -> list[ScoredBlock]:
        """Return the top-``k`` blocks by cosine similarity to ``query``.

        Args:
            query: The free-text query.
            k: Maximum number of results.
            kinds: Restrict results to these block kinds (all kinds when ``None``).

        Results are sorted by descending score, with a stable tie-break by
        ``block_id`` so rankings are deterministic.
        """
        if not self._blocks:
            return []
        query_vec = self.embedder.embed([query])[0]
        scored: list[ScoredBlock] = []
        for block, vector in zip(self._blocks, self._vectors, strict=True):
            if kinds is not None and block.kind not in kinds:
                continue
            scored.append(ScoredBlock(block=block, score=_cosine(query_vec, vector)))
        scored.sort(key=lambda item: (-item.score, item.block.block_id))
        return scored[:k]


class LanceDbRetriever:
    """LanceDB-backed retriever (``rag`` extra), same interface as :class:`RagRetriever`.

    Lazy-imports ``lancedb`` / ``numpy`` inside its methods so importing this
    module stays hermetic. Never exercised by the default test suite.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        *,
        uri: str | None = None,
        table_name: str = "blocks",
    ) -> None:
        self.embedder: Embedder = embedder or SentenceTransformerEmbedder()
        self.uri = uri
        self.table_name = table_name
        self._blocks: dict[str, Block] = {}
        self._table: object | None = None

    @staticmethod
    def _connect(uri: str | None) -> object:
        try:
            import lancedb
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise RetrievalDependencyError(
                "lancedb is required for LanceDbRetriever. Install with: uv sync --extra rag"
            ) from exc
        import tempfile

        return lancedb.connect(uri or tempfile.mkdtemp(prefix="clio-lancedb-"))

    def index(self, blocks: MemoryBlocks) -> None:
        """Embed every block and (re)create the LanceDB table."""
        db = self._connect(self.uri)
        items = blocks.all_blocks()
        self._blocks = {block.block_id: block for block in items}
        vectors = self.embedder.embed([block.to_context("full") for block in items])
        rows = [
            {"block_id": block.block_id, "kind": block.kind, "vector": vector}
            for block, vector in zip(items, vectors, strict=True)
        ]
        if self.table_name in db.table_names():  # type: ignore[attr-defined]
            db.drop_table(self.table_name)  # type: ignore[attr-defined]
        if rows:
            self._table = db.create_table(self.table_name, data=rows)  # type: ignore[attr-defined]
        else:
            self._table = None

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        kinds: list[BlockKind] | None = None,
    ) -> list[ScoredBlock]:
        """Return the top-``k`` blocks via a LanceDB vector search.

        The ``kinds`` filter is pushed into the query (a ``.where(...)`` clause
        on the ``kind`` column) so the backend returns ``k`` *matching* rows
        rather than ``k`` rows that may then be post-filtered down to fewer.
        """
        if self._table is None:
            return []
        query_vec = self.embedder.embed([query])[0]
        search = self._table.search(query_vec).metric("cosine")  # type: ignore[attr-defined]
        if kinds:
            # Push the kind filter down so the limit applies to matching rows.
            # Quote each kind for the SQL-style predicate LanceDB evaluates.
            quoted = ", ".join(f"'{kind}'" for kind in kinds)
            search = search.where(f"kind IN ({quoted})")
        results = search.limit(k).to_list()
        scored: list[ScoredBlock] = []
        for row in results:
            block = self._blocks.get(row["block_id"])
            if block is None:
                continue
            # LanceDB returns cosine *distance* (1 - similarity); convert back.
            score = 1.0 - float(row.get("_distance", 0.0))
            scored.append(ScoredBlock(block=block, score=score))
        scored.sort(key=lambda item: (-item.score, item.block.block_id))
        return scored[:k]


# --------------------------------------------------------------------------- #
# Selective context injection
# --------------------------------------------------------------------------- #
def render_scored(
    scored: list[ScoredBlock],
    detail: Detail = "summary",
) -> tuple[str, list[str]]:
    """Render scored blocks into joined context plus their block ids.

    Args:
        scored: Ranked blocks (typically from :meth:`RagRetriever.search`).
        detail: Detail level passed to :meth:`Block.to_context`.

    Returns:
        A ``(joined_context, block_ids)`` pair. ``joined_context`` is the blocks'
        renderings joined by blank lines; ``block_ids`` preserves their order.
    """
    contexts = [item.block.to_context(detail) for item in scored]
    block_ids = [item.block.block_id for item in scored]
    return "\n\n".join(contexts), block_ids


def inject_context(
    blocks: MemoryBlocks,
    *,
    retriever: RagRetriever | None = None,
    query: str | None = None,
    mode: Literal["topk", "section", "all"] = "topk",
    k: int = 5,
    detail: Detail = "summary",
    section_path: str | None = None,
) -> str:
    """Compose an injected-context string from ``blocks``.

    Modes:
        ``"all"``: every block (reuses :meth:`MemoryBlocks.select`).
        ``"section"``: blocks under ``section_path`` (reuses ``select``).
        ``"topk"``: the top-``k`` blocks for ``query`` via ``retriever`` (a
            default :class:`RagRetriever` is built and indexed when none is given).

    Returns:
        The selected block renderings joined by blank lines.
    """
    if mode == "all":
        return "\n\n".join(blocks.select(detail=detail))
    if mode == "section":
        return "\n\n".join(blocks.select(section_path=section_path, detail=detail))
    # topk
    if query is None:
        raise ValueError("query is required for mode='topk'")
    if retriever is None:
        retriever = RagRetriever()
        retriever.index(blocks)
    scored = retriever.search(query, k=k)
    context, _ = render_scored(scored, detail=detail)
    return context


__all__ = [
    "RetrievalDependencyError",
    "Embedder",
    "HashingEmbedder",
    "SentenceTransformerEmbedder",
    "ScoredBlock",
    "RagRetriever",
    "LanceDbRetriever",
    "render_scored",
    "inject_context",
]
