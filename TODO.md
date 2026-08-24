# Build Plan

Ordered. Each phase has a **Done when** you can actually check.
Design rationale lives in `DESIGN.md` — this file is only *what to do next*.

Legend: `[ ]` todo · `[x]` done · ⚠️ known-broken existing code

---

## Phase 0 — Hygiene (do first, ~30 min)

Small things that block or hide everything else.

- [ ] `backend/pyproject.toml` with `asyncio_mode = "auto"`
      ⚠️ Without this, async tests **skip silently instead of failing** — which currently
      hides the tenant-isolation test
- [ ] `backend/tests/conftest.py` with a DB fixture
      ⚠️ `test_tenant_isolation.py` references `db_session_factory`, which doesn't exist
- [ ] Update `llm_client.py`: model → `claude-opus-5`
- [ ] `alembic init` + first migration from existing models
- [ ] Add `.env` key: `DEEPGRAM_API_KEY`

**Done when:** `pytest` runs and *reports* the isolation test as failing rather than skipping.

---

## Phase 1 — Frontend that listens ✅ DONE

A browser page that captures mic audio and streams it. No transcription yet.

- [x] Scaffold: Vite + React + TS (`frontend/`, Vite 5 pinned for Node 20.5)
- [x] `useAudioCapture` hook — `getUserMedia`, permissions, teardown
- [x] `public/audio-processor.js` AudioWorklet:
      - Float32 frames from the audio thread
      - resample any rate → 16 kHz (box-filter decimation, fractional-offset carry
        so 44.1 kHz doesn't drift)
      - convert to PCM16 little-endian
      - `postMessage` a ~200 ms buffer + a 50 ms level signal
- [x] `useConversationSocket` hook — binary frames, exponential-backoff reconnect
      - drops frames when `bufferedAmount` exceeds 512 KB
- [x] Record / stop control
- [x] Two-panel workspace: transcript left, flash cards right
- [x] Live level meter, connection status, bytes-sent, dropped-chunk counter
- [x] Backend `WS /ws/audio/{conversation_id}` — handshake validation, frame
      counting, stats push (Phase 2 replaces the body with VAD)
- [x] `scripts/ws_smoke.py` — end-to-end wire test, asserts frame integrity

⚠️ Placeholder transcripts are echoed so the UI wiring is visible before STT
exists. Turn off with `ECHO_FAKE_TRANSCRIPTS=false` once Phase 3 lands.

⚠️ Stats piggyback on inbound frames, so counters stop updating when audio
stops. Fine for now; revisit if you want a heartbeat.

**One device, one stream.** The rep sets the device on the table between them; a single mic
captures both voices. No role handshake, no session joining, no second client — speaker
separation happens server-side in Phase 3. See `DESIGN.md` §4.

**Laptop-first, responsive to phone.** Build against a laptop for iteration speed; keep the
layout responsive and avoid desktop-only APIs.

**Done when:** hitting record streams continuously, the level meter responds to both people
speaking across the table, and the byte counter climbs with no growth in `bufferedAmount`.

**Run it:**
```bash
# one-time
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-min.txt

# terminal 1
cd backend && ./.venv/bin/python -m uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev        # http://localhost:5173

# optional: verify the wire without a browser
cd backend && ./.venv/bin/python scripts/ws_smoke.py
```

⚠️ **Always use the venv.** Installing into system or Anaconda Python will
downgrade `uvicorn` / `websockets` / `starlette` / `pydantic-settings` out from
under anything else using them (langchain, langgraph, mcp).

**Sanity check:** `capture_ratio` in the `stream_close` log should be ~1.0 during
continuous speech. Well under 1.0 means chunks are being dropped or the worklet is
starved.

---

## Phase 2 — Silero VAD ⏭️ DEFERRED (now a cost optimization, not a blocker)

Originally sequenced before STT to find utterance boundaries. That reason went away:
turn boundaries come from Deepgram's endpointing (`DESIGN.md` §5), not VAD. What VAD
still buys is **not paying Deepgram to transcribe silence** — real, but an optimization
rather than a prerequisite.

Pick this up once transcription is verified working and you can measure the saving.

Receive the stream, gate silence. Transcription already works without it.

- [ ] `WS /ws/audio/{conversation_id}` accepting a JSON handshake
      (`sample_rate`, `encoding`) then binary frames
- [ ] Per-connection ring buffer; reject frames with a mismatched handshake
- [ ] Silero VAD over the buffer → speech / silence segmentation
- [ ] Structured logging on every event: `conversation_id`, duration, RMS level
- [ ] Drop silence — never forward it downstream

⚠️ VAD gives speech-vs-silence, **not turn boundaries**. On a mixed stream a pause is
ambiguous — mid-thought or speaker change. Turn boundaries arrive in Phase 3 from
Deepgram's endpointing. Don't try to infer them here.

**Done when:** speaking logs speech segments with sensible durations, silence logs nothing,
and the metered-STT byte count would be visibly lower than raw stream volume.

---

## Phase 3 — Speech to text + speaker separation ✅ BUILT (needs an API key to verify)

Single provider. One `stt.py` module owning Deepgram — no Protocol, no second
implementation (`DESIGN.md` §5). Raw WebSocket rather than `deepgram-sdk`: one fewer
dependency and no SDK version churn.

- [x] `stt.py` — Deepgram streaming client, `diarize=true`, native endpointing,
      keepalive, graceful failure
- [x] Split each result by diarized speaker — one Deepgram result can contain two
      speakers when people talk over each other, which happens constantly in person
- [x] Emit partials (UI only) and finals, speaker-labeled
- [x] `session.py` — **role resolver**: first time two voices are distinguished, prompt
      the rep with a sample of each and take a one-tap "that's me"
- [x] Retroactive relabeling — assigning roles rewrites already-rendered turns
- [x] Frontend: live transcript, interim styled distinctly, speaker attribution
- [x] Low `asr_confidence` surfaced in the UI rather than failing silently
- [x] STT failure degrades instead of halting — asserted in `scripts/ws_smoke.py`
- [ ] **Verify against real speech** — needs `DEEPGRAM_API_KEY`
- [ ] Allow role re-assignment mid-conversation (labels can swap after long silences)
- [ ] Persist final turns to `conversation_turns` (needs Postgres, deferred)

**Done when:** a two-person conversation across the table produces a live
speaker-attributed transcript and the rep assigns roles in one tap.

⚠️ Expect diarization to be weakest in the first ~15 seconds, before it has clustered
the voices. Test specifically for that.

⚠️ Not yet validated with real audio — everything above is verified by unit and wire
tests only. Far-field quality is still the biggest unknown (`DESIGN.md` §4).

---

## Phase 4 — Classifier: data → model

*Independent of Phases 1–3. Can run in parallel if you want two threads of work.*

Schema and rules: `backend/app/classifier/LABEL_SCHEMA.md`

- [ ] Generator script — batched across persona × fund type × conversation stage × register
- [ ] **50-row pilot first**; eyeball for template collapse before the full run
- [ ] Full generation (~2,800 rows, 4 splits, 25–30% hard-negative pairs, ASR-degraded
      fraction) — roughly $5–8 in API cost
- [ ] Schema validator — every row conforms to LABEL_SCHEMA §6
- [ ] **Hand-audit `test_natural`** (~150 rows); record generator error rate
- [ ] Fine-tune DistilBERT, two heads, class-weighted
- [ ] Threshold sweep on val against the cost asymmetry (`DESIGN.md` §6)
- [ ] Version + persist the checkpoint
- [ ] Replace `orchestrator/trigger_classifier.py` with the serving wrapper
      ⚠️ Current file is a keyword placeholder
- [ ] Rewrite `eval/run_evals.py`: precision/recall/F1, not accuracy
      ⚠️ Current metric scores ~85% for a do-nothing classifier
- [ ] Retire `eval/eval_set.jsonl`
      ⚠️ All 5 rows are keyword-separable — scores 100% by construction, can never
      detect a regression

**Done when:** a saved checkpoint produces precision/recall/F1 on `test_natural`, the
threshold is justified by the P/R curve rather than chosen, and the confusion matrix on
`test_balanced` looks sane.

---

## Phase 5 — Context assembly + agent

- [ ] Fix `mcp_client.py`
      ⚠️ `list_tool_schemas()` returns `[]` — the agent currently has **zero tools**
      ⚠️ `stdio_client(...).__aenter__()` without holding the context manager leaks
- [ ] Connect MCP servers once at app startup; hold sessions for the process lifetime
- [ ] **Tenant ID injection** — strip `distributor_id` from advertised tool schemas,
      inject from session context before dispatch (`DESIGN.md` §10)
- [ ] Implement `compare_funds` ⚠️ currently returns "not yet implemented"
- [ ] Context assembler: conversation window + profile + retrieval, fetched in parallel
- [ ] Category-driven tool routing (`DESIGN.md` §6)
- [ ] Wire classifier → assembler → agent as RQ workers
- [ ] Complete `data/synthetic/generate_data.py`
      ⚠️ Builds dicts but never inserts to Postgres; no document chunks, no embeddings

**Done when:** a triggering utterance produces a flash card grounded in real synthetic
data, and a `distributor_id` supplied in transcript text cannot influence which tenant's
data is fetched.

---

## Phase 6 — Flash card delivery

- [ ] Stream card tokens over WebSocket as generated
- [ ] `FlashCard` component — content, source attribution, trigger reason
- [ ] Persist to `flash_cards` with tokens and latency
- [ ] Cooldown + topic-dedup gates (orchestrator-level, not classifier)
- [ ] Distributor profile sidebar

**Done when:** speaking a triggering question into the distributor client makes a card
appear on the rep's screen, streaming, within the latency budget.

---

## Phase 7 — Memory

- [ ] `conversation_chunks` table + migration
- [ ] Post-conversation worker: summarize → `distributor_memory`
- [ ] Embed + store chunks, scoped by `distributor_id`
- [ ] Eviction: cap per distributor, oldest-first
- [ ] Retrieval path for `historical_reference` triggers

**Done when:** a second conversation with the same distributor can answer "what did we
discuss last time?" from stored chunks.

---

## Phase 8 — Reliability

Build and **demo** each of the six named failures in `DESIGN.md` §9.

- [ ] LLM timeout → backoff → graceful card
- [ ] DB unreachable → degrade, don't crash
- [ ] Malformed tool output → agent reports the gap, invents nothing
- [ ] Classifier uncertain → fail closed
- [ ] STT mid-stream failure → resume on reconnect
- [ ] WebSocket drop → reconnect with session intact
- [ ] One test per scenario

**Done when:** you can `docker compose stop postgres` mid-conversation and the system
degrades visibly instead of dying.

---

## Phase 9 — Observability

- [ ] structlog JSON, tenant IDs on every line
- [ ] OTel spans per stage: capture → VAD → STT → classify → assemble → agent → deliver
- [ ] Export to Phoenix
- [ ] Token + latency logging per card
- [ ] Turn the `DESIGN.md` §11 table from targets into measurements

**Done when:** one Phoenix trace shows a complete utterance-to-card journey with per-stage
timings.

---

## Phase 10 — Full eval harness

- [ ] RAGAS for retrieval quality
- [ ] DeepEval G-Eval for flash card quality
- [ ] Single `make eval` running the whole suite
- [ ] Record baseline numbers

**Done when:** `make eval` prints classifier, retrieval, and card-quality metrics, and
catches a deliberately degraded prompt.

---

## Phase 11 — Tenant isolation test (do early if you can)

- [ ] Rewrite around a canary token
      ⚠️ Current assertions (`not in`, `!=`) pass trivially and would not detect a leak
- [ ] Assert on the **assembled prompt and final card**, not the tool return value
- [ ] Run concurrently via `asyncio.gather`
- [ ] Add the deliberately-broken variant that **must fail**

**Done when:** the test catches a leak you introduce on purpose, then passes once fixed.

---

## Phase 12 — Scale validation and write-up

- [ ] Seed 10k–100k rows; `EXPLAIN ANALYZE` the hot queries
- [ ] Connection pooling under concurrent load
- [ ] Locust: 50 → 500+ concurrent; find the first bottleneck
- [ ] Apply one mitigation, measure before/after
- [ ] One cost optimization with real numbers
- [ ] Fill in `DESIGN.md` §14 with measured values

**Done when:** you can say "load tested to X req/s, bottleneck was Y, mitigated by Z" and
every number is one you actually measured.

---

## Suggested order

**Phases 0 → 1 → 2 → 3** gets you a working live transcription pipeline — visible,
demoable, and it de-risks the parts with the most unknowns (AudioWorklet plumbing,
Deepgram streaming, WebSocket backpressure).

**Phase 4** is independent. Start it in parallel whenever you want a break from plumbing;
generation and training are mostly waiting anyway.

**Phase 11** is listed late but is cheap and high-value — pull it forward as soon as
Phase 5 exists.
