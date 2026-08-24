# Real-Time Sales Co-Pilot — Design Document

Single source of truth for what this system is and why it's built this way.
Supersedes `sales-copilot-project-spec.md`.

Companion documents:
- `TODO.md` — ordered build plan
- `backend/app/classifier/LABEL_SCHEMA.md` — classifier label schema and annotation rules

---

## 1. What this is

A live sales conversation runs between a **sales rep** and a **distributor** (a mutual
fund distributor evaluating products to sell to their own clients). The rep usually knows
the pitch but not the product depth — the people who built the fund know it far better.

This system listens to that conversation, decides moment by moment whether it can help,
and when it can, pushes a short data-grounded **flash card** to the rep's screen. It never
speaks, never joins the call, and stays silent most of the time.

**Independent portfolio project.** No employer code, data, or IP. All fund and distributor
data is synthetic.

### What this is not

- Not a SaaS, not aimed at real users or real scale
- No multi-region infrastructure, no real auth or onboarding
- Not attempting every edge case — a **named, bounded** set of failure modes (§9)

The goal is **production engineering practice at demo scale**: correct patterns, applied
honestly, with the difference between "designed for" and "measured at" stated explicitly
everywhere it matters (§13).

---

## 2. The whole system in one picture

```
        Rep and distributor, in person, one table, one device
                              │
┌─ BROWSER (single client, laptop-first) ─────────────────────────┐
│  getUserMedia → AudioWorklet → PCM16 @16kHz, 100–250ms chunks   │
│  ONE mixed stream — both voices                                  │
│                        ↓ WebSocket (binary, continuous)          │
└─────────────────────────────────────────────────────────────────┘
                         ↓
┌─ BACKEND ───────────────────────────────────────────────────────┐
│  WS server → Silero VAD ──────→ (silence dropped, never sent)   │
│                  ↓ speech only                                   │
│            Deepgram streaming STT + diarization                  │
│                  ↓ speaker 0 / speaker 1 + endpointing           │
│            Role resolver  (rep confirms once, by tap)            │
│                  ↓ on_partial (UI only) / on_final               │
│            Conversation window  (speaker-tagged)                 │
│                  ↓                                               │
│            DistilBERT classifier → trigger? + category           │
│                  ↓ trigger only (~15% of turns)                  │
│            Context assembly   ─── profile + memory + retrieval   │
│                  ↓                                               │
│            Agent orchestrator ─── MCP tools ─── Postgres/pgvector│
│                  ↓                                               │
│            Flash card ──→ WebSocket ──→ rep's screen             │
└─────────────────────────────────────────────────────────────────┘
                         ↓ (post-conversation, async)
              Summarize → distributor profile
              Embed     → conversation_chunks
```

**The load-bearing idea:** the expensive path (LLM + retrieval) runs on a small fraction of
turns. Everything upstream of the classifier exists to protect that path. VAD drops
silence, the classifier drops small talk, and anything uncertain resolves to *don't fire*.

---

## 3. Core loop, step by step

1. **Capture.** The rep opens the app on one device, taps record, and sets it on the table.
   One mic, one mixed stream, both voices.
2. **VAD.** Silero detects speech; silence is never shipped to STT.
3. **Transcribe and separate.** Deepgram returns partial transcripts (live UI), final
   transcripts, and diarization labels (`speaker 0` / `speaker 1`).
4. **Resolve roles.** The rep taps "that's me" once, the first time two speakers are
   distinguished. Every later turn inherits the mapping.
5. **Classify.** On each *final* distributor turn, DistilBERT scores trigger probability
   and predicts a category. Most turns stop here.
6. **Assemble context.** On trigger: recent conversation window, distributor profile,
   and retrieved fund data / documents / past-conversation chunks.
7. **Generate.** The agent calls tools and writes a short flash card.
8. **Deliver.** Pushed to the rep over WebSocket, streamed so first tokens appear fast.
9. **Learn.** After the call, summarize into the profile and embed a bounded set of
   conversation chunks.

