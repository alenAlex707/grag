from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.chat import router as chat_router
from routers.ingest import router as ingest_router

app = FastAPI(
    title="Grag",
    description="Hybrid GraphRAG backend service.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Grag-Vector-Chunks", "X-Grag-Graph-Triples"],
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat_router)
api_router.include_router(ingest_router)
app.include_router(api_router)


@app.get("/", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "Grag"}
