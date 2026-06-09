# Email Triage Algorithm

Iris classifies each email into one of five UI tabs — **rdv**, **action**, **attente**, **bonsplans**, **info** — using a two-layer NLP pipeline defined in `app/nlp/extractor.py`.

---

## Pipeline overview

```
Email (subject + body)
       │
       ▼
┌─────────────────────────────────────────┐
│  Layer 1: Regex matching                │  fast · deterministic · O(n)
│                                         │
│  1. CANCEL_EN      → meeting_cancel     │  conf 0.90
│  2. RESCHEDULE_EN  → meeting_reschedule │  conf 0.85
│  3. SCHEDULE_EN    → meeting_schedule   │  conf 0.80
│  4. BONSPLANS_RE   → bonsplans          │  conf 0.75
│  5. ATTENTE_RE     → attente            │  conf 0.70
│  6. ACTION_RE      → action             │  conf 0.70
│  7. INFO_RE        → info               │  conf 0.65
└─────────────────────────────────────────┘
       │ no match
       ▼
┌─────────────────────────────────────────┐
│  Layer 2: spaCy NER + morphology        │  slower · probabilistic
│                                         │
│  Analyses first 600 chars of text:      │
│  · imperative verb mood   → action      │  conf 0.60
│  · high question ratio    → attente     │  conf 0.55
│  · ORG entity (no LOC)    → info        │  conf 0.45
│  · fallback               → info        │  conf 0.30
└─────────────────────────────────────────┘
       │
       ▼
  ExtractionResult
  ├── classification  (internal value)
  ├── confidence      (0.0 – 1.0)
  └── metadata        (times, duration, link, participants — meeting types only)
```

---

## Categories and regex coverage

| UI tab | Internal classification | Patterns cover |
|---|---|---|
| **rdv** | `meeting_schedule` | meeting / réunion / call scheduling, availability questions, day+time combos (FR/EN/franglais) |
| **rdv** | `meeting_cancel` | cancel / annulé / ne pourra pas avoir lieu |
| **rdv** | `meeting_reschedule` | reschedule / reporter / nouvelle date |
| **bonsplans** | `bonsplans` | promo / discount / coupon / cashback / flash sale / loyalty points |
| **attente** | `attente` | follow-up / relance / checking in / sans nouvelles / just a reminder |
| **action** | `action` | action required / please confirm / formulaire à remplir / deadline / avant le [date] |
| **info** | `info` | newsletter / rapport mensuel / FYI / ci-joint / no action required |
| **info** | `other` | legacy value — remapped to `info` at the service layer |

Regex patterns are bilingual (French + English) and handle common franglais constructions ("let's sync demain", "quick call cette semaine").

---

## Metadata extraction (meeting types only)

For `meeting_schedule`, `meeting_cancel`, and `meeting_reschedule`, the extractor additionally parses:

| Field | Method |
|---|---|
| `proposed_times` | `dateparser.search.search_dates()` — up to 5 future dates |
| `duration_minutes` | regex on `\d+ min/h` patterns |
| `timezone` | regex on UTC±N, EST, CET, Europe/*, America/* |
| `meeting_link` | platform-specific patterns (Zoom, Teams, Meet, Webex) → generic URL fallback |
| `modality` | derived from link platform or keyword scan |
| `participants` | `From:` / `To:` header parsing (up to 10) |

This step is skipped for non-meeting categories to save processing time.

---

## Confidence scoring

The final confidence is the sum of:

| Signal | Points |
|---|---|
| Base confidence from regex / spaCy | 0.30 – 0.90 |
| Meeting type matched | +0.30 |
| Non-meeting actionable category | +0.20 |
| At least one proposed time extracted | +0.25 |
| Duration extracted | +0.15 |
| Timezone extracted | +0.15 |
| Meeting link extracted | +0.10 |
| Fixed bonus | +0.05 |

Capped at 1.0.

---

## LLM fallback

In `app/services/detection.py`, `detect_single()` calls the LLM fallback (`LLMFallbackOpenAI`) when:

- confidence is below `settings.LLM_CONFIDENCE_THRESHOLD` (default **0.75**), AND
- `OPENAI_API_KEY` is configured.

If the result is still `other` with confidence < 0.4 after the LLM, it is reclassified as `info` and `needs_review = True` is set for monitoring.

---

## Parallel execution

The `categorize_email()` function (used in `GET /emails` and `GET /emails/feed`) runs regex + spaCy only (no LLM). It is called concurrently via `ThreadPoolExecutor(max_workers=8)` so that a batch of emails is classified in parallel rather than sequentially.

`detect_batch()` in `detection.py` uses the same executor and includes the LLM fallback path.

Emails already categorised in the database are not re-classified — the feed endpoint pre-fetches stored categories and skips NLP for known message IDs.

---

## Improving the classifier

When users submit corrections via `POST /api/v1/feedback`, the corrections are stored in `detection_feedback`. Run the analysis script to identify common misclassifications and get keyword suggestions:

```bash
cd irisBackend
python -m app.ML.retrain_from_feedback
# → writes app/ML/feedback_patterns_report.json
```

The report lists the top misclassification transitions and the most frequent tokens in misclassified emails per category. Add high-signal tokens to the matching regex in `app/nlp/extractor.py`.