---

## 4. Audio capture

### Why AudioWorklet, not MediaRecorder

`MediaRecorder` produces encoded container chunks (WebM/Opus) on its own schedule. It's
built for recording, not streaming. `AudioWorklet` runs on the audio thread and hands you
raw PCM frames at whatever interval you choose — which is what a live pipeline needs.

Using `MediaRecorder` would quietly turn this into record-then-upload, removing the
hardest and most interesting part of the project.

### Wire format

| Property | Value | Why |
|---|---|---|
| Sample rate | 16 kHz mono | What STT engines expect; 48 kHz is wasted bandwidth |
| Encoding | PCM16 little-endian | Half the bytes of Float32, no encode/decode cost |
| Chunk size | 100–250 ms | Small enough for responsiveness, large enough to avoid WS overhead |
| Transport | WebSocket binary frames | Continuous; no batching, no upload step |

Browsers typically run `AudioContext` at 48 kHz. Downsample to 16 kHz inside the worklet
rather than requesting a 16 kHz context — Chrome honors the request, Safari does not
reliably.

**Backpressure:** check `ws.bufferedAmount` before each send. If the socket is backed up,
drop frames rather than growing an unbounded queue. Dropping audio is recoverable; running
out of memory is not.

### The setting: one device, in the room

The rep visits the distributor in person, opens the app, taps record, and puts the device
on the table between them. **One microphone, one mixed audio stream, both voices in it.**

There is no second channel, so speaker identity has to be *inferred* — see §5.

**Form factor: laptop-first, responsive to phone.** Build and iterate against a laptop for
speed and debuggability, but keep the layout responsive and avoid desktop-only APIs so a
phone demo works. Note the honest gap: far-field audio quality is not properly exercised
until it's tested on a phone lying on a table, and a laptop's mic array is meaningfully
better than a phone's.

### Acoustics are the biggest quality risk

This is a far-field recording of a live in-person conversation. Everything downstream is
bounded by how good the transcript is, and nothing downstream can repair a bad one:

| Problem | Effect |
|---|---|
| Distance and room reverb | Lower word accuracy, especially for the distributor, who sits further from the device |
| Asymmetric levels | The rep is nearest the mic and loudest; the distributor may be poorly captured |
| Overlapping speech | Far more common in person than on a call — degrades both diarization and transcription |
| Background noise | Office, café, or street noise with no headset isolation |

One thing that gets *easier*: no speaker playback in the room, so there is no echo or
acoustic feedback to cancel.

Practical mitigations: enable Deepgram's noise handling, capture at 16 kHz mono (already
the plan), and surface `asr_confidence` in the UI so low-quality stretches are visible
rather than silently wrong.

---

## 5. Speech-to-text and speaker separation

### Deepgram only — a deliberate scope cut

STT is **not** a swappable interface. Deepgram is the single implementation, kept behind
one `stt.py` module boundary so a second provider later is a contained change rather than
a refactor — but no Protocol, no second implementation.

The reason is diarization. Once speaker separation has to be inferred from a mixed stream,
it stops being a nice-to-have and becomes the thing the whole pipeline rests on. A
self-hosted whisper.cpp path can't diarize, so it would not have been a real alternative —
it would have been a second implementation that silently does less.

Cost, stated plainly: the swappable-interface pattern now has **two** instances (LLM
provider, vector store) rather than three, and there is no no-vendor-lock-in story for
transcription. Accepted.

### Diarization

Deepgram streaming with `diarize=true` returns per-word speaker labels alongside the
transcript. Server-side, so it adds essentially nothing to the latency budget — which is
what makes it viable where a local diarization model would not be.

Two known weaknesses to design around:

- **Cold start.** Diarization is least reliable at the very beginning, before there is
  enough audio to cluster voices — exactly when the first turns arrive.
