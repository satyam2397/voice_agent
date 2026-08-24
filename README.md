# Real-Time Sales Co-Pilot

An independent, from-scratch project: an agentic AI system that listens to a live sales
conversation, decides moment by moment whether it can help, and pushes short data-grounded
"flash card" nudges to the sales rep. It never speaks, never joins the call, and stays
silent most of the time.

Domain is mutual fund distribution. All fund and distributor data is synthetic — no
employer code, data, or IP.

**Scope framing:** a small/demo-scale system built with production-quality *practices*, not
a claim of production-scale infrastructure. Where something is designed-for-scale vs.
actually measured, that distinction is stated explicitly (`DESIGN.md` §14).

## Documents

| File | What it is |
|---|---|
| **`DESIGN.md`** | Source of truth — architecture, decisions, rationale |
| **`TODO.md`** | Ordered build plan with checkable milestones |
| `backend/app/classifier/LABEL_SCHEMA.md` | Classifier label schema and annotation rules |
| `sales-copilot-project-spec.md` | ⚠️ Superseded; kept for history only |

The rep visits the distributor in person, sets one device on the table, and taps record.
A single mic captures both voices.

## Pipeline

```
One device, one mixed stream → AudioWorklet → WebSocket
   → VAD (drop silence) → Deepgram STT + diarization → role resolution
   → DistilBERT trigger classifier
   → [~15% of turns] context assembly → agent + MCP tools
   → flash card streamed back to the rep
```

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript, `getUserMedia` + AudioWorklet |
| VAD | Silero (server-side) |
| STT + diarization | Deepgram (single provider — diarization is load-bearing) |
| Trigger classifier | Fine-tuned DistilBERT, two heads (trigger + category) |
| LLM | Swappable — Ollama local for dev, `claude-opus-5` for demo |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| Vector store | Swappable — pgvector primary |
| Database | PostgreSQL |
| Queue | Redis + RQ |
| Backend | FastAPI |
| Tool calling | MCP — one server per tool |
| Orchestration | Hand-rolled agent loop, not LangChain/LangGraph |
| Observability | OpenTelemetry + Arize Phoenix |
| Evals | RAGAS (retrieval) + DeepEval (trigger + card quality) |

Rationale for each choice is in `DESIGN.md` §13.

## Status

Early. Scaffolding exists; the pipeline does not yet run end to end.
See `TODO.md` — currently at **Phase 0 / Phase 1**.

## Quickstart

Phase 1 needs **no Docker, no Postgres, no Redis** — just two terminals.

```bash
# one-time — always a venv, never system/Anaconda Python
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-min.txt

cd ../frontend && npm install
```

```bash
# terminal 1
cd backend && ./.venv/bin/python -m uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev
```

Open http://localhost:5173 and press **Start listening**.

Verify the wire without a browser: `cd backend && ./.venv/bin/python scripts/ws_smoke.py`

Backend health: http://localhost:8000/health

> `requirements.txt` is the full stack (torch, phoenix, ragas, deepeval) and is
> not needed until Phase 4. `requirements-min.txt` is what runs today.

## Repo layout

```
DESIGN.md                       # architecture + rationale
TODO.md                         # build plan
backend/
  app/
    main.py                     # FastAPI + WebSocket endpoints
    config.py                   # env-driven settings
    db/                         # SQLAlchemy models + session
    classifier/                 # DistilBERT: schema, data gen, training
    orchestrator/               # agent loop, LLM + MCP clients
    mcp_servers/                # one file per tool server
    eval/                       # eval harness
  tests/
    test_tenant_isolation.py    # concurrent-session leak test
frontend/                       # React: capture, transcript, flash cards
data/synthetic/                 # synthetic fund + distributor generators
docker-compose.yml
```
