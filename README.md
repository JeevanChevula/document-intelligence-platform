# Document Intelligence Platform

A production-deployed, multi-agent RAG system for question-answering over PDF documents (searchable and scanned). Built to demonstrate real end-to-end deployment experience, not just a local prototype.

## Architecture

- **Frontend:** Streamlit — chosen deliberately over React to keep the project's focus on backend/AI engineering.
- **Backend:** FastAPI, with JWT authentication.
- **Agent orchestration:** LangGraph, with four agents:
  - Router — decides how to handle an incoming query
  - Retrieval — fetches relevant chunks from the vector store
  - Answer Generation — produces the response via the LLM
  - Validator — checks the generated answer before returning it
- **Vector store:** Qdrant (Docker, local for now)
- **Relational store:** PostgreSQL (Docker, local for now) — users, chat sessions, chat history, document metadata
- **File storage:** Local disk behind a storage abstraction layer, swappable to AWS S3 later without touching business logic
- **LLM:** Groq API (`llama-3.3-70b-versatile`)
- **OCR:** PyMuPDF for clean/searchable PDFs; PaddleOCR for scanned PDFs; Tesseract as a fallback if PaddleOCR is too resource-heavy
- **Containerization:** Docker + Docker Compose
- **Testing:** pytest
- **CI/CD:** GitHub Actions (added once core code exists)

## Scope

- Input is PDF only — both searchable and scanned. No DOCX, no standalone images.
- No Kubernetes — Docker Compose is sufficient at this scale.
- No React — Streamlit is sufficient for this project's purpose.

## Development approach

1. Build and test the entire system locally first, with zero cloud cost.
2. Only after the full local system works end-to-end: create an AWS account, set up billing alerts, then deploy to EC2 free tier.

## Local setup

1. Copy `.env.example` to `.env` and fill in `GROQ_API_KEY`.
2. Start infra services:
   ```bash
   docker compose up -d
   ```
3. (App run instructions will be added once the FastAPI app exists.)

See `PROGRESS.md` for a running log of what's built, what's working, and what's next.
