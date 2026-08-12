# Document Intelligence Platform

A multi-agent RAG system for question-answering over PDF documents — both searchable and scanned. Upload your PDFs, then ask questions about them in a chat interface. Every answer is labelled with where it actually came from, so you can always tell a document-grounded answer from the model's own general knowledge.

Built and deployed end-to-end: FastAPI backend, LangGraph agent pipeline, Qdrant vector search, PostgreSQL, Streamlit frontend, Docker Compose, GitHub Actions CI, running on AWS EC2.

## What it does

1. **Register / log in** — JWT authentication; every user only ever sees their own documents and chats.
2. **Upload a PDF** — the file is validated, text-extracted, and indexed for semantic search. Scanned PDFs (no embedded text) are automatically detected and routed through OCR.
3. **Ask questions in chat** — a four-agent pipeline decides how to handle the question, searches your documents, generates an answer grounded in what it found, and fact-checks that answer before showing it to you.
4. **See where each answer came from** — every assistant reply carries an explicit source label:

   | Label | Meaning |
   |---|---|
   | 📄 From your documents | Grounded in your uploaded content, and the Validator confirmed it |
   | 🧠 General knowledge | Answered from the model's own knowledge — not from your files |
   | ⚠️ No relevant documents found | The question was document-shaped, but nothing usable was found |
   | ❌ Error | The pipeline failed (LLM outage, rate limit) — your question is still saved |

## Architecture

```
Streamlit (8501)  ──HTTP──▶  FastAPI (8000)  ──▶  LangGraph pipeline  ──▶  Groq LLM
                                   │
                                   ├──▶  PostgreSQL (5432)   users, chat sessions, messages, document metadata
                                   ├──▶  Qdrant (6333)       chunk embeddings + payloads
                                   └──▶  Local disk          uploaded PDFs (behind a storage abstraction)
```

### The agent pipeline

Orchestrated with **LangGraph** as a state graph with a conditional branch:

```
          ┌─▶ general ──────────────────────────┐
Router ───┤                                     ├─▶ Generation ─▶ Validator ─▶ answer
          └─▶ retrieval ─▶ Retrieval agent ─────┘
```

