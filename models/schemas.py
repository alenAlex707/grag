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
