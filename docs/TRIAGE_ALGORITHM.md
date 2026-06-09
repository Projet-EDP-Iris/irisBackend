# Email Triage Algorithm

Iris classifies each email into one of five UI tabs — **rdv**, **action**, **attente**, **bonsplans**, **info** — using a three-layer pipeline.

---

## Pipeline overview

```
Email (subject + body + sender + headers)
       │
       ▼
┌──────────────────────────────────────────────┐
│  Layer 0: Zero-shot pre-filter               │  O(1) · pure regex
│  app/nlp/preprocessor.py                     │
│                                              │
│  Signals checked:                            │
│  · no-reply pattern in sender               │
│  · "List-Unsubscribe" header present        │
│  · unsubscribe keyword in first 800 chars   │
│                                              │
│  If automated + promo keywords → bonsplans  │
│  If automated (no promo)       → info        │
│  Otherwise                     → continue   │
└──────────────────────────────────────────────┘
       │ not automated
       ▼
┌──────────────────────────────────────────────┐
│  Layer 1: Weighted scoring matrix            │  fast · multi-signal · O(n)
│  app/nlp/extractor.py                        │
│                                              │
│  Each category has multiple patterns with    │
│  individual weights (1.0–3.0). All patterns │
│  are evaluated; scores are summed (capped    │
│  at 3 matches per pattern group).            │
│                                              │
│  RDV hierarchy override: when cancel or      │
│  reschedule scores > 0, lower-priority       │
│  meeting categories (schedule) are removed  │
│  to prevent "réunion" leaking upward.        │
│                                              │
│  Confidence formula:                         │
│    conf = 0.5 + 0.4*(top/total) + 0.1*margin│
│    capped at 0.95                            │
│                                              │
│  If scores empty → fall through to spaCy    │
└──────────────────────────────────────────────┘
       │ low confidence or no scores
       ▼
┌──────────────────────────────────────────────┐
│  Layer 1b: spaCy NER + morphology            │  slower · probabilistic
│                                              │
│  Analyses first 600 chars of text:           │
│  · imperative verb mood   → action  0.60    │
│  · high question ratio    → attente 0.55    │
│  · ORG entity (no LOC)    → info    0.45    │
│  · fallback               → info    0.30    │
└──────────────────────────────────────────────┘
       │
       ▼
  ExtractionResult
  ├── classification  (internal value)
  ├── confidence      (0.0 – 0.95)
  ├── needs_llm       (True when conf < LLM_CONFIDENCE_THRESHOLD)
  └── metadata        (times, duration, link, participants — meeting types only)
       │
       ▼ (async, post-batch)
┌──────────────────────────────────────────────┐
│  Layer 2: Async LLM batch enrichment         │  gpt-4o-mini · category only
│  app/services/detection.py  enrich_batch()  │
│                                              │
│  Pass 1 — category reclassification:         │
│    Emails with needs_llm=True are sent to    │
│    gpt-4o-mini concurrently (asyncio.gather) │
│    to correct the category label only.       │
│                                              │
│  Pass 2 — auto-reply drafting:               │
│    rdv / action / attente emails (up to 20)  │
│    get a suggested_reply generated in        │
│    parallel, stored in EmailItem.            │
└──────────────────────────────────────────────┘
```

---

## Categories and pattern coverage

| UI tab | Internal classification | Patterns cover |
|---|---|---|
| **rdv** | `meeting_schedule` | meeting / réunion / call scheduling, availability, day+time combos (FR/EN/franglais) |
| **rdv** | `meeting_cancel` | cancel / annulé / ne pourra pas avoir lieu (weight 3.0 — highest priority) |
| **rdv** | `meeting_reschedule` | reschedule / reporter / nouvelle date (weight 2.5) |
| **bonsplans** | `bonsplans` | promo / discount / coupon / cashback / flash sale / loyalty points |
| **attente** | `attente` | follow-up / relance / checking in / sans nouvelles / just a reminder |
| **action** | `action` | action required / please confirm / formulaire à remplir / deadline / avant le [date] |
| **info** | `info` | newsletter / rapport mensuel / FYI / ci-joint / no action required |

---

## Metadata extraction (meeting types only)

For `meeting_schedule`, `meeting_cancel`, and `meeting_reschedule`:

| Field | Method |
|---|---|
| `proposed_times` | `dateparser.search.search_dates()` — up to 5 future dates |
| `duration_minutes` | regex on `\d+ min/h` patterns |
| `timezone` | regex on UTC±N, EST, CET, Europe/*, America/* |
| `meeting_link` | platform-specific patterns (Zoom, Teams, Meet, Webex) → generic URL fallback |
| `modality` | derived from link platform or keyword scan |
| `participants` | `From:` / `To:` header parsing (up to 10) |

---

## Parallel execution

`GET /emails/feed` runs NLP concurrently via `ThreadPoolExecutor(max_workers=8)`. After all synchronous classifications complete, `enrich_batch()` fires two async passes using `asyncio.gather` for concurrent LLM calls. Emails already categorised in the database skip NLP entirely.

---

## LLM fallback threshold

Set via environment variable (default **0.75**):

```
LLM_CONFIDENCE_THRESHOLD=0.75
```

Emails below this threshold have `needs_llm=True` and enter the async LLM batch for category correction. The LLM receives only subject + first 800 chars of body and returns a JSON category label — it does not re-extract meeting metadata.

---

## Improving the classifier

When users submit corrections via `POST /api/v1/feedback`, corrections are stored in `detection_feedback`. Run:

```bash
cd irisBackend
python -m app.ML.retrain_from_feedback
# → writes app/ML/feedback_patterns_report.json
```

The report lists top misclassification transitions and the most frequent tokens per category. Add high-signal tokens to `_CATEGORY_PATTERNS` in `app/nlp/extractor.py`.
