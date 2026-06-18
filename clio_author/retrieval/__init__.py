"""Retrieval: ranking memory blocks and selective context injection.

The hermetic default path (:class:`HashingEmbedder` + in-memory
:class:`RagRetriever`) needs no heavy dependencies. The optional LanceDB /
SentenceTransformer backend lives behind the ``rag`` extra and is lazy-imported.
"""

from clio_author.retrieval.rag import (
    Embedder,
    HashingEmbedder,
    LanceDbRetriever,
    RagRetriever,
    RetrievalDependencyError,
    ScoredBlock,
    SentenceTransformerEmbedder,
    inject_context,
    render_scored,
)
from clio_author.retrieval.kg import (
    EdgeRelation,
    KGEdge,
    KGNode,
    KnowledgeGraph,
    NodeType,
    build_kg_from_llm,
)

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "LanceDbRetriever",
    "RagRetriever",
    "RetrievalDependencyError",
    "ScoredBlock",
    "SentenceTransformerEmbedder",
    "EdgeRelation",
    "KGEdge",
    "KGNode",
    "KnowledgeGraph",
    "NodeType",
    "build_kg_from_llm",
    "inject_context",
    "render_scored",
]
