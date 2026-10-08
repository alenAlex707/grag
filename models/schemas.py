from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    """Base model for API and structured LLM payloads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentIngestionRequest(StrictSchema):
    """Payload accepted when ingesting a text document."""

    text: str = Field(min_length=1, description="Raw document text to ingest.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata associated with the document.",
    )


class IngestionResponse(StrictSchema):
    """Summary returned after documents are persisted successfully."""

    document_ids: list[str]
    document_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    triple_count: int = Field(ge=0)


class EntityRelationshipTriple(StrictSchema):
    """A directed relationship between two extracted entities."""

    source_entity: str = Field(
        min_length=1,
        description="Entity where the directed relationship begins.",
    )
    relationship_type: str = Field(
        min_length=1,
        description="Type of relationship connecting the entities.",
    )
    target_entity: str = Field(
        min_length=1,
        description="Entity where the directed relationship ends.",
    )


class TripleExtractionResult(StrictSchema):
    """Validated collection returned by structured triple extraction."""

    triples: list[EntityRelationshipTriple] = Field(
        description="Entity-relationship triples extracted from the input text."
    )


class ChatRequest(StrictSchema):
    """Query and retrieval controls accepted by the chat endpoint."""

    query: str = Field(min_length=1, description="Question to answer using Grag.")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of semantically similar chunks to retrieve.",
    )
    graph_hops: int = Field(
        default=2,
        ge=1,
        le=2,
        description="Number of graph hops to traverse from matched entities.",
    )
