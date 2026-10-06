import logging
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest
from services.retriever import (
    GenerationConfigurationError,
    GenerationError,
    GroqResponseStreamer,
    HybridRetriever,
    RetrievalConfigurationError,
    RetrievalError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@lru_cache(maxsize=1)
def get_hybrid_retriever() -> HybridRetriever:
    """Return the process-wide hybrid retriever."""

    return HybridRetriever()


@lru_cache(maxsize=1)
def get_response_streamer() -> GroqResponseStreamer:
    """Return the process-wide Groq streaming client."""

    return GroqResponseStreamer()


@router.post(
    "/chat",
    response_class=StreamingResponse,
    summary="Chat with the hybrid GraphRAG engine",
)
async def chat(request: ChatRequest) -> StreamingResponse:
    """Retrieve hybrid context and stream a grounded answer."""

    try:
        retrieval = await get_hybrid_retriever().retrieve(
            request.query,
            top_k=request.top_k,
            graph_hops=request.graph_hops,
        )
        token_stream = await get_response_streamer().stream_answer(
            request.query,
            retrieval.fused_context,
        )
    except (GenerationConfigurationError, RetrievalConfigurationError) as exc:
        logger.exception("Chat dependencies are not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (RetrievalError, GenerationError) as exc:
        logger.exception("The chat request could not be started.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return StreamingResponse(
        _guard_stream(token_stream),
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Grag-Vector-Chunks": str(len(retrieval.vector_chunks)),
            "X-Grag-Graph-Triples": str(len(retrieval.graph_triples)),
        },
    )


async def _guard_stream(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    try:
        async for token in token_stream:
            yield token
    except GenerationError:
        logger.exception("The chat response failed after streaming started.")
        yield "\n\n[The response stream ended because generation failed.]"
