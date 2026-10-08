import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from models.schemas import DocumentIngestionRequest, IngestionResponse
from services.ingestion import (
    IngestionConfigurationError,
    IngestionError,
    IngestionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])

ALLOWED_FILE_EXTENSIONS = {".md", ".txt"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    """Return the process-wide ingestion service."""

    return IngestionService()


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest text or a document into Grag",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/DocumentIngestionRequest"}
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "file": {"type": "string", "format": "binary"},
                            "metadata": {
                                "type": "string",
                                "description": "Optional JSON object.",
                            },
                        },
                    }
                },
            },
            "required": True,
        }
    },
)
async def ingest(request: Request) -> IngestionResponse:
    """Parse JSON or multipart input, then persist vectors and graph triples."""

    documents = await _parse_documents(request)

    try:
        summary = await get_ingestion_service().ingest(documents)
    except IngestionConfigurationError as exc:
        logger.exception("Ingestion dependencies are not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except IngestionError as exc:
        logger.exception("Document ingestion failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return IngestionResponse(
        document_ids=list(summary.document_ids),
        document_count=summary.document_count,
        chunk_count=summary.chunk_count,
        triple_count=summary.triple_count,
    )


async def _parse_documents(request: Request) -> list[DocumentIngestionRequest]:
    content_type = request.headers.get("content-type", "").lower()

    if content_type.startswith("application/json"):
        return [await _parse_json_document(request)]
    if content_type.startswith("multipart/form-data"):
        return await _parse_multipart_documents(request)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Use application/json or multipart/form-data.",
    )


async def _parse_json_document(request: Request) -> DocumentIngestionRequest:
    try:
        payload: Any = await request.json()
        return DocumentIngestionRequest.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The JSON body must include non-empty text and optional metadata.",
        ) from exc


async def _parse_multipart_documents(
    request: Request,
) -> list[DocumentIngestionRequest]:
    try:
        form = await request.form()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The multipart form could not be parsed.",
        ) from exc

    metadata = _parse_metadata(form.get("metadata"))
    documents: list[DocumentIngestionRequest] = []
    text_value = form.get("text")
    file_value = form.get("file")

    if isinstance(text_value, str) and text_value.strip():
        documents.append(DocumentIngestionRequest(text=text_value, metadata=metadata))

    if isinstance(file_value, UploadFile) and file_value.filename:
        file_text = await _read_text_file(file_value)
        documents.append(
            DocumentIngestionRequest(
                text=file_text,
                metadata={**metadata, "filename": file_value.filename},
            )
        )

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide non-empty text or a .txt/.md file.",
        )

    return documents


def _parse_metadata(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata must be a JSON object encoded as text.",
        )

    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata must contain valid JSON.",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata must decode to a JSON object.",
        )
    return parsed


async def _read_text_file(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .txt and .md files are supported.",
        )

    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded files must be 10 MB or smaller.",
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded files must use UTF-8 encoding.",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty.",
        )
    return text
