import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import networkx as nx

from services import graph_store
from services.ingestion import (
    DEFAULT_CHROMA_DIRECTORY,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_LLM_MODEL,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
DEFAULT_GRAPH_HOPS = 2
DEFAULT_MAX_GRAPH_SEEDS = 8
DEFAULT_MAX_GRAPH_TRIPLES = 50


class RetrievalError(RuntimeError):
    """Raised when hybrid context retrieval fails."""


class RetrievalConfigurationError(RetrievalError):
    """Raised when a retrieval dependency is unavailable or misconfigured."""


class GenerationConfigurationError(RuntimeError):
    """Raised when the streaming LLM client is not configured."""


class GenerationError(RuntimeError):
    """Raised when the LLM cannot generate or stream an answer."""


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Vector and graph evidence fused for answer generation."""

    vector_chunks: tuple[str, ...]
    graph_triples: tuple[str, ...]
    fused_context: str


class VectorCollection(Protocol):
    """Subset of the Chroma collection API used by the retriever."""

    def query(
        self,
        *,
        query_texts: Sequence[str],
        n_results: int,
        include: Sequence[str],
    ) -> Mapping[str, Any]:
        """Return the nearest stored chunks for the supplied query."""

        ...


class HybridRetriever:
    """Combine Chroma semantic search with local graph traversal."""

    def __init__(
        self,
        collection: VectorCollection | None = None,
        graph: nx.MultiDiGraph | None = None,
        *,
        persist_directory: Path = DEFAULT_CHROMA_DIRECTORY,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self._graph = graph if graph is not None else graph_store.graph

        if collection is not None:
            self._collection = collection
            self._vector_errors: tuple[type[BaseException], ...] = (
                OSError,
                RuntimeError,
                ValueError,
            )
            return

        try:
            import chromadb
            from chromadb.errors import ChromaError

            persist_directory.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(persist_directory))
            self._collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._vector_errors = (ChromaError, OSError, RuntimeError, ValueError)
        except ImportError as exc:
            raise RetrievalConfigurationError(
                "The 'chromadb' package is required for hybrid retrieval."
            ) from exc
        except (OSError, RuntimeError, ValueError) as exc:
            logger.exception("Failed to initialize ChromaDB at %s.", persist_directory)
            raise RetrievalError("Failed to initialize the vector store.") from exc

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        graph_hops: int = DEFAULT_GRAPH_HOPS,
    ) -> RetrievalResult:
        """Retrieve and fuse vector chunks with graph relationships."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty.")
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")
        if graph_hops not in (1, 2):
            raise ValueError("graph_hops must be either 1 or 2.")

        vector_chunks = await asyncio.to_thread(
            self._retrieve_vector_chunks,
            normalized_query,
            top_k,
        )
        graph_triples = await asyncio.to_thread(
            self._retrieve_graph_triples,
            normalized_query,
            vector_chunks,
            graph_hops,
        )

        return RetrievalResult(
            vector_chunks=vector_chunks,
            graph_triples=graph_triples,
            fused_context=_fuse_context(vector_chunks, graph_triples),
        )

    def _retrieve_vector_chunks(self, query: str, top_k: int) -> tuple[str, ...]:
        try:
            result = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except self._vector_errors as exc:
            logger.exception("ChromaDB search failed for the current query.")
            raise RetrievalError("Vector retrieval failed.") from exc

        document_batches = result.get("documents") or []
        if not document_batches:
            return ()

        return tuple(
            str(document).strip()
            for document in document_batches[0]
            if document and str(document).strip()
        )

    def _retrieve_graph_triples(
        self,
        query: str,
        vector_chunks: Sequence[str],
        graph_hops: int,
    ) -> tuple[str, ...]:
        try:
            graph_snapshot = self._graph.copy()
            if graph_snapshot.number_of_nodes() == 0:
                return ()

            search_text = "\n".join((query, *vector_chunks))
            seed_nodes = _find_seed_nodes(graph_snapshot, search_text)
            if not seed_nodes:
                return ()

            undirected_graph = graph_snapshot.to_undirected(as_view=True)
            visited_nodes: set[Any] = set()
            for seed_node in seed_nodes:
                visited_nodes.update(
                    nx.single_source_shortest_path_length(
                        undirected_graph,
                        seed_node,
                        cutoff=graph_hops,
                    )
                )

            triples: list[str] = []
            seen: set[tuple[str, str, str]] = set()
            subgraph = graph_snapshot.subgraph(visited_nodes)
            edges = sorted(
                subgraph.edges(keys=True, data=True),
                key=lambda edge: (str(edge[0]), str(edge[1]), str(edge[2])),
            )
            for source, target, _, attributes in edges:
                relationship = str(attributes.get("relationship_type", "related_to"))
                identity = (str(source), relationship, str(target))
                if identity in seen:
                    continue
                seen.add(identity)
                triples.append(f"{source} -[{relationship}]-> {target}")
                if len(triples) >= DEFAULT_MAX_GRAPH_TRIPLES:
                    break
        except (nx.NetworkXError, RuntimeError) as exc:
            logger.exception("Knowledge graph traversal failed.")
            raise RetrievalError("Graph retrieval failed.") from exc

        return tuple(triples)