- **Label drift.** Speaker labels can swap mid-conversation, particularly after long
  silences or heavy overlap.

### Role resolution: one tap

Deepgram returns `speaker 0` and `speaker 1`. It does not know which one is the rep.

The first time two speakers are distinguished, the UI shows both snippets and the rep taps
**"that's me."** Two seconds, near-always correct, no extra model. Every later turn
inherits the mapping.

This is deliberately human-in-the-loop for the one bit that is genuinely hard to infer.
The alternatives were voice enrollment (another model and a setup flow, same outcome) and
a first-speaker/loudest heuristic — which fails *silently*, and a wrong role assignment
inverts every trigger decision for the entire conversation.

### End-of-turn comes from Deepgram, not VAD

On a mixed channel VAD cannot give you turn boundaries. It detects speech versus silence,
and a pause is ambiguous — it might be mid-thought, or it might be a speaker change, and
those need opposite handling. Deepgram's endpointing is speaker-aware and resolves it.

VAD keeps its **upstream** job: a cheap audio-level gate so silence is never shipped to a
per-minute-metered API.

### Partials are for the UI only

Partial transcripts render live so the rep sees the conversation as it happens. **Nothing
downstream consumes them.** The classifier runs on finals only — classifying a
half-finished sentence produces both wrong answers and duplicate work.

---

## 6. Trigger classifier

Full schema, adjudication rules, and dataset design: `backend/app/classifier/LABEL_SCHEMA.md`.

### Text-native by choice

The classifier reads transcript text, not raw audio. This is a deliberate architecture
decision: the trigger decision becomes inspectable, cheap to evaluate against a labeled
text dataset, and reuses the same eval harness as the rest of the system. An audio-native
intent model would be a materially harder training problem with no benefit to the decision
being made.

### Fine-tuned DistilBERT

| Alternative | Why not |
|---|---|
| **Rules only** | Once implicit pushback counts ("i'd need to see how it handles a downturn"), the task isn't keyword-matchable — and that's exactly where the co-pilot earns its keep |
| **Prompt-based LLM** | 300–600ms and a metered call *per conversational turn*. Putting an LLM call inside the layer that decides whether to make an LLM call is a design contradiction, not just an expense |
| **DistilBERT** ✓ | 15–30ms CPU, zero per-call cost, and a real ML systems story |

Cost: a second resident model (~250 MB) alongside the MiniLM embedder. Accepted
deliberately.

### Two heads on one encoder

- **`trigger`** — sigmoid, **tunable threshold**. Carries the fail-closed asymmetry.
- **`category`** — softmax over 13 classes. **Routes tool selection and prompt template.**

The binary head is deliberately not derived from the category argmax. Keeping it separate
preserves the threshold as an independent lever.

The category head is functional, not decorative: `fund_comparison` → `compare_funds`,
`historical_reference` → `conversation_chunks`, `suitability_match` → distributor profile.
A category that routes nothing is a label you paid to generate and never used.

### Input

