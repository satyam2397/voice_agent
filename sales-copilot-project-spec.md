> ⚠️ **SUPERSEDED — do not edit.** This file is kept only as a record of how the design
> evolved. The current source of truth is **`DESIGN.md`**, with the build plan in
> **`TODO.md`**. Parts of this document are out of date (STT choice, classifier design,
> the rules layer's role). Safe to delete once you no longer want the history.

# Real-Time Sales Co-Pilot — Project Spec (Resume Project)

## 1. What this is
An independent, from-scratch project (no employer code, data, or IP) demonstrating an
agentic AI system that assists a financial advisor/sales rep during a live conversation
by surfacing real-time, data-grounded "flash card" nudges.

Domain: mutual fund / financial advisory sales (using synthetic or public factsheet data only).

## 2. Purpose of the project
- Primary goal: **learn and showcase skills** — agentic architecture, tool orchestration,
  retrieval systems, real-time processing, system design discipline.
- Not a SaaS. Not aiming for real users or real scale.
- Aiming for: **production engineering practices, applied at small/demo scale.**
  (i.e., correct patterns and discipline — not production-scale infrastructure.)
- Must be honestly describable in interviews without overclaiming.

## 3. Explicit non-goals (to prevent scope creep)
- No multi-region infra, no real load testing at scale, no real user auth/onboarding flows.
- No real distributor/investor data, no real employer references or code.
- Not attempting to handle every edge case in the world — a **named, bounded** set of
  failure modes (see #5) rather than vague "full fault tolerance."

## 4. Core functional loop
1. Browser captures live mic audio and streams it continuously to the backend, which runs
   VAD and streaming STT to produce final transcripts. Speaker identity comes from
   per-party channel separation, not diarization.
2. Trigger classifier decides, turn-by-turn, whether an LLM/agent call is warranted
   (see section 6a).
3. On trigger: assemble context — recent conversation window, distributor/advisor profile
   (from past interaction memory), and retrieved data (fund performance, documents, notes).
4. Agent(s) call tools against this data, synthesize a short actionable "flash card."
5. Flash card is surfaced to the rep in near real time.
6. Post-conversation: summarize into the rolling profile, and embed a bounded set of
   conversation chunks for later semantic recall (both scoped to the distributor).

## 5. Engineering principles to apply (concrete, not abstract)

**Reliability / fault tolerance — name the specific failure modes to handle:**
- LLM API call fails or times out → retry with backoff, then graceful fallback message.
- Vector DB / RDB unreachable → degrade gracefully (serve from cache or reduced context,
  don't crash the whole pipeline).
- Tool call returns malformed/empty data → agent handles it without hallucinating filler.
- Trigger classifier is uncertain → default to *not* calling the LLM (fail closed, cost-safe).
- Define and log these explicitly; each should be demoable (kill a dependency, show system
  degrades instead of dying).

**Scalability — design for it, don't over-build it:**
- Stateless service layers where possible (so horizontal scaling is a config change, not a rewrite).
- Async/queue-based decoupling between ingestion → classification → agent execution, so
  slow LLM calls don't block ingestion.
- Don't build actual multi-instance infra/load balancers for a solo demo — just don't
  architect in a way that would prevent it later.

**Flexibility / swappability (pick concrete targets, not "everything"):**
- LLM provider behind an interface (swap Claude/OpenAI/local model with config, not code changes).
- Vector store behind an interface (e.g., swap Chroma/Pinecone/pgvector).
- Keep prompt templates and tool definitions decoupled from orchestration logic.

**Security (bounded, realistic for a demo):**
- No real PII — synthetic data only, clearly labeled as such.
- Basic secrets management (env vars / secret manager, not hardcoded keys).
- Input sanitization on anything that reaches a DB query or prompt (basic prompt-injection
  awareness for tool-calling agents is a good talking point).

**Evaluation (often skipped — a strong differentiator):**
- A small labeled test set of conversation snippets with expected trigger/no-trigger decisions.
- A basic rubric or LLM-judged scoring for flash card quality/relevance.
- Regression check: re-run eval set when you change prompts/models to catch quality drops.

**Cost & latency as first-class constraints:**
- Define a target latency budget end-to-end (e.g., "<3s from trigger to flash card").
- Track token usage per interaction; make deliberate choices about context size vs. cost.

## 6. Architecture decisions (made explicitly)

**Single orchestrator, not multi-agent.** Chosen for latency and debuggability — a real-time
system with a <3s budget favors a straight line of reasoning over agent handoffs. The
orchestrator is a hand-rolled loop (call the LLM with tools → run any requested tool call
via MCP → feed the result back → repeat until a final answer), not LangChain/LangGraph.

*Why not LangChain/LangGraph, explicitly:* LangGraph earns its keep when there's a branching
graph of agents to manage, or when you need built-in checkpointing/persistence. This system
has neither — single orchestrator, no multi-agent handoffs. The two things a framework would
otherwise provide (tool orchestration, tool/prompt decoupling) are already covered by native
tool-use and MCP. A hand-rolled loop is also a stronger interview story: every step between a
trigger and a flash card is something you can explain line by line, not "the framework
handles that part." Worth revisiting LangGraph specifically if resumable/checkpointed
conversation state becomes a requirement later.

**Core pipeline (async, queue-decoupled):**

```
Conversation ingestion → Trigger classifier (fail-closed) → Context assembly
  → Agent orchestrator (MCP tool calls) → Flash card delivered + memory updated
```

Ingestion writes to Redis and returns immediately; classification, context assembly, and
agent execution run as async workers pulled off the queue, so a slow LLM call never blocks
the live transcript feed. The trigger classifier runs cheap rule-based checks first, falling
back to a small model only when ambiguous — and any residual uncertainty resolves to *not*
triggering (fail closed, per section 5).

**Tool calling via MCP.** Each tool — fund data lookup, document retrieval, distributor
profile/memory — is its own MCP server; the orchestrator is an MCP client. Adding a new tool
later (e.g. a compliance check) means standing up a new MCP server, not touching orchestrator
code. This directly satisfies the "keep tool definitions decoupled from orchestration logic"
principle in section 5, and is the concrete answer to "how would this scale to a real
production system with more tools."

**Memory / profile storage.** Structured fields (AUM tier, risk appetite, recent topics) for
fast lookups, plus a rolling text summary — not raw embeddings of every past turn. Keeps
context assembly cheap and makes the retention/eviction policy in section 10e concrete:
summarize old turns, never keep unbounded raw history.

Alongside that, a *bounded* set of embedded conversation chunks per distributor
(`conversation_chunks`) supports semantic recall of specific past exchanges — the
"is this riskier than what we discussed last quarter?" case. This is deliberately not
"embed every turn forever": chunks are written at conversation close, capped per
distributor, and evicted oldest-first once the rolling summary covers them.

**Audio ingestion — real browser mic capture, streamed.** The frontend captures live
audio with `getUserMedia` + **AudioWorklet** (not `MediaRecorder`), emits ~100-250ms PCM
chunks, and streams them continuously over WebSocket. No record-then-upload, no batching:
the point of the project is a live pipeline, and a batch upload would quietly remove the
hardest and most interesting part of it.

**STT sits behind a swappable interface**, the same pattern as the LLM provider and the
vector store — three interfaces, one pattern, demonstrated rather than asserted. Deepgram
is the primary implementation; self-hosted **whisper.cpp** is the alternative, and exists
specifically so there is a no-vendor-lock-in answer. The contract is `on_partial` /
`on_final`.

**End-of-turn belongs to the STT adapter, not to VAD directly.** Deepgram ships its own
endpointing; whisper.cpp does not and wraps Silero to produce the same signal. Making
Silero the authoritative end-of-turn would leak a whisper.cpp implementation detail into
an interface both providers must satisfy. VAD still earns its place *upstream* as a cheap
audio-level gate on what gets shipped to STT at all — a direct cost lever once Deepgram is
metered per minute.

**The classifier never runs mid-utterance.** It consumes final transcripts only, on the
adapter's end-of-turn signal.

**The classifier is text-native by choice, not by fallback.** Operating on transcript text
rather than raw audio means the trigger decision is inspectable, cheap to evaluate against
a labeled text dataset, and reuses the same eval harness the rest of the system uses. An
audio-native intent model would be a materially harder training problem with no benefit to
the decision being made.

**Speaker identity comes from channel separation, not diarization** — one audio channel
per party, as real call-recording systems do. Diarization models are slow and would sit
directly in the latency budget to solve a problem the capture setup solves for free.
Because speaker is known before transcription, rep turns are filtered at ingestion and
never reach the classifier at all.

**Tenant isolation.** Every query against Postgres or the pgvector store is scoped by
`distributor_id` at the query level (`WHERE` clause / metadata filter), never filtered in
application code after retrieval.

**The tenant ID is never a model-supplied tool argument.** It is held by the orchestrator
for the session and injected into every tool call before dispatch; it does not appear in
the tool schemas the model sees. A correctly-scoped `WHERE` clause is worthless if the
value it filters on was chosen by a model reading an untrusted live transcript — that is a
prompt-injection path straight through the isolation boundary. Removing the argument means
a cross-tenant request is *inexpressible*, not merely discouraged. This is the concrete
form of the "prompt-injection awareness for tool-calling agents" point in section 5.

Tested by the concurrent-session test in section 10f, which asserts against a unique canary
token seeded into user B's memory and checks user A's *fully assembled prompt and flash
card* — not just the tool return value, since the classic leak is in context assembly or a
mis-keyed cache rather than in the query itself.

**Sync vs. async by stage:**
| Stage | Mode |
|---|---|
| Audio capture → ASR | Streaming, per-utterance |
| Ingestion write | Sync (fast, non-blocking) |
| Trigger classification | Async worker |
| Context assembly | Async worker |
| Agent execution | Async worker |
| Conversation chunk embedding | Async, post-conversation |
| Memory update | Async, post-conversation |

## 6a. Trigger classifier design

**A fine-tuned DistilBERT is the primary mechanism** — not rules, and not a prompt-based
LLM classifier. Full label schema, adjudication rules, and dataset design live in
`backend/app/classifier/LABEL_SCHEMA.md`; this section is the rationale.

Why a fine-tuned encoder over the two alternatives:

- **vs. rules** — the task is genuinely hard once implicit, non-interrogative pushback
  counts as a trigger ("i'd need to see how it handles a downturn"). That is not
  keyword-matchable, and it is where the co-pilot earns its keep.
- **vs. prompt-based LLM classification** — ~15-30ms CPU inference and zero per-call API
  cost, versus 300-600ms and a metered call *per conversational turn*. Putting an LLM call
  inside the layer whose entire job is deciding whether to make an LLM call is a design
  contradiction, not just an expense.

**Two heads on one shared encoder.** A sigmoid `trigger` head with a **tunable threshold**,
and a softmax `category` head over 13 classes. The binary head is deliberately not derived
from the category argmax — keeping it separate is what preserves the threshold as an
independent lever for the fail-closed asymmetry below.

**The category head is functional, not decorative.** It selects which tools the
orchestrator exposes and which prompt template it uses: `fund_comparison` → `compare_funds`,
`historical_reference` → `conversation_chunks`, `suitability_match` → distributor profile.
A category label that routes nothing is a label you paid to generate and never used.

**Input.** Three previous turns plus the target turn, speaker-tagged, target always last.
The trailing context is what makes anaphoric turns ("is this riskier than what we discussed
last quarter?") classifiable at all.

**No LLM escalation tier.** Below threshold means no trigger. The encoder is fast enough
that no ambiguous band justifies a 300ms+ API call, and escalation would reintroduce the
contradiction above.

**Optional rule pre-filter.** A cheap rules layer in front of DistilBERT (backchannels,
obvious small talk) is a nice-to-have cost optimization, **not the primary mechanism** —
and it must be measured *against* the DistilBERT-only baseline before it ships. A
pre-filter that changes accuracy is a bug, not a feature. The cooldown and topic-dedup
gates are separate: they are orchestrator-level product constraints (don't bury the rep),
not part of the classification decision.

**Threshold selection.** From the precision/recall curve on the validation split against a
stated cost asymmetry — a false positive burns an LLM call *and* erodes the rep's trust in
the tool; a false negative costs only a missed assist. Interrupting a live sales call
wrongly is worse than staying silent, so tune for precision and accept lower recall. That
asymmetry is the fail-closed principle expressed as a defensible number rather than a round
default.

**One generation effort, four splits.** Train / val / `test_natural` / `test_balanced`
(see LABEL_SCHEMA §5). The `test_natural` split carries the realistic ~15% base rate and is
**hand-audited**; it produces the headline number. `test_balanced` is explicitly diagnostic
— per-category confusion only, its accuracy is never quoted as the system's accuracy.

**Honest framing.** Training labels are distilled from a frontier model. Because
`test_natural` is human-verified, the headline metric is trigger correctness rather than
teacher-agreement — and the generator's own error rate, measured during that audit, is
reported as a bound on label noise.

**Metric.** Precision/recall/F1 on the trigger head, never bare accuracy: at a ~15% base
rate a classifier that always answers "no" scores ~85%, which cannot distinguish a working
fail-closed system from one that does nothing.

## 7. Tech stack (free / open-source, or generous free tier)

| Layer | Choice | Why |
|---|---|---|
| LLM | Ollama (local, free) for dev; Claude API (`claude-opus-5`) behind the same interface for the real demo | Build and iterate at zero cost; flip one config value for the hosted-model demo. |
| Audio capture | Browser `getUserMedia` + **AudioWorklet**, ~100-250ms PCM chunks over WebSocket | Real live capture. `MediaRecorder` batches into containers and would turn this into record-then-upload. |
| VAD | Silero VAD, server-side | Cheap audio-level gate on what reaches STT — a direct cost lever on metered STT. Not the end-of-turn authority (see section 6). |
| STT | **Swappable interface**; Deepgram primary, self-hosted whisper.cpp alternative | Third interface following the same pattern as LLM and vector store. whisper.cpp exists so there is a no-vendor-lock-in answer. Contract is `on_partial`/`on_final`. |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`), local | Free, no API cost, fast enough at demo scale. Serves document and conversation-chunk embedding. |
| Trigger classifier | Fine-tuned **DistilBERT**, two heads (trigger + category) | ~15-30ms CPU, zero per-call cost. A second resident model (~250MB) alongside the MiniLM embedder — accepted deliberately for the stronger ML-systems story. See section 6a. |
| Vector store | pgvector, abstracted behind an interface (Chroma as an alternative implementation) | One database instead of two moving parts; interface still demonstrates swappability. |
| Relational DB | PostgreSQL (Docker locally; Supabase/Neon free tier if hosted) | Free; already needed for pgvector. |
| Queue / cache | Redis + RQ | Free; satisfies the async-decoupling principle in section 5. |
| Backend | FastAPI | Async-native, minimal, easy to reason about. |
| Tool calling | MCP (Anthropic's MCP Python SDK) | Free, open protocol; decouples tools from orchestration and scales to "more tools later" cleanly. |
| Orchestration | Hand-rolled agent loop using native tool-use, not LangChain/LangGraph | See section 6 rationale. |
| Observability | OpenTelemetry + Arize Phoenix (Apache 2.0, self-hostable, OTel-native) | LLM-aware tracing (prompts, completions, tokens, retrieval spans) without hand-rolled dashboards. |
| Evals | RAGAS (retrieval quality: context precision/recall, faithfulness) + DeepEval (trigger classifier accuracy, LLM-judge flash-card quality, pytest-style regression tests) | Both Apache 2.0 / free; cover the two different evaluation problems in this system (retrieval vs. generation quality). |
| Load testing | Locust | Free, Python-native, fits the "50 → 500-1000 req/s" curve in section 10a. |
| Structured logging | structlog | Free; JSON logs with request/session/tenant IDs on every line. |
| Frontend | React | WebSocket client rendering flash cards as they arrive; kept thin, no business logic. |
| Local orchestration | Docker Compose (Postgres, Redis, Phoenix, Ollama, backend) | One command spins up the whole stack, zero hosting cost. |

Nothing here requires a paid tier to build and demo. The only variable cost is Claude API
calls made deliberately during final testing/demo — most development happens against the
free local Ollama model.

## 8. Synthetic data schema

```
distributors                    -- the person the rep is talking to
  id, name, region, aum_tier, risk_appetite,
  preferred_asset_classes[], relationship_start_date

funds                           -- synthetic factsheet data
  id, name, category, aum, expense_ratio,
  return_1y, return_3y, return_5y, benchmark_name,
  risk_rating, manager_name, inception_date

fund_documents                  -- chunked for embedding
  id, fund_id, doc_type, title, chunk_text, embedding (pgvector)

conversations
  id, distributor_id, rep_id, channel, started_at, ended_at, status

conversation_turns
  id, conversation_id, speaker (rep|distributor), text, ts,
  audio_start_ms, audio_end_ms, asr_confidence, is_final

distributor_memory              -- scoped strictly by distributor_id
  id, distributor_id, structured_fields (jsonb),
  rolling_summary, last_updated

conversation_chunks             -- tenant-scoped vectors; the ONLY embedded
                                -- data that is not shared reference material
  id, distributor_id (NOT NULL, indexed), conversation_id,
  chunk_text, embedding (pgvector), created_at

trigger_events                  -- for the eval harness
  id, conversation_id, turn_id, triggered (bool),
  classifier_confidence, latency_ms,
  classifier_stage (rule_no|rule_yes|model), classifier_version

flash_cards
  id, conversation_id, turn_id, trigger_reason, content,
  tool_calls_used (jsonb), input_tokens, output_tokens, latency_ms

eval_set                        -- hand-labeled, separate from live data
  id, conversation_snippet, expected_trigger (bool),
  expected_topic, notes
```

`trigger_events` and `eval_set` are the pieces most projects skip — keeping them from day
one is what makes the evaluation and regression-check story in section 5 real rather than
retrofitted.

**Two embedded tables, two different isolation stories.** `fund_documents` is shared
reference material — identical for every rep, so there is nothing to isolate.
`conversation_chunks` is tenant-scoped and is where the per-tenant metadata filter in
section 10f actually applies. `distributor_id` is denormalized onto the chunk row so the
filter is a direct `WHERE`, never a join through `conversations`.

**Filtered vector search caveat.** An HNSW index combined with a `WHERE distributor_id = ?`
predicate can post-filter — searching the global neighbourhood first and discarding
non-matching rows — which silently destroys recall for tenants holding a small share of the
corpus. It is *correct* (no cross-tenant leakage), just lossy. At demo scale it will not
bite; the mitigations are pgvector iterative index scans or partitioning by tenant.
Documented here because knowing the failure mode is the point, not hitting it.

`eval_set` is **hand-labeled and disjoint from the classifier's generated training data**
(see section 6a). Training examples live as versioned JSONL in the repo; the eval set is
the regression gate and never shares rows with them.

## 9. How to talk about this project (positioning, for resume/interviews)
- Describe it as an independent project applying agentic AI + RAG + system design patterns
  to a financial-advisory sales-enablement use case.
- Be upfront it's a focused, small-scale system built with production-quality *practices*
  (not a claim of production-scale infrastructure).
- Lead with the specific engineering decisions and trade-offs made (this spec = your
  interview talking points), not just "I built an AI agent." In particular: why a single
  orchestrator over multi-agent, why a hand-rolled loop over LangGraph, why MCP for tools,
  why pgvector over a separate vector DB.

## 10. Scale & Security Learning Plan (design-for-scale, validate-what's-validatable)

Principle: we're not building for millions of users, but every isolation/statelessness/
scoping decision is made *as if* it will scale — and wherever possible, we validate that
with simulated load rather than just asserting it. Be explicit in interviews about which
claims are "designed for" vs. "actually load tested to X."

**a. Concurrency / scale — simulate, measure, don't fake-claim**
- Tool: Locust for load testing the API layer.
- Fire simulated concurrent requests (start at 50, push to 500-1000+) against the pipeline.
- Capture: where it breaks first (LLM rate limits vs. DB pool exhaustion vs. classifier
  throughput), and what mitigation was applied.
- Resume-safe claim format: "Load tested to X req/s using Locust; identified Y as the primary
  bottleneck; mitigated via Z (e.g., connection pooling, caching, queueing)."

**b. Data management at scale**
- Partition/index schema sensibly (e.g., index by distributor_id, avoid full scans).
- Seed synthetic data at 10k-100k row scale (not 100) and validate query plans stay fast
  (EXPLAIN ANALYZE on Postgres, or equivalent).
- Connection pooling configured and tested under concurrent load (ties into 10a).

**c. Latency**
- Tool: OpenTelemetry tracing across every pipeline stage (ASR, ingestion, classifier,
  retrieval, agent, LLM call), visualized in Arize Phoenix.
- Produce a per-stage latency breakdown, not just end-to-end — this is the actual
  production practice, and it's fully learnable at small scale.

**Budget is measured end of distributor utterance → flash card visible to the rep.**
Adding ASR means the old "<3s from trigger" framing understates the number the rep
actually experiences. Per-stage *targets* (not yet measurements — see below):

| Stage | Target | Notes |
|---|---|---|
| Capture → chunk → WS | ~100–250ms | One chunk interval; continuous, never batched |
| VAD end-of-speech | ~50–100ms | Silero, server-side |
| STT final transcript | 150–400ms | Deepgram streaming; whisper.cpp is slower, measure both |
| Ingestion write (Redis) | <10ms | Returns immediately, never blocks capture |
| Trigger classify (DistilBERT) | 15–30ms | CPU; optional rule pre-filter short-circuits some turns |
| Context assembly (PG + pgvector + memory) | 50–150ms | Parallelize the independent fetches |
| Agent loop (Opus 5, 1–2 tool calls) | 1200–2500ms | Dominates the budget |
| WebSocket push + render | ~50ms | |
| **Total** | **~1.6–3.4s** | Tight against a 3s budget |

Two consequences worth stating up front. First, **the agent stage dominates**, so `effort`
is the primary latency lever — a flash card is a short, well-scoped generation, which is
exactly the shape where `low`/`medium` effort holds quality. Second, **streaming the card
makes time-to-first-token the number the rep perceives**, which is a different (and much
easier) target than total completion.

*These are design targets. Until the Phoenix traces and the section 10a load test exist,
every number above is "budgeted for", not "measured at" — see section 10 preamble.*

**d. Cost optimization**
- Track token usage per interaction (log input/output tokens per LLM call).
- Implement at least one real optimization and show before/after numbers:
  e.g., caching distributor profile summaries instead of re-embedding every turn,
  or truncating/compressing conversation context before it hits the LLM.

**e. Agent memory management**
- Explicit scope boundary per distributor/session (memory keyed by tenant, never global).
- Retention/eviction policy: summarize old turns, don't keep unbounded raw history.
- Document the policy explicitly (this is an architecture decision, not a scale one).

**f. Security / tenant isolation (matters at 1 user just as much as 1 million — top priority)**
- Every data fetch (RDB, vector store, memory store) scoped by distributor/session ID at
  the *query* level (WHERE clause / metadata filter), never filtered after retrieval.
- Vector store: `conversation_chunks` carries a per-tenant metadata filter so similarity
  search can never cross-return another distributor's embedded data. `fund_documents` is
  shared reference material and is deliberately *not* tenant-scoped — stating which is
  which matters more than claiming everything is isolated.
- **The tenant ID is never a model-supplied tool argument** — it is injected by the
  orchestrator from session context and absent from the tool schemas the model sees. See
  section 6; this closes a prompt-injection path that query-level scoping alone does not.
- No shared global mutable state in the agent/session layer (classic bug: a shared
  in-memory dict/cache keyed incorrectly, leaking user B's context into user A's prompt).
- Concrete test to build: two concurrent simulated sessions, with a **unique canary token**
  seeded into user B's memory and conversation chunks, asserting that token never appears
  in user A's fully assembled prompt or flash card. Two properties make this a real test
  rather than a decorative one:
  - It checks the *assembled context and final output*, not just a tool's return value —
    the classic leak is in context assembly or a mis-keyed cache, downstream of the query.
  - The suite includes a deliberately-broken variant (tenant filter removed) that must
    fail, proving the test is capable of failing at all.
- Run the two sessions concurrently via `asyncio.gather`, not sequentially — a sequential
  test cannot exercise the shared-mutable-state bug it exists to catch.

**g. Observability (ties all of the above together)**
- Structured logging across all pipeline stages (structlog, not print statements) — include
  request/session/tenant IDs on every log line for traceability.
- OpenTelemetry traces (see 10c) exported to Arize Phoenix, showing latency, error rate,
  token cost, and trigger-classifier fire rate over time.
- This is what turns "I built an agent" into "I built and can operate a system."

## 11. Next steps (for future build sessions)
- [x] Finalize tech stack (see section 7)
- [x] Design agent/tool interfaces (single orchestrator + MCP servers, see section 6)
- [x] Define synthetic data schema (see section 8)
- [x] Design trigger classifier fully (section 6a; schema in `app/classifier/LABEL_SCHEMA.md`)
- [x] Design the label schema and adjudication rules (13 categories, two heads)

**Classifier track — current focus:**
- [ ] Generate the synthetic dataset per LABEL_SCHEMA §5 (~2800 rows across four splits,
      25-30% hard-negative pairs, ASR-degraded fraction)
- [ ] Hand-audit `test_natural` (~150 rows); record generator error rate as label-noise bound
- [ ] Fine-tune DistilBERT, two heads, class-weighted; version the checkpoint
- [ ] Pick the trigger threshold from the val P/R curve against the stated cost asymmetry
- [ ] Replace the accuracy metric in `app/eval/run_evals.py` with precision/recall/F1 —
      accuracy is ~85% for a do-nothing classifier at a realistic base rate
- [ ] Retire the current five-row eval set: separable by keyword rules alone, so the harness
      scores 100% by construction and can never detect a regression
- [ ] Optional rule pre-filter — only if it beats the DistilBERT-only baseline on cost
      *without* moving accuracy

**Audio track:**
- [ ] Frontend: `getUserMedia` + AudioWorklet, ~100-250ms PCM chunks, continuous WS stream
- [ ] Backend: WS audio endpoint → Silero VAD → STT adapter interface
- [ ] Deepgram adapter (primary) and whisper.cpp adapter (no-vendor-lock-in alternative)
- [ ] Per-speaker channel separation wired end to end; rep turns filtered at ingestion

**Cross-cutting:**
- [ ] Add `conversation_chunks` table, embed-on-close job, and the eviction cap
- [ ] Move tenant ID out of MCP tool schemas into orchestrator-side injection
- [ ] Build eval harness before/alongside the main pipeline (scaffolded — see `app/eval/`)
- [ ] Define the 3–5 fault scenarios and build demoable failure/recovery for each
- [ ] Rewrite the tenant-isolation test around a canary token (current assertions pass
      trivially and would not detect a leak); add the must-fail broken variant
- [ ] Add `conftest.py` and pytest `asyncio_mode` config — async tests currently skip
      silently rather than fail, which hides the headline isolation test
- [ ] Set up OpenTelemetry + Phoenix tracing across pipeline stages before load testing
- [ ] Run Locust load test once the core pipeline works end-to-end; document bottleneck
      found and mitigation applied
- [ ] Scaffold the React frontend (WebSocket client + flash card rendering)
- [ ] Write up the "designed for vs. load tested to X" distinction with real numbers once
      section 10a is run
