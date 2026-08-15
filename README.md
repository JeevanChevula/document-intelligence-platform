# Document Intelligence Platform

A multi-agent RAG system for question-answering over PDF documents — both searchable and scanned. Upload your PDFs, then ask questions about them in a chat interface. Every answer is labelled with where it actually came from, so you can always tell a document-grounded answer from the model's own general knowledge.

Built and deployed end-to-end: FastAPI backend, LangGraph agent pipeline, Qdrant vector search, PostgreSQL, Streamlit frontend, Docker Compose, GitHub Actions CI, running on AWS EC2.

## Live demo

🔗 **http://98.130.133.25:8501**

Register an account, upload a PDF, and ask questions about it.

> Served over plain HTTP, so please **don't reuse a real password** — anything you type is
> sent unencrypted. It runs on a free-tier LLM capped at 200K tokens/day, so answers may
> occasionally fail once that's exhausted.

## What it does

1. **Register / log in** — JWT authentication; every user only ever sees their own documents and chats.
2. **Upload a PDF** — the file is validated, text-extracted, and indexed for semantic search. Scanned PDFs (no embedded text) are automatically detected and routed through OCR.
3. **Ask questions in chat** — a four-agent pipeline decides how to handle the question, searches your documents, generates an answer grounded in what it found, and fact-checks that answer before showing it to you. Chats are named automatically after their opening message.
4. **See where each answer came from** — every assistant reply carries an explicit source label:

   | Label | Meaning |
   |---|---|
   | 📄 From your documents | Answered using your uploaded content |
   | 🧠 General knowledge | Answered from the model's own knowledge — not from your files |
   | ⚠️ No relevant documents found | The question was document-shaped, but nothing was retrieved |
   | ❌ Error | The pipeline failed (LLM outage, rate limit) — your question is still saved |

   Verification is reported *separately* from provenance: a document-grounded answer the
   Validator couldn't confirm is shown as 📄 with an added "parts not verified" note, rather
   than being demoted to "no relevant documents". The two are genuinely different questions —
   an advisory question ("what roles should I apply for based on my resume?") legitimately
   extrapolates beyond the source while still being grounded in it.

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

- **Router** — classifies the message as `retrieval` (needs the user's documents) or `general` (greeting, small talk, unrelated question). Runs at `temperature=0.0`, and deliberately sees **only the current message** — feeding it conversation history caused unrelated recent chat to bias its classification. It *is* given the user's document **filenames** (never their contents, so the cost is a few tokens): judging a sentence in a vacuum proved fragile to phrasing, where a one-character typo — "validity **or** my driving license" — routed to general despite the user owning `Driving licence.pdf`. The filenames supply the context a human reader would have had, while "how long are driving licences valid in the UK?" still correctly routes to general.
- **Retrieval** — embeds the question and searches Qdrant, filtered server-side by `user_id` so one user's query can never touch another user's chunks.
- **Generation** — answers strictly from the retrieved context on the `retrieval` path, or converses normally on the `general` path. Receives recent conversation history, so follow-ups like "check that again" work.
- **Validator** — an independent second LLM call ("LLM-as-judge") that fact-checks the generated answer against the same retrieved chunks. If it can't confirm the answer is grounded, the answer is returned with an explicit disclaimer rather than presented as fact.

All four agents share a single model. Splitting the cheap Router onto a smaller model would spread load across two independent rate-limit budgets, but measured traffic at this scale never approaches those limits — so the split would add a config knob and a failure mode to solve a problem that doesn't exist yet.

### Retrieval design

Retrieval deliberately does **not** filter by a similarity-score threshold. Measured on real data with this embedding model, cosine similarity did not separate relevant from irrelevant content: an unrelated control query scored `0.495` while a genuinely relevant chunk scored `0.455`. No threshold value can split those. Instead the pipeline retrieves generously (top 20) and lets the LLM do relevance judgement in Generation and Validator, which it does far better at this scale.

This suits the project's scope — a handful of personal documents per user. At corpus sizes in the hundreds or thousands of chunks it would need a stronger embedding model or a reranking step instead.

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Streamlit | Chosen over React to keep focus on backend/AI engineering |
| Backend | FastAPI + Pydantic | JWT auth (python-jose), bcrypt password hashing |
| Agents | LangGraph | `StateGraph` with a conditional edge on the Router's decision |
| LLM | Groq — `openai/gpt-oss-120b` | Configurable via `GROQ_MODEL` |
| Embeddings | fastembed — `BAAI/bge-small-en-v1.5` (384-dim) | ONNX-based; chosen over PyTorch-based alternatives to keep the dependency footprint small |
| Vector store | Qdrant | Cosine distance, server-side `user_id` filtering |
| Database | PostgreSQL + SQLAlchemy + Alembic | Versioned schema migrations |
| PDF text | PyMuPDF | Also detects whether a PDF is scanned |
| OCR | Tesseract (pytesseract) | Pages rendered at 300 DPI before OCR |
| File storage | Local disk behind an abstraction | Swappable to S3 without touching business logic |
| Infra | Docker Compose | Postgres, Qdrant, Adminer |
| Tests | pytest | 66 tests; LLM calls mocked so the suite never spends API quota |
| CI | GitHub Actions | Runs the full suite against a real Qdrant service container |

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/register` | Create an account |
| `POST` | `/auth/login` | Get a JWT access token |
| `GET` | `/auth/me` | Current user |
| `POST` | `/documents/upload` | Upload and index a PDF |
| `GET` | `/documents` | List your uploaded documents |
| `DELETE` | `/documents/{id}` | Delete a document — its file, its metadata and its indexed chunks |
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

An **Elastic IP** is attached so the public address survives stop/start cycles — an auto-assigned address is only stable while the instance keeps running, which would have made the demo link above go stale.

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

66 tests covering chunking, embeddings, PDF extraction, OCR, storage, JWT/password security, PDF validation, all four agents, document deletion across all three data stores, and the full graph wiring.

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

- **LLM rate limits.** Runs on Groq's free tier: 200K tokens/day and 8K tokens/minute. A document question costs roughly 3,600 tokens, because Generation and the Validator each read the retrieved chunks. Sustained use can exhaust the daily budget, and a question against a large document — where all 20 retrieved chunks come back full — can approach the per-minute ceiling. A paid tier removes both; short of that, the lever is sending the Validator a trimmed chunk set rather than the full one.
- **Retrieval doesn't scale to large corpora.** The retrieve-generously strategy described above is right for a handful of documents per user, but would need a reranking step at much larger scale.
- **No HTTPS.** The deployment serves plain HTTP on its EC2 public IP, so credentials travel unencrypted. Fixing it properly means a domain name and a TLS certificate, since certificates aren't issued for bare IP addresses.
