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
    BASE_EDGE_RELATIONS,
    BASE_NODE_TYPES,
    KGEdge,
    KGNode,
    KnowledgeGraph,
    build_kg_from_llm,
    coerce_node_type,
    coerce_relation,
)
from clio_author.retrieval.kg_pipeline import (
    Ontology,
    OntologyType,
    detect_domain,
    generate_ontology,
    resolve_coref,
    run_kg_pipeline,
    verify_graph,
)

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "LanceDbRetriever",
    "RagRetriever",
    "RetrievalDependencyError",
    "ScoredBlock",
    "SentenceTransformerEmbedder",
    "BASE_EDGE_RELATIONS",
    "BASE_NODE_TYPES",
    "KGEdge",
    "KGNode",
    "KnowledgeGraph",
    "build_kg_from_llm",
    "coerce_node_type",
    "coerce_relation",
    "Ontology",
    "OntologyType",
    "detect_domain",
    "generate_ontology",
    "resolve_coref",
    "verify_graph",
    "run_kg_pipeline",
    "inject_context",
    "render_scored",
]
