## Context

The current product flow is trip-scoped and Mongo-backed: a LINE chat selects an active trip, lodging links are stored under that trip, enrichment adds canonical lodging metadata, and `/清單` plus `/摘要` read canonical Mongo data. The itinerary workflow should follow the same shape: LINE is the input surface, Gemini can normalize structured output, and Mongo remains the source of truth.

LINE quoted-message support has an important constraint: webhook events can include `quotedMessageId`, but LINE does not let the bot fetch the quoted message body later. To support replying to an older itinerary message with `/整理行程`, the bot must first persist inbound text messages by message id.

## Goals / Non-Goals

**Goals:**
- Store itinerary source text, AI drafts, and confirmed itinerary items under the active trip.
- Support `/整理行程 <itinerary text>` for direct full-document import.
- Support replying to an earlier text message with `/整理行程` by resolving `quotedMessageId` from message snapshots.
- Generate a pending draft before changing confirmed itinerary items.
- Compare a new import against existing itinerary items and present a diff summary before apply.
- Preserve stable item identity where possible so later export layers do not create duplicates.

**Non-Goals:**
- Do not implement Google Calendar OAuth or event export.
- Do not implement Google Maps place lookup or directions export.
- Do not build a full itinerary editing web UI.
- Do not directly apply AI output without user confirmation.
- Do not guarantee recovery of quoted messages sent before snapshot persistence was deployed.

## Decisions

### 1. Persist message snapshots before relying on quoted-message commands

Inbound text messages will be saved to a lightweight `line_message_snapshots` collection keyed by LINE `message_id` and source scope. The command path can then resolve `/整理行程` with `quotedMessageId` to the original text.

Rationale:
- LINE exposes the quoted message id but not the quoted content.
- Snapshot persistence is the only reliable way to support reply-based imports without asking users to paste the full text again.

Alternatives considered:
- Fetch quoted content from LINE on demand.
  - Rejected: LINE does not provide that content through webhook or API.
- Only support inline `/整理行程 <text>`.
  - Rejected: replying to a long existing itinerary is a key usability improvement.

### 2. Store source, draft, and confirmed items separately

Each import creates a `trip_itinerary_sources` record for raw text and a `trip_itinerary_drafts` record for AI-normalized proposed changes. Applying a draft writes or updates `trip_itinerary_items`.

Rationale:
- Raw source text is useful for audit, reprocessing, and debugging AI output.
- Drafts let users inspect add/update/delete proposals before changing canonical data.
- Confirmed items stay clean for display and future export.

Alternatives considered:
- Write AI output directly into `trip_itinerary_items`.
  - Rejected: itinerary imports can be ambiguous and should not silently mutate confirmed plans.
- Store only a single denormalized itinerary document on `LineTrip`.
  - Rejected: item-level updates, future export ids, and diffing are easier with item documents.

### 3. Use deterministic parsing before AI normalization

The importer should first parse obvious Markdown structure such as `## 第 1 天 — 2026-06-01` and bullet rows like `09:30-11:00 | title | note`. Gemini then classifies item type, optional status, location fields, and calendar-friendly titles.

Rationale:
- The user's expected input format is structured enough for deterministic extraction.
- Reducing the AI input surface improves repeatability and validation.
- AI remains useful for classification and normalization, not brittle text splitting.

Alternatives considered:
- Send the whole message to Gemini and trust the response.
  - Rejected: larger risk of hallucinated dates, missing rows, and unstable item identity.

### 4. Re-imports produce diff drafts rather than replacing everything

Each proposed item gets a stable fingerprint based on date, time, title, and location. When importing a revised full itinerary, the service compares proposed items against existing confirmed items and marks draft changes as `add`, `update`, `possible_delete`, or `unchanged`.

Rationale:
- Users will paste revised full itineraries; replacing all rows would break future calendar export ids and create duplicate external events.
- A diff draft makes updates visible and recoverable.

Alternatives considered:
- Delete all existing items and insert the new parsed list.
  - Rejected: destructive and incompatible with later export synchronization.

## Risks / Trade-offs

- [Message snapshots store chat content] -> Keep snapshots scoped, avoid storing non-text payloads, and add a configurable retention window.
- [AI may produce invalid or overconfident output] -> Validate with Pydantic schemas, reject unknown source references, and keep all output pending until user applies it.
- [Diff matching may miss large rewrites] -> Mark ambiguous missing items as `possible_delete` instead of deleting immediately.
- [Long LINE replies may exceed message limits] -> Return a compact summary and later reuse the trip display page for richer itinerary viewing.

## Migration Plan

1. Add message snapshot persistence and quoted-message fields to the webhook schema.
2. Add itinerary models, repository protocols, and Mongo repositories.
3. Add deterministic parser and Gemini itinerary draft provider.
4. Add `/整理行程`, `/套用行程`, `/取消行程`, and `/行程` command handling.
5. Add tests covering inline import, quoted import, draft application, diff behavior, and missing snapshot fallback.
6. Update README with the new workflow and LINE quote limitation.

Rollback strategy:
- Disable itinerary commands and leave the new collections unused.
- Existing lodging and trip flows remain unaffected because itinerary data is stored in separate collections.

## Open Questions

- Should message snapshots expire after a fixed number of days, or should itinerary-like messages be retained until the trip is archived?
- Should `/套用行程` apply `possible_delete` changes by default, or require a separate explicit delete confirmation?
- Should day notes such as shopping priorities be stored as itinerary notes, daily notes, or both?
