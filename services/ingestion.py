import asyncio
import hashlib
import json
import logging
import os
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from models.schemas import (
    DocumentIngestionRequest,
    EntityRelationshipTriple,
    TripleExtractionResult,
)
from services import graph_store

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_EXTRACTION_CONCURRENCY = 4
DEFAULT_CHROMA_DIRECTORY = Path(__file__).resolve().parents[1] / "chroma_db"
DEFAULT_COLLECTION_NAME = "grag_documents"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

_GRAPH_WRITE_LOCK = threading.Lock()

MetadataValue = str | int | float | bool
DocumentInput = str | DocumentIngestionRequest


class IngestionError(RuntimeError):
    """Base exception for ingestion pipeline failures."""


class IngestionConfigurationError(IngestionError):
    """Raised when an ingestion dependency is unavailable or misconfigured."""


class TripleExtractionError(IngestionError):
    """Raised when structured triple extraction fails."""


class VectorStoreError(IngestionError):
    """Raised when chunks cannot be persisted in the vector store."""


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """A chunk of a source document with stable persistence identifiers."""

    id: str
    document_id: str
    index: int
    text: str
    metadata: dict[str, MetadataValue]


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """Counts and identifiers produced by a completed ingestion run."""

    document_ids: tuple[str, ...]
    document_count: int
    chunk_count: int
    triple_count: int


class TripleExtractor(Protocol):
    """Contract for an asynchronous structured triple extractor."""

    async def extract(self, text: str) -> TripleExtractionResult:
        """Extract validated graph triples from text."""

        ...


class VectorStore(Protocol):
    """Contract for asynchronous chunk persistence."""

    async def upsert_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        """Insert or replace chunks using their stable identifiers."""

        ...


class OpenAITripleExtractor:
    """Extract triples with OpenAI structured outputs and Pydantic validation."""

    _SYSTEM_PROMPT = (
        "Extract factual, directed entity relationships from the supplied text. "
        "Use concise canonical entity names and a concise relationship type. "
        "Return only relationships explicitly supported by the text."
    )

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise IngestionConfigurationError(
                "The 'openai' package is required for triple extraction."
            ) from exc

        self._model = model or os.getenv("GRAG_LLM_MODEL", DEFAULT_LLM_MODEL)
        self._client: Any = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def extract(self, text: str) -> TripleExtractionResult:
        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                RateLimitError,
            )

            completion = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                response_format=TripleExtractionResult,
            )
            message = completion.choices[0].message
        except (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
            ValidationError,
            IndexError,
        ) as exc:
            logger.exception("Structured triple extraction failed.")
            raise TripleExtractionError("Structured triple extraction failed.") from exc

        if message.refusal:
            logger.warning("The LLM refused triple extraction: %s", message.refusal)
            raise TripleExtractionError(
                f"The LLM refused extraction: {message.refusal}"
            )
        if message.parsed is None:
            raise TripleExtractionError(
                "The LLM returned no validated extraction result."
            )

        return message.parsed


