## 1. Message Snapshot Foundation

- [x] 1.1 Extend LINE webhook schemas to preserve `quotedMessageId` and `quoteToken`
- [x] 1.2 Add message snapshot model, repository protocol, and Mongo repository with source-scope lookup by `message_id`
- [x] 1.3 Store inbound text message snapshots during webhook processing before command handling
- [x] 1.4 Add tests for text snapshot persistence, non-text ignore behavior, retention metadata, and scoped quoted lookup

## 2. Itinerary Data Model

- [x] 2.1 Add itinerary source, draft, draft change, item, and day-note models with Pydantic validation
- [x] 2.2 Add itinerary repository protocol and Mongo repository methods for source creation, pending draft lookup, draft state transitions, item upsert, and chronological item listing
- [x] 2.3 Wire itinerary repositories into `app/main.py`, router/controller dependencies, and test app setup
- [x] 2.4 Add repository tests covering trip-scoped isolation, item ordering, draft apply state, and source linkage

## 3. Import And AI Normalization

- [x] 3.1 Implement a deterministic Markdown itinerary parser for day headings, timed rows, and day note sections
- [x] 3.2 Add Gemini itinerary draft client/service using structured JSON output and schema validation
- [x] 3.3 Implement stable item fingerprinting and diff generation for add, update, unchanged, and possible-delete changes
- [x] 3.4 Add service tests for direct imports, optional items, daily notes, invalid AI output, and revised full-itinerary diffs

## 4. LINE Commands

- [x] 4.1 Add `/整理行程` direct-text handling that creates a source and pending draft for the active trip
- [x] 4.2 Add `/整理行程` quoted-message handling that resolves `quotedMessageId` through message snapshots
- [x] 4.3 Add `/套用行程` and `/取消行程` confirmation commands for the latest pending draft
- [x] 4.4 Add `/行程` command rendering for confirmed itinerary items grouped by date
- [x] 4.5 Update `/help` and README command documentation for the itinerary workflow

## 5. End-To-End Coverage

- [x] 5.1 Add webhook tests for inline `/整理行程`, quoted `/整理行程`, missing quoted snapshot fallback, and no-active-trip behavior
- [x] 5.2 Add webhook tests for apply, discard, no pending draft, and confirmed itinerary listing
- [x] 5.3 Run the focused itinerary tests and the full `pytest -q` suite
