# Progress Log

## Session 1 — 2026-08-03

### Built
- Project scaffolding: `app/` folder, `.env` / `.env.example`, `.gitignore`, `README.md`, `PROGRESS.md`
- `docker-compose.yml` defining `postgres` (16-alpine) and `qdrant` (latest) services, each with a named volume for persistence and a healthcheck (Postgres only — Qdrant has no built-in healthcheck endpoint suited for this yet)
- Generated a random `JWT_SECRET_KEY` into `.env`

### Working
- Not yet verified this session — containers not started yet

### Next
- Verify both containers are up and reachable (Postgres via connection check, Qdrant via HTTP API)
- Scaffold FastAPI app skeleton (`app/main.py`, config loading from `.env`)

## Session 2 — 2026-08-06

### Built
- `docker compose up -d` run by user: `docintel-postgres` (healthy) and `docintel-qdrant` both up, ports 5432/6333 reachable
- Fixed a secrets leak: real `GROQ_API_KEY` had ended up in `.env.example` (the file meant for git, not gitignored); moved it to `.env` only
- FastAPI app skeleton: `app/config.py` (typed settings loaded from `.env` via pydantic-settings, fails fast if required vars are missing) + `app/main.py` (`/health` endpoint)
- `requirements.txt` (fastapi, uvicorn, pydantic-settings) installed into a local `.venv`

### Working
- Verified `uvicorn app.main:app` starts and `GET /health` returns 200 with real config values (groq_model, storage_backend)

### Next
- Set up storage abstraction layer (local backend first, S3-compatible interface)
- JWT auth: register/login endpoints, password hashing, token issuing/verification

## Session 3 — 2026-08-06

### Built
- `app/database.py`: SQLAlchemy engine + session factory (`SessionLocal`) + `Base` for models, `get_db()` dependency
- `app/models.py`: four tables — `User`, `ChatSession`, `Message`, `DocumentMetadata` — with UUID primary keys, foreign keys linking them, and `cascade="all, delete-orphan"` so deleting a user cleans up their sessions/documents
- Alembic initialized (`alembic/`), `env.py` wired to pull the DB URL from our own `Settings` (not duplicated in `alembic.ini`) and to use `Base.metadata` for autogenerate
- Added `sqlalchemy`, `psycopg2-binary`, `alembic` to `requirements.txt`

### Working
- Generated first migration (`create initial tables`), reviewed the SQL before applying, ran `alembic upgrade head`
- Verified via `docker exec docintel-postgres psql -U docintel -d docintel -c '\dt'`: all four tables + `alembic_version` exist in the real database

### Next
- JWT auth: register/login endpoints, password hashing, token issuing/verification

## Session 4 — 2026-08-06