- **Router** — classifies the message as `retrieval` (needs the user's documents) or `general` (greeting, small talk, unrelated question). Runs at `temperature=0.0`, and deliberately sees **only the current message** — feeding it conversation history caused unrelated recent chat to bias its classification.
- **Retrieval** — embeds the question and searches Qdrant, filtered server-side by `user_id` so one user's query can never touch another user's chunks.
- **Generation** — answers strictly from the retrieved context on the `retrieval` path, or converses normally on the `general` path. Receives recent conversation history, so follow-ups like "check that again" work.
- **Validator** — an independent second LLM call ("LLM-as-judge") that fact-checks the generated answer against the same retrieved chunks. If it can't confirm the answer is grounded, the answer is returned with an explicit disclaimer rather than presented as fact.

### Retrieval design

Retrieval deliberately does **not** filter by a similarity-score threshold. Measured on real data with this embedding model, cosine similarity did not separate relevant from irrelevant content: an unrelated control query scored `0.495` while a genuinely relevant chunk scored `0.455`. No threshold value can split those. Instead the pipeline retrieves generously (top 20) and lets the LLM do relevance judgement in Generation and Validator, which it does far better at this scale.

This suits the project's scope — a handful of personal documents per user. At corpus sizes in the hundreds or thousands of chunks it would need a stronger embedding model or a reranking step instead.

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Streamlit | Chosen over React to keep focus on backend/AI engineering |
| Backend | FastAPI + Pydantic | JWT auth (python-jose), bcrypt password hashing |
| Agents | LangGraph | `StateGraph` with a conditional edge on the Router's decision |
| LLM | Groq — `llama-3.3-70b-versatile` | Configurable via `GROQ_MODEL` |
| Embeddings | fastembed — `BAAI/bge-small-en-v1.5` (384-dim) | ONNX-based; chosen over PyTorch-based alternatives to keep the dependency footprint small |
| Vector store | Qdrant | Cosine distance, server-side `user_id` filtering |
| Database | PostgreSQL + SQLAlchemy + Alembic | Versioned schema migrations |
| PDF text | PyMuPDF | Also detects whether a PDF is scanned |
| OCR | Tesseract (pytesseract) | Pages rendered at 300 DPI before OCR |
| File storage | Local disk behind an abstraction | Swappable to S3 without touching business logic |
| Infra | Docker Compose | Postgres, Qdrant, Adminer |
| Tests | pytest | 50 tests; LLM calls mocked so the suite never spends API quota |
| CI | GitHub Actions | Runs the full suite against a real Qdrant service container |

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/register` | Create an account |
| `POST` | `/auth/login` | Get a JWT access token |
| `GET` | `/auth/me` | Current user |
| `POST` | `/documents/upload` | Upload and index a PDF |
| `GET` | `/documents` | List your uploaded documents |
| `POST` | `/chat/sessions` | Start a chat session |
| `GET` | `/chat/sessions` | List your chat sessions |
| `POST` | `/chat/sessions/{id}/messages` | Send a message, run the pipeline, get the answer |
| `GET` | `/chat/sessions/{id}/messages` | Full chat history |
| `GET` | `/health` | Health check |

Interactive docs at `/docs` when the backend is running.

Every endpoint requires authentication and is scoped to the logged-in user. Requesting another user's chat session returns `404`, not `403`, so the API never reveals whether it exists.

## Running locally

**Prerequisites:** Docker, Python 3.13, and Tesseract (`sudo apt install tesseract-ocr`).

```bash
# 1. Configure
cp .env.example .env        # then fill in GROQ_API_KEY and JWT_SECRET_KEY

# 2. Start infrastructure
docker compose up -d

# 3. Install dependencies
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Create the database schema
alembic upgrade head

# 5. Run the backend and frontend
uvicorn app.main:app --reload
streamlit run frontend/app.py          # in a second terminal
```

| Service | URL |
|---|---|
| Streamlit app | http://localhost:8501 |
| FastAPI backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Adminer (browse Postgres) | http://localhost:8081 |
| Qdrant dashboard | http://localhost:6333/dashboard |

## Deployment

Deployed on an **AWS EC2** `t3.small` instance (Ubuntu, ap-south-2), provisioned within the AWS free tier.

The instance runs the same stack as local development: Docker Compose for Postgres and Qdrant, with the FastAPI backend and Streamlit frontend running directly on the host. Its security group exposes ports `8000` and `8501` publicly, while SSH (`22`) is restricted to a single administrative IP.

```bash
# On the instance
git pull
source .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
nohup streamlit run frontend/app.py --server.headless true \
      --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &
```

Secrets are never committed — `.env` is recreated directly on the instance.

## Testing

```bash
pytest tests/ -v
```

50 tests covering chunking, embeddings, PDF extraction, OCR, storage, JWT/password security, PDF validation, all four agents, and the full graph wiring.

Two deliberate testing decisions:

- **LLM calls are always mocked.** The suite asserts on *our* logic — prompt construction, routing decisions, source labelling, history threading — and never spends real API quota.
- **Retrieval is tested against a real Qdrant instance**, not a mock, because multi-tenant isolation is a security property worth verifying for real. One test specifically asserts that a second user's semantically-matching query never returns another user's chunks.

CI runs the same suite on every push and pull request against `main`.

## Scope

Deliberate boundaries, chosen to keep the project focused:

- **PDF only** — searchable and scanned. No DOCX, no standalone images.
- **No Kubernetes** — Docker Compose is sufficient at this scale.
- **No React** — Streamlit is a deliberate choice, not a shortcut.

## Known limitations

- **LLM rate limits.** Runs on Groq's free tier (100K tokens/day). Each document question costs roughly 3,600 tokens across the Generation and Validator calls, so sustained heavy use can exhaust the daily budget; a paid tier removes the ceiling.
- **Retrieval doesn't scale to large corpora.** The retrieve-generously strategy described above is right for a handful of documents per user, but would need a reranking step at much larger scale.
- **Documents can't be deleted through the API** yet — uploads are currently add-only.
- **No HTTPS.** The deployment serves plain HTTP on its EC2 public IP.