class ChromaVectorStore:
    """Embedded ChromaDB adapter using its local persistent client."""

    def __init__(
        self,
        persist_directory: Path = DEFAULT_CHROMA_DIRECTORY,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        try:
            import chromadb
            from chromadb.errors import ChromaError
        except ImportError as exc:
            raise IngestionConfigurationError(
                "The 'chromadb' package is required for vector persistence."
            ) from exc

        try:
            persist_directory.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(persist_directory))
            self._collection: Any = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except (ChromaError, OSError, ValueError) as exc:
            logger.exception("Failed to initialize ChromaDB at %s.", persist_directory)
            raise VectorStoreError("Failed to initialize the vector store.") from exc

        self._chroma_error = ChromaError

    async def upsert_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        if not chunks:
            return

        await asyncio.to_thread(self._upsert_chunks_sync, chunks)

    def _upsert_chunks_sync(self, chunks: Sequence[DocumentChunk]) -> None:
        try:
            self._collection.upsert(
                ids=[chunk.id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                metadatas=[chunk.metadata for chunk in chunks],
            )
        except (self._chroma_error, OSError, ValueError) as exc:
            logger.exception("Failed to persist %d chunks in ChromaDB.", len(chunks))
            raise VectorStoreError("Failed to persist document chunks.") from exc


class IngestionService:
    """Coordinate chunking, extraction, graph writes, and vector persistence."""

    def __init__(
        self,
        triple_extractor: TripleExtractor | None = None,
        vector_store: VectorStore | None = None,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        extraction_concurrency: int = DEFAULT_EXTRACTION_CONCURRENCY,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero.")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be non-negative and less than chunk_size."
            )
        if extraction_concurrency <= 0:
            raise ValueError("extraction_concurrency must be greater than zero.")

        self._triple_extractor = triple_extractor or OpenAITripleExtractor()
        self._vector_store = vector_store or ChromaVectorStore()
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._extraction_semaphore = asyncio.Semaphore(extraction_concurrency)

    async def ingest(
        self,
        documents: DocumentInput | Sequence[DocumentInput],
    ) -> IngestionSummary:
        """Ingest one or more documents into both local persistence stores."""

        normalized_documents = _normalize_documents(documents)
        chunks = [
            chunk
            for document in normalized_documents
            for chunk in chunk_document(
                document,
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
        ]

        extraction_results = await asyncio.gather(
            *(self._extract_chunk(chunk) for chunk in chunks)
        )
        extracted_triples = _deduplicate_triples(
            triple for result in extraction_results for triple in result.triples
        )

        await self._vector_store.upsert_chunks(chunks)
        await asyncio.to_thread(_persist_triples, extracted_triples)

        summary = IngestionSummary(
            document_ids=tuple(
                _document_id(document) for document in normalized_documents
            ),
            document_count=len(normalized_documents),
            chunk_count=len(chunks),
            triple_count=len(extracted_triples),
        )
        logger.info(
            "Ingested %d documents as %d chunks and %d unique triples.",
            summary.document_count,
            summary.chunk_count,
            summary.triple_count,
        )
        return summary

    async def _extract_chunk(self, chunk: DocumentChunk) -> TripleExtractionResult:
        async with self._extraction_semaphore:
            try:
                return await self._triple_extractor.extract(chunk.text)
            except TripleExtractionError:
                raise
            except (OSError, RuntimeError, ValidationError, ValueError) as exc:
                logger.exception("Triple extraction failed for chunk %s.", chunk.id)
                raise TripleExtractionError(
                    f"Triple extraction failed for chunk {chunk.id}."
                ) from exc


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, preferring natural boundaries."""

    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("Document text must not be empty.")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and less than chunk_size.")

    chunks: list[str] = []
    start = 0

    while start < len(normalized_text):
        end = min(start + chunk_size, len(normalized_text))
        if end < len(normalized_text):
            minimum_boundary = start + (chunk_size // 2)
            boundary = max(
                normalized_text.rfind("\n\n", minimum_boundary, end),
                normalized_text.rfind(". ", minimum_boundary, end),
                normalized_text.rfind(" ", minimum_boundary, end),
            )
            if boundary >= minimum_boundary:
                end = boundary + 1

        chunk = normalized_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized_text):
            break

        start = max(end - chunk_overlap, start + 1)

    return chunks


def chunk_document(
    document: DocumentIngestionRequest,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Create identified chunks with Chroma-compatible metadata."""

    document_id = _document_id(document)
    metadata = _normalize_metadata(document.metadata)
    text_chunks = chunk_text(
        document.text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    return [
        DocumentChunk(
            id=f"{document_id}:{index}",
            document_id=document_id,
            index=index,
            text=text,
            metadata={
                **metadata,
                "document_id": document_id,
                "chunk_index": index,
            },
        )
        for index, text in enumerate(text_chunks)
    ]


def _normalize_documents(
    documents: DocumentInput | Sequence[DocumentInput],
) -> list[DocumentIngestionRequest]:
    items: Sequence[DocumentInput]
    if isinstance(documents, (str, DocumentIngestionRequest)):
        items = [documents]
    else:
        items = documents

    if not items:
        raise ValueError("At least one document is required.")

    try:
        return [
            item
            if isinstance(item, DocumentIngestionRequest)
            else DocumentIngestionRequest(text=item)
            for item in items
        ]
    except (TypeError, ValidationError) as exc:
        logger.exception("Invalid document ingestion payload.")
        raise ValueError("Every document must contain non-empty text.") from exc


def _document_id(document: DocumentIngestionRequest) -> str:
    serialized_metadata = json.dumps(
        document.metadata,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(
        f"{document.text}\0{serialized_metadata}".encode()
    ).hexdigest()
    return digest


def _normalize_metadata(metadata: Mapping[str, Any]) -> dict[str, MetadataValue]:
    normalized: dict[str, MetadataValue] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        elif value is None:
            normalized[key] = ""
        else:
            normalized[key] = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
    return normalized


def _deduplicate_triples(
    triples: Iterable[EntityRelationshipTriple],
) -> list[EntityRelationshipTriple]:
    unique_triples: list[EntityRelationshipTriple] = []
    seen: set[tuple[str, str, str]] = set()

    for triple in triples:
        identity = (
            triple.source_entity.casefold(),
            triple.relationship_type.casefold(),
            triple.target_entity.casefold(),
        )
        if identity not in seen:
            seen.add(identity)
            unique_triples.append(triple)

    return unique_triples


def _persist_triples(triples: Sequence[EntityRelationshipTriple]) -> None:
    try:
        with _GRAPH_WRITE_LOCK:
            for triple in triples:
                graph_store.add_edge(
                    source_entity=triple.source_entity,
                    relationship_type=triple.relationship_type,
                    target_entity=triple.target_entity,
                )
            graph_store.save_graph()
    except (ValueError, graph_store.GraphStoreError) as exc:
        logger.exception("Failed to persist extracted triples in the graph store.")
        raise IngestionError("Failed to persist extracted graph triples.") from exc