### Built
- `app/storage/base.py`: `StorageBackend` abstract interface (`save`, `get`, `delete`, `exists`) — business logic will depend only on this, never on a concrete backend
- `app/storage/local.py`: `LocalStorage` implementation — writes to `./storage`, generates random UUID filenames (avoids collisions and path-traversal from untrusted filenames)
- `app/storage/__init__.py`: `get_storage()` factory reading `STORAGE_BACKEND` from `.env` and returning the right implementation — this is the single swap point for adding S3 later
- Added `pytest` to `requirements.txt`, `pytest.ini` (`pythonpath = .`, needed because pytest doesn't auto-add the project root to the import path)
- `tests/test_storage.py`: two tests covering save/get/exists/delete and filename-collision avoidance, using pytest's `tmp_path` fixture for isolation

### Working
- `pytest tests/ -v` → 2 passed

### Next
- JWT auth: register/login endpoints, password hashing, token issuing/verification

## Session 5 — 2026-08-06

### Built
- `app/security.py`: bcrypt password hashing (`hash_password`/`verify_password` via `passlib`) + JWT creation/decoding (`create_access_token`/`decode_access_token` via `python-jose`), reading `JWT_SECRET_KEY`/`JWT_ALGORITHM`/`JWT_EXPIRE_MINUTES` from settings
- `app/schemas.py`: `UserCreate` (email + min-8-char password), `UserOut` (id + email only, never the password hash), `Token` (access_token + bearer type)
- `app/dependencies.py`: `get_current_user` — extracts and validates the JWT from the `Authorization` header, looks up the user, powers the "Authorize" button in `/docs`
- `app/routers/auth.py`: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`; wired into `app/main.py` via `app.include_router(auth.router)`
- Added `passlib[bcrypt]`, `python-jose[cryptography]`, `python-multipart`, `email-validator` to `requirements.txt`
- Pinned `bcrypt==4.0.1` — newer bcrypt versions removed an attribute passlib's version-detection code depends on, which broke hashing entirely until pinned

### Working
- `pytest tests/test_security.py -v` → 3 passed (hash/verify round-trip, valid token round-trip, tampered-token rejection)
- Manually verified live end-to-end via curl against the running app + real Postgres: register → login (got real JWT) → `/auth/me` with valid token (200, correct user) → `/auth/me` with no token (401) → login with wrong password (401). Test user then deleted from the database.

### Next
- Wire document upload: an endpoint that takes a PDF, saves it via `get_storage()`, and records a `DocumentMetadata` row
- PDF text extraction: PyMuPDF for searchable PDFs, PaddleOCR for scanned PDFs

## Session 6 — 2026-08-06

### Built
- `app/schemas.py`: added `DocumentOut` (id, filename, content_type, num_pages, ocr_used, uploaded_at — num_pages/ocr_used stay empty until text extraction is built)
- `app/config.py` / `.env` / `.env.example`: added `MAX_UPLOAD_SIZE_MB` (default 20)
- `app/validation.py`: `is_valid_pdf()` — checks the real file bytes start with `%PDF`, not just the declared content-type, so a renamed non-PDF file gets rejected
- `app/routers/documents.py`: `POST /documents/upload` — requires login, rejects non-PDF content-type, rejects oversized files, rejects files that fail the real-PDF check, saves via `get_storage()`, creates a `DocumentMetadata` row; wired into `app/main.py`

### Working
- `pytest tests/test_validation.py -v` → 3 passed (valid PDF accepted, garbage rejected, fake-.exe-renamed-to-.pdf rejected)
- Manually verified live end-to-end via curl: no-auth upload → 401; upload with real content that fails the PDF check → 400; valid PDF upload → 201 with correct metadata. Confirmed the saved file exists on disk with its random UUID name, and the `document_metadata` row in Postgres matches (`storage_path` points at the real file). Test data cleaned up afterward.

### Next
- PDF text extraction: PyMuPDF for searchable PDFs, detect scanned vs. searchable, PaddleOCR fallback for scanned PDFs

## Session 7 — 2026-08-07

### Built
- `app/extraction.py`: `extract_text()` opens a PDF with PyMuPDF (`fitz`), pulls text page by page, counts pages, and flags `is_scanned` via a heuristic (average chars/page below a threshold ⇒ likely image-only)
- `app/models.py`: added `is_scanned` (nullable bool) to `DocumentMetadata`, kept separate from `ocr_used` on purpose — `is_scanned` = detected as needing OCR, `ocr_used` = OCR actually ran (still always `False`, since the OCR pipeline doesn't exist yet)
- New migration `add_is_scanned_to_document_metadata`, reviewed and applied
- `app/schemas.py`: `DocumentOut` now includes `is_scanned`
- `app/routers/documents.py`: upload endpoint now runs extraction right after the PDF-content check and before saving; a PDF that fails to open (corrupt despite passing the earlier magic-bytes check) is rejected with 400 before anything is written to disk or the database
- Added `pymupdf` to `requirements.txt`

### Working
- `pytest tests/test_extraction.py -v` → 3 passed (searchable PDF correctly detected, blank/no-text PDF correctly flagged as scanned, corrupt PDF raises) — test PDFs generated on the fly with PyMuPDF itself, no external fixture files needed
- Full suite: `pytest tests/ -v` → 11 passed
- Manually verified live: uploaded a real generated searchable PDF (`is_scanned: false`, `num_pages: 1`) and a blank PDF (`is_scanned: true`, `num_pages: 1`) against the running app + real Postgres. Test data cleaned up afterward.

### Next
- OCR fallback: PaddleOCR for documents where `is_scanned` is true, Tesseract as backup if PaddleOCR is too resource-heavy
- Chunking: split extracted text into overlapping pieces suitable for embedding
- Embeddings: store chunks in Qdrant, linked back to the source document

## Session 8 — 2026-08-07

### Attempted: PaddleOCR
- Installed `paddlepaddle` + `paddleocr`, hit and fixed a chain of real environment issues in order: (1) `paddlepaddle==2.6.2` has no Python 3.13 build, moved to `3.3.1`; (2) PaddleOCR 3.x needs the `paddlex[ocr]` extra, not installed by default; (3) OpenCV (a PaddleOCR dependency) needs system graphics libraries not present on this headless machine — `libgl1`, then `libglib2.0-0`/`libsm6`/`libxext6`/`libxrender1` (all installed via `sudo apt-get`, run by the user); (4) hit a genuine PaddlePaddle bug (`NotImplementedError` in its CPU inference optimizer/oneDNN path) — worked around by disabling `enable_mkldnn`
- With mkldnn disabled, OCR worked correctly (verified against a real generated image) but took **~90 seconds for a single small image** — impractical for a real API, and likely worse on weaker AWS free-tier hardware
- Decision: dropped PaddleOCR entirely (uninstalled `paddleocr`/`paddlepaddle`/`paddlex`) in favor of Tesseract — this is exactly the fallback scenario the original project plan anticipated ("Tesseract as backup if PaddleOCR is too resource-heavy on free-tier hardware")

### Built
- Tesseract system binary installed (`sudo apt-get install -y tesseract-ocr`, run by the user)
- `app/ocr.py`: `run_ocr()` renders each PDF page to a 300-dpi image via PyMuPDF, then runs `pytesseract.image_to_string()` (a thin wrapper around the real `tesseract` CLI) on each page
- `app/routers/documents.py`: upload endpoint now runs OCR when extraction detected `is_scanned=True`; sets `ocr_used=True` only if OCR actually completes without error — a failed OCR attempt doesn't block the upload, the document is just saved still flagged as not-yet-OCR'd
- Added `pytesseract`, `pillow` to `requirements.txt`; removed `paddlepaddle`/`paddleocr`

### Working
- `pytest tests/test_ocr.py -v` → 2 passed (real text correctly read back, blank page returns empty)
- Full suite: `pytest tests/ -v` → 13 passed
- Manually verified live: built a genuinely image-only PDF (text drawn as pixels via PIL, embedded as an image with no text layer — a real simulation of a scanned document, not just an empty page), uploaded it against the running app + real Postgres: correctly detected as `is_scanned: true`, OCR ran and set `ocr_used: true`, whole upload+OCR round-trip took ~0.6 seconds. Test data cleaned up afterward.

### Next
- Chunking: split extracted text (from both the PyMuPDF path and the OCR path) into overlapping pieces suitable for embedding
- Embeddings: store chunks in Qdrant, linked back to the source document

## Session 9 — 2026-08-07

### Built
- `app/chunking.py`: `chunk_text()` — word-aware sliding-window chunker with overlap (default 1000 chars/chunk, 200 chars overlap, both configurable via `CHUNK_SIZE`/`CHUNK_OVERLAP` in `.env`); breaks only on word boundaries, never mid-word
- Deliberately **not** wired into the upload endpoint yet — there's nowhere to persist chunks until embeddings/Qdrant storage exists (next session); today's scope is a standalone, tested capability only

### Working
- `pytest tests/test_chunking.py -v` → 5 passed: empty input, short text (single chunk), long text (multiple chunks of the expected size), consecutive chunks genuinely overlap, and no word is ever split or dropped across the full chunk set
- Full suite: `pytest tests/ -v` → 18 passed

### Next
- Embeddings: convert chunks into vectors and store them in Qdrant, linked back to the source document — this is also where `chunk_text()` actually gets called for real, during upload, using text from both the PyMuPDF path and the OCR path

## Session 10 — 2026-08-07

### Built
- Chose `fastembed` (Qdrant's own lightweight embedding library, ONNX-based, no PyTorch) over `sentence-transformers` — deliberate choice given today's PaddleOCR dependency pain; confirmed a clean install and fast inference (0.05s for 2 chunks) before committing to it
- `app/embeddings.py`: `embed_texts()` — wraps fastembed's `TextEmbedding` (default model `BAAI/bge-small-en-v1.5`, 384-dim), cached as a singleton so the model loads once per process, not per call
- `app/vector_store.py`: `ensure_collection()` (creates the Qdrant collection once, idempotent) and `upsert_chunks()` (embeds chunks and stores them as Qdrant points, tagged with `document_id`/`user_id`/`chunk_index`/`text`; point IDs are deterministic via `uuid5(document_id, chunk_index)` so reprocessing a document overwrites rather than duplicates)
- `app/models.py`: added `is_indexed` to `DocumentMetadata`, mirroring the `ocr_used` pattern — true only once chunks are actually embedded and stored
- Migration `add_is_indexed_to_document_metadata` — hit and fixed a real Postgres constraint issue: adding a `NOT NULL` column to a table with existing rows requires `server_default` so Postgres knows how to backfill those rows (this project's own test uploads from earlier sessions), not just a Python-level default
- `app/routers/documents.py`: upload endpoint now generates the document's ID upfront (`uuid.uuid4()`), extracts/OCRs raw text (previously discarded, now actually used), chunks it, embeds and stores it in Qdrant, and only then creates the `DocumentMetadata` row — all sharing one consistent ID from the start. Indexing failure doesn't block the upload, same non-fatal-degrade pattern as OCR.
- Added `fastembed`, `qdrant-client` to `requirements.txt`; had to pin `pillow==10.4.0` (fastembed requires <11.0, conflicting with the version pinned during the OCR session)

### Working
- `pytest tests/test_embeddings.py -v` → 3 passed, including a semantic check (two similar sentences embed closer together than an unrelated one — proof the model captures real meaning, not just "runs without crashing")
- Full suite: `pytest tests/ -v` → 21 passed
- Manually verified live end-to-end: uploaded a real PDF against the running app + real Postgres + real Qdrant, got `is_indexed: true`, then queried Qdrant's REST API *directly* (bypassing our own app entirely) and confirmed the chunk actually exists there with correct `document_id`/`user_id`/`chunk_index`/text. Test data cleaned up from Postgres, local storage, and Qdrant afterward.

### Next
- Groq LLM client wrapper — thin service for sending prompts to Groq and getting completions
- LangGraph agents: Router, Retrieval (searches Qdrant), Answer Generation, Validator
- Chat persistence: save queries/responses into `chat_sessions`/`messages`

## Session 11 — 2026-08-07

### Built
- `app/llm.py`: `get_completion()` — thin wrapper around the official `groq` SDK, builds a standard chat-completion message list (optional system prompt + user prompt) and returns just the plain text answer
- Added `groq` to `requirements.txt`
- Deliberately **not** writing automated tests that call the real Groq API — free tier is rate/quota limited (~30 req/min, 1000/day), so hitting it on every `pytest` run would silently burn quota. Verified manually instead (see below), same principle as Postgres/Qdrant.

### Working
- Live manual call: `get_completion("Reply with exactly the words: Groq integration works.")` → returned exactly that, confirming the real API round-trip works
- `tests/test_llm.py`: 2 mocked tests (no real API calls, no quota used) verifying *our* message-construction logic — correct message list with/without a system prompt, and correct extraction of the response text
- Full suite: `pytest tests/ -v` → 23 passed

### Next
- LangGraph agents: Router (decides how to handle a query), Retrieval (searches Qdrant using `app.vector_store`), Answer Generation (uses `app.llm` + retrieved context), Validator (checks the generated answer)
- Wire the four agents into a single LangGraph workflow
- Chat persistence: save queries/responses into `chat_sessions`/`messages`

## Session 12 — 2026-08-07

### Built
- `app/vector_store.py`: added `search_chunks()` — embeds a query and searches Qdrant, filtered server-side to one user's own chunks via `Filter(must=[FieldCondition(key="user_id", ...)])`; kept consistent with `upsert_chunks()` by accepting raw text and handling embedding internally, not requiring callers to embed first
- `app/agents/` package created; `app/agents/retrieval.py`: the Retrieval agent — currently a thin, deliberate wrapper around `search_chunks()`, kept as its own module (separate from the Qdrant mechanics in `vector_store.py`) since this is the function that becomes a LangGraph node later
- `tests/test_retrieval.py`: first automated pytest test touching the real, live Qdrant service directly (previous Qdrant work was only manually verified) — justified because user-data isolation is a real security property worth a repeatable automated check, not just a one-off manual test. Uses a pytest fixture to insert real test data for two different fake users and clean it up afterward.

### Working
- `pytest tests/test_retrieval.py -v` → 2 passed: retrieval finds the right user's own relevant chunk, and — the critical one — a second user's semantically-matching query never returns another user's chunks, proving the isolation happens at the database filter level, not just relevance ranking
- Full suite: `pytest tests/ -v` → 25 passed
- Manually verified against real data: queried "Who is the CEO and what company did Jeevan work for?" against the real previously-uploaded experience letter (still sitting in Qdrant from earlier manual testing) — correctly retrieved the right chunk (mentions PiHex Labs, Sumit Jha CEO) with a 0.641 similarity score, proving genuine semantic search (no keyword overlap with the query) works end-to-end against real data

### Next
- Router agent: decide how to handle an incoming query
- Answer Generation agent: use `app.llm` + retrieved chunks from the Retrieval agent to produce a real answer
- Validator agent: check the generated answer before returning it
- Wire all four agents into a single LangGraph workflow
- Chat persistence: save queries/responses into `chat_sessions`/`messages`

## Session 13 — 2026-08-08

### Built
- `app/agents/router.py`: Router agent — asks the LLM to classify a query as `retrieval` or `general`, defaults to `general` on any unexpected response
- `app/agents/generation.py`: Answer Generation agent — bundles retrieved chunks into a labeled context block, instructs the LLM to answer only from that context and admit uncertainty rather than guess
- `app/agents/validator.py`: Validator agent — a second, independent LLM call fact-checks the generated answer against the same context ("LLM-as-judge"); on failure, prepends an honest disclaimer rather than hiding or silently accepting the answer
- `app/graph.py`: wired all four agents into an actual LangGraph `StateGraph` — router branches (via `add_conditional_edges`) to either the retrieval path or straight to generation for general chat; `run_agent_pipeline()` is the single entry point
- `app/routers/chat.py` + schema additions: real endpoints — `POST/GET /chat/sessions`, `POST/GET /chat/sessions/{id}/messages`. Sending a message persists the user's message, runs the full agent pipeline, persists the assistant's answer, and returns it. Session ownership checks return 404 (not 403) for another user's session, to avoid revealing whether it exists.
- Added `langgraph` to `requirements.txt`

### Working
- 8 mocked tests (router/generation/validator agents) + 2 mocked graph-wiring tests, all with zero real API calls — full suite: `pytest tests/ -v` → 35 passed
- One real, live, full end-to-end run: register → upload → create chat session → ask a real question → real Router/Retrieval/Generation/Validation pipeline executes → answer persisted in Postgres. Confirmed via direct SQL query that both the user's question and the assistant's answer are stored correctly.
- **A genuine finding, not a bug**: the first real test PDF had its text silently truncated by PyMuPDF's `insert_text()` (a single-line method with no wrapping) — extraction/chunking/retrieval all correctly handled the resulting incomplete text, and Generation correctly said "I don't have enough information" rather than guessing, exactly as instructed
- **A second genuine finding**: with a properly-wrapped, complete test PDF, the Validator still flagged the answer as unverified. Investigated by reproducing with the exact real retrieved context and exact real generated answer — found the Generation step had subtly misattributed a "15% increase" figure (which applied to total revenue in the source) to a different figure (the growth-driver's dollar contribution) due to sentence reordering. The Validator correctly caught this real, subtle grounding error. Conclusion: the Validator agent is working as intended, not malfunctioning — a good concrete demonstration of why that step exists in the pipeline.
- Test data cleaned up from Postgres, local storage, and Qdrant afterward

### Next
- Streamlit frontend: login/register screens, document upload + list, chat interface
- Broaden test coverage as the frontend surfaces more real usage patterns
- GitHub Actions CI (per the plan: added once core code exists — it now does)

## Session 14 — 2026-08-08

### Fixed (4 issues raised in review)
- **General chat gap**: `generate_answer()` now takes the Router's actual `route` ("general" vs "retrieval"), not just "are chunks empty?" — needed because empty chunks means two different things: general chat (no documents needed) vs. a document question where nothing relevant enough was found. General chat now gets a normal conversational system prompt with no fake "context" wrapper; document questions keep the strict grounded-answer behavior either way. `graph.py`'s `generation_node` updated to pass `state["route"]` through.
- **Retrieval relevance**: added `retrieval_score_threshold` (default 0.5, configurable via `.env`) to `search_chunks()` — Qdrant's native `score_threshold` param on `query_points()`, so weak/irrelevant matches are excluded server-side instead of always returning the "closest available" result regardless of how weak.
- **Orphaned messages on pipeline failure**: `chat.py`'s `send_message` now wraps `run_agent_pipeline()` in try/except — if Groq fails partway through (outage, rate limit, network error), the user's question still gets a real saved reply (an honest "something went wrong" message) instead of the endpoint crashing with an unhandled 500 and leaving the question with no answer ever recorded.
- **Router/Validator consistency**: added a `temperature` parameter to `get_completion()` (default 0.7, unchanged for Generation); Router and Validator now explicitly pass `temperature=0.0` since their yes/no-style decisions should be consistent run-to-run, not creative.

### Working
- Added/updated tests for all four fixes, including direct regression tests that would have failed against the old code: `test_general_route_has_normal_conversation_not_document_prompt`, `test_search_filters_out_weak_matches_via_score_threshold`, temperature-assertion tests for both Router and Validator. Full suite: `pytest tests/ -v` → 39 passed.
- Live-verified all three chat scenarios together in one session: general chat now responds naturally ("I'm doing great, thanks for asking..."), an unrelated document question correctly stays in "I don't have that information" mode rather than switching to chit-chat (proving the route-based distinction works), and a real document question still gets an accurate grounded answer.
- Test data cleaned up from Postgres and Qdrant afterward (left the user's own real experience-letter document untouched in Qdrant, as before).

### Next
- Streamlit frontend: login/register screens, document upload + list, chat interface
- Broaden test coverage as the frontend surfaces more real usage patterns
- GitHub Actions CI (per the plan: added once core code exists — it now does)

## Session 15 — 2026-08-08

### Built — answer transparency (`source` field)
- Identified a real gap while explaining the pipeline: a question with no document framing (e.g. "What is the capital of France?") gets classified `general` by the Router and is legitimately answered from the LLM's own general knowledge — correct behavior, but the API gave no way to tell that apart from a document-grounded answer
- `app/graph.py`: added `_determine_source(route, chunks)` — a small pure function returning `"general_knowledge"`, `"documents"`, or `"no_relevant_documents"`; wired into `generation_node`, added `source` to `GraphState`
- `app/models.py`: added `source` (nullable) to `Message` — only set for assistant messages; migration `add_source_to_messages` reviewed and applied (nullable, no backfill issue this time since existing rows just get NULL)
- `app/routers/chat.py`: persists and returns `source`; the pipeline-failure fallback path now sets `source="error"` so even failure responses are honestly labeled
- `app/schemas.py`: `MessageOut` includes `source: str | None`

### Working
- `_determine_source` unit tests (pure logic, no LLM/DB) + updated graph tests asserting `source` on both routing paths + a new test for the "retrieval but nothing relevant found" case — full suite: `pytest tests/ -v` → 43 passed
- One flaky, non-reproducing failure observed in `test_security.py::test_tampered_token_is_rejected` during a single full-suite run — passed in isolation and on a second full-suite rerun; unrelated to any file touched this session, noted for awareness rather than acted on
- Live-verified all three real scenarios end-to-end plus history retrieval: `"What is the capital of France?"` → `general_knowledge`; a real question about the uploaded PDF → `documents`; an unrelated document question → `no_relevant_documents`. Confirmed `GET /chat/sessions/{id}/messages` correctly shows `source: null` for user messages and the correct label for each assistant reply. Test data cleaned up from Postgres and Qdrant (real experience-letter document left untouched).

### Next
- Streamlit frontend: login/register screens, document upload + list, chat interface — this is also a natural place to visually surface the `source` label per message
- Broaden test coverage as the frontend surfaces more real usage patterns
- GitHub Actions CI (per the plan: added once core code exists — it now does)

## Session 16 — 2026-08-08

### Built — Streamlit frontend
- `app/routers/documents.py`: added `GET /documents` — listing a user's own uploaded documents was missing (only upload existed); needed so the frontend has something to show in a document list view
- `frontend/api_client.py`: thin `requests`-based wrapper around every backend endpoint (register, login, list/upload documents, list/create chat sessions, list/send messages) — no business logic duplicated, it only calls the existing FastAPI API
- `frontend/app.py`: the actual UI —
  - Login/Register screen (two tabs), token kept in `st.session_state`
  - **Documents tab**: PDF uploader + a table of the user's uploaded documents (filename, pages, scanned, OCR used, indexed, uploaded at)
  - **Chat tab**: session picker + "new chat" creation, `st.chat_message`/`st.chat_input` for a real chat UI, with each assistant reply showing a small caption badge for its `source` (📄 from your documents / 🧠 general knowledge / ⚠️ no relevant documents found / ❌ error) — directly surfacing the transparency work from Session 15
- Added `streamlit` and `requests` to `requirements.txt`

### Working
- No automated endpoint tests added for `GET /documents`, consistent with this project's established pattern (no FastAPI `TestClient` integration tests exist anywhere — Postgres/Qdrant-backed endpoints are verified live, not mocked)
- Verified `GET /documents` live against a throwaway test user (returned `[]` for a fresh account as expected), then deleted that test user
- Launched the backend (`uvicorn`) and the frontend (`streamlit run frontend/app.py`) together locally; confirmed both serve traffic (`/health` 200, Streamlit page 200)
- Handed off to the user to click through the real flow in-browser (register/login, upload a PDF, chat with source badges visible per message) rather than only asserting it from the terminal

### Next
- Incorporate whatever the user finds while clicking through the Streamlit app themselves
- Broaden test coverage as the frontend surfaces more real usage patterns
- GitHub Actions CI (per the plan: added once core code exists — it now does)
- AWS EC2 deployment, after billing alerts are set up first (per the original plan)

## Session 17 — 2026-08-08

### Fixed — frontend UX bugs found via real usage, then a real conversational-memory gap
- Found while clicking through the app: `st.chat_input` doesn't auto-pin to the bottom of the page when placed inside `st.tabs` (a Streamlit limitation), and the old code additionally printed each new exchange manually right after the input instead of refreshing history — the two combined made new messages appear to render "in the middle" of the conversation. Fixed in `frontend/app.py`: sending a message now just calls `send_message()` then `st.rerun()`, so the full conversation (already including the new turn, now persisted in Postgres) re-renders as one consistent list above the input every time.
- Found via real testing: the assistant had no memory of earlier messages in the same chat session — e.g. asking "what's my name?" right after introducing yourself got "I don't know, we just started chatting." Root cause: `run_agent_pipeline()` only ever received the current query; nothing read prior messages back out of Postgres and fed them to the LLM, even though they were already being stored correctly.

### Built — conversation history
- `app/llm.py`: `get_completion()` takes an optional `history` list of prior `{role, content}` turns, inserted between the system prompt and the current message
- `app/agents/router.py` / `app/agents/generation.py`: both accept and forward `history` down to `get_completion()` — Router uses it to correctly classify context-dependent follow-ups ("check that again"), Generation uses it to stay consistent with earlier turns
- `app/graph.py`: added `history` to `GraphState`; `run_agent_pipeline()` takes a `history` argument threaded through the router and generation nodes (Validator intentionally left untouched — it only fact-checks the answer against retrieved chunks, not conversational consistency)
- `app/routers/chat.py`: `send_message()` now queries the last `MAX_HISTORY_MESSAGES` (10) messages for that session from Postgres *before* inserting the new user message, and passes them as `history` into the pipeline — this is the actual "read back what was already stored" step

### Fixed — a real (not flaky) test bug
- `test_security.py::test_tampered_token_is_rejected` had failed intermittently across two separate sessions. Root cause found: it tampered with the *last* character of the JWT string, but a base64-encoded string's final character can encode unused padding bits — toggling it sometimes decodes to the exact same underlying bytes, silently no-op'ing the tamper and letting the untampered signature verify successfully. Fixed by tampering a character in the middle of the token instead, which always changes real payload/signature bytes. Confirmed reliable across 5 repeated runs after the fix.

### Working
- Added/updated tests across `test_llm.py`, `test_router_agent.py`, `test_generation_agent.py`, `test_graph.py` asserting `history` is correctly threaded through every layer (including a default-to-empty-list case when no history is passed)
- Full suite: `pytest tests/ -v` → 49 passed
- Live end-to-end verification pending in-browser confirmation from the user (asking "what's my name?" after introducing themselves earlier in the same chat session)

### Next
- Confirm conversational memory works as expected in the live Streamlit app
- Broaden test coverage as the frontend surfaces more real usage patterns
- GitHub Actions CI (per the plan: added once core code exists — it now does)
- AWS EC2 deployment, after billing alerts are set up first (per the original plan)

## Session 18 — 2026-08-10

### Built — git, GitHub, and CI actually stood up
- Initialized the git repository for the first time (`git init`), confirmed `.gitignore` correctly excluded `.env`/`storage/`/`.venv`/logs, made the initial commit, created the `JeevanChevula/document-intelligence-platform` GitHub repo, and pushed.
- Hit and fixed a real permission issue: the first push was rejected because the GitHub Personal Access Token in use lacked the `workflow` scope needed to push `.github/workflows/ci.yml`. Fixed by editing the existing token's scopes on GitHub (no need to regenerate the token or touch local credentials) rather than working around it.
- **Found a genuine bug via CI itself, not local testing**: the very first GitHub Actions run failed on `ModuleNotFoundError: No module named 'app.storage'`. Root cause: `.gitignore`'s `storage/` rule (line 12, meant only for the top-level uploaded-files folder) matched *any* directory named `storage` anywhere in the repo, so it was silently also excluding `app/storage/` — real source code (`base.py`, `local.py`, `__init__.py`) that had never actually been committed. Fixed by anchoring the rule to the repo root (`/storage/`), then added and pushed the previously-missing files. This is exactly the kind of gap CI exists to catch — the code worked locally because the files were still sitting on disk uncommitted, so nothing local would have ever revealed this.
- Second CI run passed cleanly (49 tests, real Qdrant service container, dummy config values) — first genuinely green run.
- Added a lightweight **Adminer** service to `docker-compose.yml` (port 8081) — gives a browser-based table view for Postgres, mirroring Qdrant's own built-in dashboard (`localhost:6333/dashboard`), for inspecting stored documents/chat sessions/messages without writing SQL by hand.

### Fixed — local dev environment stability
- Diagnosed repeated Streamlit crashes during local testing: root cause was the laptop's total RAM (8GB) being nearly exhausted by Cursor + Chrome + Docker Desktop's GUI running simultaneously alongside the app — not a bug in the app itself. Mitigated by closing Docker Desktop's window (containers keep running headless) and reducing open browser tabs; a `.wslconfig` memory-limit increase was considered and correctly ruled out once Task Manager showed the *host* machine itself, not just WSL's allocation, was the actual bottleneck.

### Built — AWS account and first EC2 instance
- Created a new AWS account, deliberately selected the **Free Plan** (credits-based, services pause rather than charge once exhausted — not the Paid Plan) plus billing alerts, after working through the billing-safety questions in detail (a card is always required and can never be fully removed while the account is open, but Free Plan structurally prevents surprise charges).
- Launched one EC2 instance: region **ap-south-2 (Hyderabad)** for low latency from India, **Ubuntu Server 26.04 LTS**, instance type **t3.small (2GB RAM)** — chosen over the default 1GB `t3.micro` given the exact memory-pressure lessons just learned locally, 8GB gp3 root volume.
- Security group configured with three rules: SSH (port 22) restricted to the user's own IP only, plus two public rules (Custom TCP 8000 for the FastAPI backend, Custom TCP 8501 for Streamlit) open to `0.0.0.0/0` since recruiters/testers will connect from arbitrary networks.
- Connected via SSH (key pair `docintel-key.pem`, copied from the Windows-side `/mnt/c/...` path into WSL's own filesystem first, since strict key permissions don't work reliably from the Windows-mounted path directly), installed Docker (`docker.io`, `docker-compose-v2`), enabled it, added the `ubuntu` user to the `docker` group, then rebooted to clear a pending post-upgrade restart flag. Verified `docker ps` runs without needing `sudo`.

### Working
- CI: green, 49 tests passing on GitHub Actions
- EC2 instance: running, Docker installed and confirmed working
- Paused deliberately before continuing — no containers started on the instance yet, so nothing needed stopping; instance itself should be stopped from the AWS console between sessions to conserve free-tier credits

### Next
- Resume on EC2: note its public IP will very likely change on next start (no Elastic IP reserved yet) — re-check it before reconnecting
- Install Python + git on the instance, clone the GitHub repo onto it
- Recreate `.env` there securely (not via git)
- `docker compose up -d` for Postgres/Qdrant, then run the backend and Streamlit on the instance
- Test the deployed app via the instance's public IP in a browser
- Stop the instance when not actively testing/demoing