Three previous turns plus the target turn, speaker-tagged, target always last. Trailing
context is what makes anaphoric turns ("is this riskier than what we discussed last
quarter?") classifiable at all.

### The classifier must survive diarization errors

Speaker tags now come from Deepgram's diarization, not from a channel — which means they
are **probabilistic, not structural**. Rep turns cannot be reliably filtered out before the
classifier, because a mislabeled turn will occasionally arrive as a target.

So `rep_turn` is a real no-trigger category in the label schema, and the training set
includes rep utterances *as targets*. The classifier is the backstop for diarization
mistakes: if a rep's "let me pull that up for you" is mislabeled as the distributor
speaking, the classifier should still decline to fire.

This is a direct consequence of single-device capture. With channel separation it would
have been dead weight.

### Fail closed

Below threshold means no trigger. There is no LLM escalation tier. The threshold comes from
the validation precision/recall curve against a stated cost asymmetry:

> A false positive burns an LLM call **and** erodes the rep's trust in the tool.
> A false negative costs only a missed assist.

Interrupting a live sales call wrongly is worse than staying silent — so tune for precision
and accept lower recall. That asymmetry *is* the fail-closed principle, expressed as a
number you can defend.

### Optional rule pre-filter

A cheap rules layer in front of DistilBERT (backchannels, obvious small talk) is a
nice-to-have cost optimization, **not the primary mechanism**. It ships only if it beats
the DistilBERT-only baseline on cost *without moving accuracy*. A pre-filter that changes
accuracy is a bug.

Cooldown and topic-dedup are separate — orchestrator-level product constraints (don't bury
the rep), not part of the classification decision.

---

## 7. Agent orchestration

### Single orchestrator, hand-rolled loop

Not multi-agent, and not LangChain/LangGraph.

**Why single orchestrator:** a <3s budget favors a straight line of reasoning over agent
handoffs. There is no branching graph here and no need for checkpointing.

**Why hand-rolled:** the two things a framework would buy — tool orchestration and
tool/prompt decoupling — are already covered by native tool use and MCP. And every step
between a trigger and a flash card is something you can explain line by line, rather than
"the framework handles that part."

Worth revisiting LangGraph specifically if resumable checkpointed conversation state ever
becomes a requirement.

### Tools via MCP

Each tool is its own MCP server; the orchestrator is an MCP client. Adding a compliance
check later means standing up a new server, not touching orchestrator code.

| Server | Tools |
|---|---|
| `fund_data` | `get_fund_performance`, `compare_funds` |
| `document_retrieval` | `search_fund_documents` |
| `distributor_profile` | `get_distributor_memory` |

**Latency note:** MCP servers are subprocesses. Connect once at application startup and
hold the sessions — spawning per request would blow the budget, since the document server
loads a sentence-transformer at import.

---

## 8. Data model

```
distributors           id, name, region, aum_tier, risk_appetite,
                       preferred_asset_classes[], relationship_start_date

funds                  id, name, category, aum, expense_ratio,
                       return_1y/3y/5y, benchmark_name, risk_rating,
                       manager_name, inception_date

fund_documents         id, fund_id, doc_type, title, chunk_text,
                       embedding vector(384)          ← SHARED reference data

conversations          id, distributor_id, rep_id, channel,
                       started_at, ended_at, status

conversation_turns     id, conversation_id, speaker, text, ts,
                       audio_start_ms, audio_end_ms, asr_confidence, is_final

conversation_chunks    id, distributor_id (NOT NULL, indexed), conversation_id,
                       chunk_text, embedding vector(384)   ← TENANT-SCOPED

distributor_memory     id, distributor_id, structured_fields (jsonb),
                       rolling_summary, last_updated

trigger_events         id, conversation_id, turn_id, triggered,
                       classifier_confidence, latency_ms,
                       classifier_stage, classifier_version

flash_cards            id, conversation_id, turn_id, trigger_reason, content,
                       tool_calls_used (jsonb), input_tokens, output_tokens,
                       latency_ms

eval_set               id, conversation_snippet, expected_trigger,
                       expected_topic, notes
```

### Two embedded tables, two different isolation stories

`fund_documents` is **shared** — identical for every rep, nothing to isolate.
`conversation_chunks` is **tenant-scoped** and is where the per-tenant filter actually
applies. `distributor_id` is denormalized onto the chunk row so filtering is a direct
`WHERE`, never a join.

Saying which is which is more honest — and more useful — than claiming everything is
isolated.

**Filtered vector search caveat:** an HNSW index plus `WHERE distributor_id = ?` can
post-filter — searching the global neighbourhood and discarding non-matching rows — which
silently destroys recall for tenants holding a small share of the corpus. It stays
*correct* (no leakage), just lossy. Mitigations are pgvector iterative index scans or
partitioning. Won't bite at demo scale; documented because knowing the failure mode is the
point.

### Memory policy

Structured fields plus a rolling text summary for fast lookups — **not** embeddings of
every past turn. Alongside that, a *bounded* set of conversation chunks per distributor:
written at conversation close, capped per distributor, evicted oldest-first once the
rolling summary covers them. Never unbounded raw history.

---

## 9. Reliability — named failure modes

Each is specific, and each is demoable by killing a dependency.

| # | Failure | Behavior |
|---|---|---|
| 1 | LLM API times out or errors | Retry with backoff, then a graceful "couldn't fetch" card — never a crash, never invented data |
| 2 | Postgres / pgvector unreachable | Degrade to reduced context or cache; the pipeline continues, the card says what's missing |
| 3 | Tool returns malformed or empty data | Agent reports the gap instead of hallucinating filler |
| 4 | Classifier uncertain | Fail closed — no trigger, no LLM call |
| 5 | STT fails mid-stream | Error surfaced to the UI; pipeline keeps ingesting audio, transcript resumes on reconnect |
| 6 | WebSocket drops | Client reconnects with the same `conversation_id`; audio resumes, session state survives |
| 7 | Diarization mislabels a speaker | Classifier declines on rep-sounding turns (`rep_turn` category); the rep can re-assign roles mid-conversation from the UI |

Scalability is **designed for, not built**: stateless service layers, queue-decoupled
stages, nothing that would prevent horizontal scaling later. No load balancers or
multi-instance infrastructure for a solo demo.

---

## 10. Security and tenant isolation

Top priority regardless of scale. Matters identically at one user and one million.

**Every query is scoped at the query level** — `WHERE` clause or metadata filter — never
filtered in application code after retrieval.

**The tenant ID is never a model-supplied tool argument.** It is held by the orchestrator
for the session and injected into every tool call before dispatch; it does not appear in
the tool schemas the model sees.

> A correctly-scoped `WHERE` clause is worthless if the value it filters on was chosen by a
> model reading an untrusted live transcript. That's a prompt-injection path straight
> through the isolation boundary. Removing the argument makes a cross-tenant request
> *inexpressible*, not merely discouraged.

**No shared global mutable state** in the agent/session layer — the classic leak is a
mis-keyed in-memory cache, not a missing `WHERE`.

**The test:** two concurrent sessions, a unique **canary token** seeded into user B's
memory and chunks, asserting that token never appears in user A's fully assembled prompt or
flash card. Two properties make it real:

- it checks the **assembled context and final output**, not a tool's return value — the
  classic leak is downstream of the query
- the suite includes a **deliberately-broken variant** (tenant filter removed) that must
  fail, proving the test can fail at all

Run concurrently via `asyncio.gather`, never sequentially — a sequential test cannot
exercise the shared-state bug it exists to catch.

**Other bounded measures:** synthetic data only, secrets via env vars, input sanitization
on anything reaching a query or a prompt.

---

## 11. Latency, cost, observability

### Budget: end of distributor utterance → card visible

| Stage | Target |
|---|---|
| Capture → chunk → WS | 100–250 ms |
| VAD end-of-speech | 50–100 ms |
| STT final transcript | 150–400 ms |
| Ingestion write (Redis) | <10 ms |
| Classifier (DistilBERT) | 15–30 ms |
| Context assembly | 50–150 ms |
| Agent loop (LLM + tools) | 1200–2500 ms |
| WS push + render | ~50 ms |
| **Total** | **~1.6–3.4 s** |

Two consequences. **The agent stage dominates**, so `effort` is the primary latency lever —
a flash card is a short, well-scoped generation, exactly the shape where lower effort holds
quality. And **streaming the card makes time-to-first-token the number the rep perceives**,
a much easier target than total completion.

### Cost controls

- Log input/output tokens on every LLM call, per flash card
- The classifier is the main cost lever: no trigger, no spend
- VAD prevents paying to transcribe silence
- At least one measured optimization with before/after numbers (candidate: cache
  distributor profile summaries instead of re-assembling per turn)

### Observability

- **structlog** — JSON logs, `session_id` / `distributor_id` / `conversation_id` on every
  line
- **OpenTelemetry → Arize Phoenix** — a span per pipeline stage, so the table above becomes
  measurements instead of targets
- Tracked over time: latency per stage, error rate, token cost, classifier fire rate

---

## 12. Evaluation

Two different problems, two tools.

**Trigger classifier** — precision / recall / F1 on the trigger head. **Never bare
accuracy**: at a ~15% base rate, a classifier that always says "no" scores ~85%, which
cannot distinguish a working fail-closed system from one that does nothing.

- `test_natural` (~150 rows, realistic base rate, **hand-audited**) → the headline number
- `test_balanced` (~260 rows, ~20/class) → per-category confusion only; its accuracy is
  **never** quoted as the system's accuracy

**Retrieval quality** — RAGAS: context precision/recall, faithfulness.

**Flash card quality** — DeepEval G-Eval judge against a rubric: does the card answer what
was actually asked, using only retrieved data, with no invented numbers?

**Regression gate** — re-run the whole set on every prompt or model change.

**Honest framing:** training labels are distilled from a frontier model. Because
`test_natural` is human-verified, the headline metric is trigger correctness rather than
teacher-agreement — and the generator's own error rate, measured during that audit, is
reported as a bound on label noise.

---

## 13. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Thin: capture, render transcript, render cards. No business logic. |
| Audio capture | `getUserMedia` + AudioWorklet | Real streaming; `MediaRecorder` would make it record-then-upload |
| VAD | Silero, server-side | Cheap gate on what reaches metered STT |
| STT + diarization | Deepgram (single provider, behind one module) | Diarization is load-bearing on a mixed stream; no self-hosted path can match it |
| Classifier | Fine-tuned DistilBERT, two heads | 15–30 ms, zero per-call cost |
| LLM | **Interface**; Ollama local for dev, `claude-opus-5` for demo | Iterate free, flip one config value |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Free, local, 384-dim |
| Vector store | **Interface**; pgvector, Chroma alternative | One database instead of two moving parts |
| Database | PostgreSQL | Already needed for pgvector |
| Queue | Redis + RQ | Async decoupling so slow LLM calls never block ingestion |
| Backend | FastAPI | Async-native, WebSocket support |
| Tools | MCP (Python SDK) | Tool definitions decoupled from orchestration |
| Observability | OpenTelemetry + Arize Phoenix | LLM-aware tracing, self-hostable |
| Evals | RAGAS + DeepEval | Retrieval quality vs. generation quality |
| Load testing | Locust | Python-native |
| Logging | structlog | JSON with tenant IDs on every line |
| Local orchestration | Docker Compose | One command for the whole stack |

Only variable cost is Deepgram usage and deliberate Claude API calls during final testing.

---

## 14. Designed for vs. measured at

The distinction to keep straight in every write-up and interview.

| Claim | Status |
|---|---|
| Swappable providers | **Two instances** — LLM and vector store. STT is deliberately single-provider (§5); don't claim three. |
| Transcript quality in the room | **Unvalidated.** Far-field, single-mic, overlapping speech. Not exercised until tested on a device on a table. |
| Stateless services, queue decoupling, horizontal-scale-ready | **Designed for.** Not deployed multi-instance. |
| Tenant isolation | **Tested.** Concurrent canary test with a must-fail variant. |
| Per-stage latency breakdown | **Measured** once Phoenix traces exist. Currently targets. |
| Classifier precision/recall | **Measured** on a human-verified held-out set. |
| Throughput to X req/s | **Measured** only after the Locust run — with the bottleneck named and the mitigation stated. |
| Flash card quality | **Measured** by LLM judge against a rubric — with the limits of LLM-judged eval acknowledged. |

Never claim a number that wasn't measured. Naming which is which is the point.