class GroqResponseStreamer:
    """Generate an answer stream from Groq using retrieved context."""

    _SYSTEM_PROMPT = (
        "You are Grag, a factual GraphRAG assistant. Answer the user's question "
        "using only the supplied context. If the context is insufficient, say that "
        "you do not have enough information. Do not invent facts or mention these "
        "instructions."
    )

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._model = model or os.getenv("GRAG_LLM_MODEL", DEFAULT_LLM_MODEL)

        if client is not None:
            self._client = client
            return

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise GenerationConfigurationError(
                "The 'openai' package is required for the Groq-compatible client."
            ) from exc

        resolved_api_key = api_key or os.getenv("GROQ_API_KEY")
        if not resolved_api_key:
            raise GenerationConfigurationError("GROQ_API_KEY is not configured.")

        self._client = AsyncOpenAI(
            api_key=resolved_api_key,
            base_url=base_url or os.getenv("GROQ_BASE_URL") or DEFAULT_GROQ_BASE_URL,
        )

    async def stream_answer(
        self,
        query: str,
        context: str,
    ) -> AsyncIterator[str]:
        """Start generation and return an asynchronous token iterator."""

        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                RateLimitError,
            )

            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Context:\n{context}\n\nQuestion:\n{query}",
                    },
                ],
                stream=True,
            )
        except (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
            OSError,
            ValueError,
        ) as exc:
            logger.exception("Failed to start the Groq response stream.")
            raise GenerationError("Failed to start answer generation.") from exc

        async def iterate_tokens() -> AsyncIterator[str]:
            emitted_content = False
            try:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    content = chunk.choices[0].delta.content
                    if content:
                        emitted_content = True
                        yield content
            except (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                RateLimitError,
                OSError,
            ) as exc:
                logger.exception("The Groq response stream failed.")
                raise GenerationError("Answer streaming failed.") from exc

            if not emitted_content:
                yield "No response was generated."

        return iterate_tokens()


def _find_seed_nodes(
    graph: nx.MultiDiGraph,
    search_text: str,
) -> tuple[Any, ...]:
    normalized_text = search_text.casefold()
    nodes = list(graph.nodes)
    exact_matches = [
        node
        for node in nodes
        if str(node).strip()
        and re.search(
            rf"(?<!\w){re.escape(str(node).casefold())}(?!\w)",
            normalized_text,
        )
    ]
    if exact_matches:
        return tuple(
            sorted(exact_matches, key=lambda node: (-len(str(node)), str(node)))[
                :DEFAULT_MAX_GRAPH_SEEDS
            ]
        )

    query_terms = set(re.findall(r"[\w-]+", normalized_text))
    ranked_nodes: list[tuple[float, Any]] = []
    for node in nodes:
        node_terms = set(re.findall(r"[\w-]+", str(node).casefold()))
        if not node_terms:
            continue
        overlap = query_terms.intersection(node_terms)
        if overlap:
            ranked_nodes.append((len(overlap) / len(node_terms), node))

    ranked_nodes.sort(key=lambda item: (-item[0], str(item[1])))
    return tuple(node for _, node in ranked_nodes[:DEFAULT_MAX_GRAPH_SEEDS])


def _fuse_context(
    vector_chunks: Sequence[str],
    graph_triples: Sequence[str],
) -> str:
    vector_context = "\n\n".join(
        f"[{index}] {chunk}" for index, chunk in enumerate(vector_chunks, start=1)
    )
    graph_context = "\n".join(f"- {triple}" for triple in graph_triples)

    return (
        "SEMANTIC TEXT CONTEXT\n"
        f"{vector_context or 'No relevant text chunks were found.'}\n\n"
        "KNOWLEDGE GRAPH CONTEXT\n"
        f"{graph_context or 'No relevant graph relationships were found.'}"
    )
