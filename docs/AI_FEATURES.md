# AI Features: Summarize, Auto-reply, and Reply Suggestions

Iris uses OpenAI `gpt-4o-mini` for three user-facing AI features and one backend enrichment pass. All calls are async and fail gracefully (empty string / empty list) when `OPENAI_API_KEY` is not set.

---

## 1. Email Summarization

**Endpoint:** `POST /api/v1/emails/summarize`

**Request:**
```json
{ "subject": "...", "body": "..." }
```

**Response:**
```json
{ "summary": "2–3 sentence summary in the email's language." }
```

**Implementation:** `app/services/openai_service.generate_summary()`

- Detects the email language automatically and writes the summary in that language.
- Focuses on: what the sender wants, any deadlines or dates, and the required action.
- `max_tokens=150`, `temperature=0.3` (deterministic).
- Input truncated to subject[:200] + body[:1500].

**UI trigger:** "Résumer" button in QuickAction (available for all categories). Opens the email detail panel in summary mode.

---

## 2. Auto-reply Drafting (background enrichment)

**Function:** `app/services/openai_service.generate_auto_reply()`

Called automatically during `POST /emails/fetch-detect-predict` for **rdv**, **action**, and **attente** emails (up to 20 per batch). The draft is stored in `EmailItem.suggested_reply` and returned in the feed response.

- Detects language and replies in kind.
- Tailored instructions per category:
  - **rdv**: acknowledge and propose confirming availability.
  - **action**: confirm receipt and indicate next steps.
  - **attente**: apologise for delay, give a concrete update or timeline.
- `max_tokens=300`, `temperature=0.7`.

---

## 3. Reply Suggestions (3 variants)

**Endpoint:** `POST /api/v1/suggest-inline`

**Request:**
```json
{ "subject": "...", "body": "..." }
```

**Response:**
```json
{
  "variants": [
    { "label": "Amical",  "content": "..." },
    { "label": "Formel",  "content": "..." },
    { "label": "Court",   "content": "..." }
  ]
}
```

**Implementation:** `app/services/openai_service.generate_mail_suggestions()`

Returns three stylistically distinct drafts in the email's detected language. Uses strict JSON schema response format.

**UI trigger:** "Répondre" button in QuickAction (available for **rdv**, **action**, **attente** only). Opens the email detail panel in reply mode showing all three variants with copy buttons.

---

## Email detail panel modes

The right-side `EmailPanel` component supports three render modes:

| Mode | Trigger | Content |
|---|---|---|
| `read` | Click email card body | Full email body |
| `summary` | Click "Résumer" in QuickAction | AI summary card + collapsible original |
| `reply` | Click "Répondre" in QuickAction | Three reply variant cards (Amical / Formel / Court) with copy buttons |

A mode label (✦ Résumé / ✦ Réponses suggérées) is shown in the panel header for non-read modes.

In summary mode, a "Voir l'original" toggle below the summary card reveals the full email body without leaving the panel.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes (for AI features) | API key for gpt-4o-mini calls |
| `LLM_CONFIDENCE_THRESHOLD` | No (default 0.75) | Confidence below which the classifier requests LLM reclassification |
