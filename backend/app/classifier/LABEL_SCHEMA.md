# Trigger Classifier — Label Schema & Annotation Guide

Governs both the synthetic training set and the held-out eval set. The generator
prompt and the human audit pass must both follow this document — if they diverge,
measured accuracy is measuring the disagreement, not the model.

All data is synthetic. No real fund names, distributor names, or firm names.

## 1. What the classifier sees

Input is the trailing conversation window, speaker-tagged, target turn always last:

```
[REP] Happy to walk you through the mid-cap fund.
[DIST] Sure.
[REP] Three-year returns are running ahead of the benchmark.
[DIST] How does that compare to the category average?     <- target
```

- **3 previous turns + target turn.** Truncate from the left at 512 tokens
  (DistilBERT's limit); conversational turns are short, so truncation is rare.
- **Rep turns DO appear as targets.** Capture is single-device, so speaker tags come
  from Deepgram diarization — probabilistic, not structural. A mislabeled rep turn
  will occasionally arrive as a target, and the classifier is the backstop. See §3
  `rep_turn` and rule R11.
- Text arrives from STT: lowercase, sparse punctuation, disfluencies, occasional
  word errors. The dataset must reflect that (see §5).

## 2. Two heads

| Head | Output | Purpose |
|---|---|---|
| `trigger` | sigmoid, `{0,1}` | **Tunable threshold.** Carries the fail-closed precision/recall asymmetry from spec §6a. |
| `category` | softmax, 13 classes | Routes tool selection and prompt template in the orchestrator. |

The binary head is not derivable from the category argmax — it exists separately so
the trigger threshold stays independently tunable.

## 3. Categories

### Trigger (8)

| Category | Signal | Example target turn | Routes to |
|---|---|---|---|
| `fund_factual` | single-attribute lookup | "what's the expense ratio on that one" | `get_fund_performance` |
| `fund_comparison` | 2+ funds, or fund vs benchmark/category | "how's it stack up against the category average" | `compare_funds` |
| `objection_performance` | pushback on returns / track record | "your three year numbers lagged the index though" | fund data + commentary |
| `objection_cost` | pushback on fees, expense ratio, commission | "that's steep next to a passive option" | fund data + peer set |
| `objection_risk` | volatility / drawdown / downside concern | "my clients can't stomach that kind of dip" | risk rating + factsheet |
| `suitability_match` | fit to their client base or mandate | "would this work for conservative retirees" | distributor profile + fund attrs |
| `historical_reference` | refers to a **prior conversation** | "is this the one you mentioned last quarter" | `conversation_chunks` |
| `process_operational` | product mechanics: minimums, onboarding, docs, commission | "what's the minimum ticket size" | fund data / documents |

### No-trigger (6)

| Category | Example target turn |
|---|---|
| `small_talk` | "how's the family doing" |
| `backchannel` | "mhm", "right", "got it", "sure" |
| `logistics` | "can you email that over after this" |
| `soft_close` | "makes sense, let me think on it" |
| `unintelligible` | truncated or garbled ASR output |
| `rep_turn` | "let me pull that up for you" — the rep speaking |

**14 categories total** (8 trigger, 6 no-trigger).

`rep_turn` exists because single-device capture makes speaker tags probabilistic. It is
the classifier's backstop against diarization errors — see R11.

## 4. Adjudication rules

These exist because "label on intent, not syntax" is ambiguous without them.
Every rule below resolves a case the generator will otherwise label inconsistently.

**R1 — Intent over syntax.** A turn triggers if it expresses an information need the
rep would benefit from answering, whether or not it is grammatically a question.
`"i'd need to see how it handles a downturn"` → `objection_risk`, trigger.

**R2 — Recoverable object required.** An implicit request triggers only when the
subject is recoverable from the turn or its context window. `"i'd need to see how it
handles a downturn"` triggers; bare `"hmm, i don't know about this"` does not — there
is nothing to retrieve.

**R3 — Rhetorical questions do not trigger.** `"who wouldn't want fifteen percent"`
is interrogative but carries no information need. → `small_talk`.

**R4 — Label the utterance, not the conversation state.** If a question was already
answered two turns ago, it is *still* labeled as a trigger. Suppressing repeats is
the orchestrator's topic-dedup gate, not the model's job. Baking conversation state
into labels makes identical utterances carry different labels and the function
unlearnable.

**R5 — Multi-intent: the dominant intent wins, and pushback dominates.**
`"yeah that makes sense, but what's the expense ratio"` → `fund_factual`, not
`soft_close`. `"the returns look fine but that fee is rich"` → `objection_cost`, not
`fund_factual` — where an objection and a question coexist, the question is usually
rhetorical framing for the objection.

**R6 — Statements about their own book are not triggers unless they carry an ask.**
`"i mostly sell debt funds"` → `small_talk`, no trigger.
`"i mostly sell debt funds so i'm not sure this fits"` → `suitability_match`, trigger.

**R7 — Anaphora resolves from the context window.** `"how about that one"` following
a named fund → `fund_factual`. Following nothing resolvable → no trigger.

**R8 — `historical_reference` requires a *prior conversation*,** not merely something
said earlier in this one. Referring back within the current call is ordinary anaphora
(R7) and takes the category of whatever is being asked.

**R9 — `logistics` vs `process_operational`.** `logistics` is about the sales
interaction (send that over, schedule a follow-up). `process_operational` is about
the product's mechanics (minimum investment, folio setup, exit load). "email me the
factsheet" is logistics; "what's the exit load" is process_operational.

**R10 — `unintelligible` is a real class, not a dumping ground.** Use it for genuinely
garbled or truncated ASR output. A turn that is merely vague but parseable is
`small_talk` or no-trigger under R2.

**R11 — `rep_turn` is labeled on *who is speaking*, not on content.** A rep utterance is
`rep_turn` / no-trigger even when it is phrased as a question ("so what's your usual
ticket size?"). These rows exist so the classifier declines when diarization mislabels a
rep turn as the distributor. Generate them as sales-side speech: pitching, explaining,
qualifying, and asking the distributor questions.

## 5. Dataset composition

### Splits

| Split | Size | Base rate | Labels | Purpose |
|---|---|---|---|---|
| `train` | ~2000 | category-balanced | generated | fine-tuning |
| `val` | ~400 | category-balanced | generated | early stopping, threshold sweep |
| `test_natural` | ~150 | **realistic (~15% trigger)** | **hand-audited** | headline precision/recall — the number quoted |
| `test_balanced` | ~260 (~20/class) | balanced | generated | per-category diagnostics, confusion matrix |

Two test sets because they answer different questions. A realistic base rate is
required for precision/recall to describe the deployed distribution, but at 15%
trigger a 150-row set holds ~3 examples per trigger category — far too thin for
per-category numbers. `test_balanced` covers that, and is explicitly diagnostic:
**its accuracy is never quoted as the system's accuracy.**

Train/val are category-balanced (over-representing triggers relative to reality) so
the rarer classes get learned; class weights compensate at training time.

### Hard negatives — target ~25-30% of the dataset

The single highest-leverage property. Without deliberate near-misses the task
degenerates into keyword matching and DistilBERT buys nothing over the rules layer.
Generate as **explicit pairs**: a positive and its minimally-different negative.

| Trigger | Near-miss negative |
|---|---|
| "how's the fund been doing" (`fund_factual`) | "how's business been treating you" (`small_talk`) |
| "that expense ratio is high" (`objection_cost`) | "that fund did well for me personally" (no trigger) |
| "is this the one from last quarter" (`historical_reference`) | "send me the one we just discussed" (`logistics`) |
| "not sure that fits my book" (`suitability_match`, R6) | "not sure, let me think" (`soft_close`, R2) |

### ASR realism

The model is served lowercase, unpunctuated, disfluent text. Training on clean prose
builds train/serve skew directly into the system. Apply to a substantial fraction of
train/val and to `test_natural`:

- lowercase, punctuation dropped or inconsistent
- disfluencies: "um", "uh", "i mean", false starts, self-corrections
- plausible ASR substitutions (homophones, domain terms misheard)
- occasional dropped short words

### Diversity axes

Vary explicitly to prevent template collapse. Generate in small batches across
combinations rather than requesting N examples of one category at once:

- fund category (large/mid/small cap, debt, hybrid, index)
- distributor persona: AUM tier, region, risk appetite, tenure
- conversation stage: opening, mid-pitch, objection handling, close
- register: formal / casual; verbose / clipped
- domain vocabulary (SIP, folio, exit load, NFO, expense ratio) — **synthetic
  entities only**

## 6. Record format

```json
{
  "id": "trg_00001",
  "context": [
    {"speaker": "rep",  "text": "..."},
    {"speaker": "dist", "text": "..."},
    {"speaker": "rep",  "text": "..."}
  ],
  "target": {"speaker": "dist", "text": "..."},
  "trigger": true,
  "category": "fund_comparison",
  "hard_negative_of": "trg_00002",
  "asr_degraded": true,
  "split": "train",
  "generator_version": "v1",
  "audited": false
}
```

`audited` flips to `true` only on hand-verified rows (`test_natural`). Any row whose
label a human changed keeps a `original_label` field so generator error rate is
measurable.

## 7. Metrics

**Never bare accuracy.** At a ~15% base rate a do-nothing classifier scores ~85%,
which cannot distinguish a working fail-closed system from one that does nothing.

- Headline: **precision / recall / F1 on the trigger head**, on `test_natural`
- Threshold chosen from the val P/R curve against the stated cost asymmetry — a false
  positive burns an LLM call *and* erodes rep trust; a false negative costs only a
  missed assist. Tune for precision.
- Per-category: confusion matrix on `test_balanced`
- Report the generator's own error rate, measured during the `test_natural` audit,
  as a stated bound on label noise.
