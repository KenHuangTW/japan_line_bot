## Context

`/清單` now renders a LINE Flex carousel plus a trip detail link from Mongo canonical lodging data. Each lodging already has objective availability (`available`, `sold_out`, `unknown`) derived from source-platform data, but the system has no user-owned decision state. Users therefore cannot mark a lodging as booked or move unsuitable candidates out of the default review flow.

The interaction must stay friendly to non-technical LINE users. Command plus ID flows are precise but too high-friction for the main path, and the existing Flex card footer is already constrained. The design should preserve a compact `/清單` while still making the most common action, "we booked this one", a direct button tap.

## Goals / Non-Goals

**Goals:**
- Add a persistent user decision status to each lodging document without conflating it with source availability.
- Let users mark a candidate as booked from `/清單` with a LINE button.
- Let users revert a booked lodging back to candidate.
- Let users dismiss unsuitable lodgings without crowding the default LINE card footer.
- Keep dismissed lodgings out of default candidate views while preserving access through trip detail filters.
- Surface decision status to Notion export when the schema is managed by this app.

**Non-Goals:**
- Do not implement payment, reservation confirmation, cancellation, or booking-provider integration.
- Do not infer booking status automatically from source-platform data or chat text.
- Do not add a full authentication system for trip detail editing.
- Do not add multi-user audit history beyond the minimal timestamp/user metadata needed for operational clarity.

## Decisions

### 1. Store decision status separately from availability

Add `decision_status` to captured lodging documents with values:
- `candidate`: default state for newly captured lodging links
- `booked`: user marked this lodging as already booked for the trip
- `dismissed`: user no longer wants to consider this lodging

Also store lightweight metadata such as `decision_updated_at` and `decision_updated_by_user_id` when available.

Rationale:
- Availability describes what the lodging source says; decision status describes what the trip group decided.
- Keeping them separate avoids ambiguous combinations such as a booked lodging later becoming sold out on the source site.

Alternatives considered:
- Reuse `is_sold_out` for hidden or discarded lodgings.
  - Rejected: it would mix external supply state with user preference.
- Add only a boolean `is_booked`.
  - Rejected: it does not cover the "not a fit anymore" cleanup path.

### 2. Use LINE postback for primary status actions

Flex buttons should send LINE postback events instead of text commands. The postback payload should identify the action, lodging document id, and target status. The webhook schema should parse postback events and route them through a small decision-status controller/service.

Candidate card behavior:
- image/title area opens the source listing URL when available
- primary footer action is `已訂這間`
- secondary footer action is `旅次詳情`

Booked card behavior:
- show an `已預訂` status/chip
- primary footer action becomes `改回候選`
- secondary footer action remains `旅次詳情`

Rationale:
- Button taps are lower friction than command plus ID.
- Postback keeps the state transition inside LINE without exposing mutation endpoints through the public trip detail URL.

Alternatives considered:
- Use message text commands such as `已訂 2`.
  - Rejected: less intuitive for non-technical users and brittle when list ordering changes.
- Use URI buttons to hit direct mutation links.
  - Rejected: harder to protect from accidental browser prefetch/open behavior and less aligned with LINE's event model.

### 3. Keep dismissal as a secondary management action

Do not put `不考慮這間` in the default `/清單` card footer. First implementation should expose dismissal from the trip detail page, where there is more room for candidate management. If LINE-only management is needed later, add a secondary "more actions" surface instead of crowding each card.

Rationale:
- The highest-frequency task in `/清單` is marking the booked lodging.
- Dismissal is useful cleanup, but making it visually equal to booking adds cognitive load and accidental-tap risk.

Alternatives considered:
- Add `已訂這間`, `不考慮這間`, and `旅次詳情` to every card.
  - Rejected: too crowded for Flex cards and weakens the primary action.
- Hide dismissal entirely.
  - Rejected: unsuitable candidates would continue polluting decision and summary surfaces.

### 4. Default displays prioritize booked and active candidates

Default `/清單` and trip detail views should include booked and candidate lodgings, with dismissed lodgings excluded unless the user chooses a decision-status filter. Summary counts should distinguish booked, candidate, and dismissed counts.

Rationale:
- Users need to see what has already been booked and what remains undecided.
- Dismissed items must remain recoverable without dominating the main view.

Alternatives considered:
- Hide booked lodgings after marking them booked.
  - Rejected: the primary user need is to confirm the trip already has the booked lodging recorded.

### 5. Update downstream surfaces without forcing a data migration job

Newly created lodging records should default to `candidate`. Existing records without `decision_status` should be treated as `candidate` at read time. Notion sync should add or update a decision-status select property when it manages the destination schema.

Rationale:
- The field can be introduced safely without a blocking migration.
- Existing trips continue to work immediately after deployment.

Alternatives considered:
- Run a one-time Mongo migration to backfill every lodging.
  - Rejected: unnecessary for a field with a safe read-time default.

## Risks / Trade-offs

- [Postback handling expands the webhook surface] -> Add explicit schema tests for message and postback events and reject unsupported action names.
- [A stale Flex card could update an old lodging] -> Resolve the lodging by document id and active trip/source scope before applying the transition.
- [Public trip detail page cannot safely mutate state without auth] -> Keep first mutation path in LINE postback; make trip detail dismissal either non-mutating in the first pass or protected by the same signed/action token if implemented.
- [Dismissed lodgings could disappear too completely] -> Preserve a decision-status filter and counts so users can recover them.
- [Notion schemas may differ across old targets] -> Treat Notion decision status as best-effort schema management, consistent with existing sync behavior.

## Migration Plan

1. Extend lodging models and trip display models with decision status and metadata, defaulting missing values to `candidate`.
2. Add repository/service support for status transitions scoped to the current trip and source context.
3. Parse LINE postback events and route `booked` and `candidate` transitions through the new service.
4. Update `/清單` Flex rendering, fallback text, alt text, and counts for decision status.
5. Update trip detail rendering and filters to include booked/candidate/dismissed states and dismissal management.
6. Extend Notion sync schema/property mapping for decision status.
7. Add tests covering defaults, postback transitions, display filtering, fallback behavior, and Notion property output.

Rollback strategy:
- Treat unknown or absent `decision_status` as `candidate`.
- Disable postback action handling and render `/清單` without decision buttons; existing Mongo fields can remain harmlessly unused.

## Open Questions

- Should trip detail page mutations use signed action URLs in the first implementation, or should dismissal be postponed until a protected LINE "more actions" surface exists?
- Should marking one lodging as booked automatically leave other candidates unchanged, or should the system offer an optional "hide other candidates" follow-up later?
