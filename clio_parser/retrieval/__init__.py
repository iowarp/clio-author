"""Retrieval: ranking memory blocks and selective context injection.

The hermetic default path (:class:`HashingEmbedder` + in-memory
:class:`RagRetriever`) needs no heavy dependencies. The optional LanceDB /
SentenceTransformer backend lives behind the ``rag`` extra and is lazy-imported.
"""

from clio_parser.retrieval.rag import (
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
from clio_parser.retrieval.literature_graph import (
    CascadeLiteratureGraphClient,
    GraphEdge,
    GraphSeed,
    LiteratureGraph,
    LiteratureGraphClient,
    OpenAlexGraphClient,
    PaperNode,
    SemanticScholarGraphClient,
    resolve_literature_graph_client,
)

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "LanceDbRetriever",
    "RagRetriever",
    "RetrievalDependencyError",
    "ScoredBlock",
    "SentenceTransformerEmbedder",
    "CascadeLiteratureGraphClient",
    "GraphEdge",
    "GraphSeed",
    "LiteratureGraph",
    "LiteratureGraphClient",
    "OpenAlexGraphClient",
    "PaperNode",
    "SemanticScholarGraphClient",
    "inject_context",
    "render_scored",
    "resolve_literature_graph_client",
]
