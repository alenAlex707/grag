# Product Requirements Document (PRD): Dynamic Knowledge Graph RAG (GraphRAG)

## 1. Project Overview
A production-grade backend service that implements a Hybrid GraphRAG engine. It ingests unstructured text, extracts entities and relationships into a local graph database, embeds chunks into a vector store, and performs hybrid retrieval (Graph Traversal + Semantic Search) for precise, context-aware LLM generation.

## 2. Tech Stack
* **Language/Framework:** Python 3.11+, FastAPI, Pydantic v2
* **Graph Engine:** NetworkX (serialized to JSON/Pickle locally for zero-config persistence)
* **Vector Database:** ChromaDB (embedded mode) or Qdrant (local file storage)
* **LLM Integration:** OpenAI API or Ollama (local model support via LangChain or direct client)
* **Dependency & Env Management:** `uv`
, `python-dotenv`

## 3. Core Architecture & Modules
1. **Ingestion Pipeline (`services/ingestion.py`):**
   * Document parsing & text chunking.
   * LLM-powered entity/relationship extraction using strict Pydantic schemas (`[Entity] -> [Relationship] -> [Entity]`).
   * Dual-write: Chunks to Vector DB, Triples to Graph DB.
2. **Hybrid Retrieval Engine (`services/retriever.py`):**
   * Query analysis: Extract key entities from the user prompt.
   * Graph Traversal: 1-hop and 2-hop neighbor extraction from NetworkX.
   * Vector Search: Top-$k$ semantic chunk retrieval.
   * Context Fusion: Merging graph triples and text chunks into a structured prompt.
3. **API Layer (`routers/`):**
   * `POST /api/v1/ingest`: Accepts raw text/documents, triggers ingestion pipeline.
   * `POST /api/v1/chat`: Accepts user query, runs hybrid retrieval, returns streamed LLM response.

## 4. Non-Functional Requirements
* Modular, clean architecture with type hints throughout.
* Clear error handling for LLM timeout/rate-limit exceptions.
* Fully documented endpoints via FastAPI auto-generated Swagger UI (`/docs`).