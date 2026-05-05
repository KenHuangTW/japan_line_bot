## Context

The current application already treats Mongo as canonical storage for lodging records, trip state, LINE previews, the read-only trip detail page, and decision summaries. Notion was originally useful as a table-based browsing and maintenance surface, but the product path has shifted to first-party trip display and upcoming itinerary planning.

Notion still remains wired through multiple layers: capture reply text, `/整理`, `/全部重來`, `/清單` secondary links, trip detail secondary links, sync APIs, a standalone job, configuration, target mapping, sync status fields, tests, and README operations. This creates avoidable complexity for future features because unrelated work must preserve Notion schema and sync behavior even though users no longer need it.

## Goals / Non-Goals

**Goals:**
- Remove Notion from user-facing LINE commands, trip display surfaces, API routes, standalone jobs, and supported configuration.
- Redefine `/整理` and `/全部重來` as active-trip lodging/map enrichment commands that update Mongo canonical data only.
- Keep trip display, summaries, and future itinerary planning based on Mongo rather than external export state.
- Avoid destructive data cleanup during the first decommissioning change.

**Non-Goals:**
- Do not migrate or delete historical Mongo `notion_*` fields.
- Do not provide a replacement table export in this change.
- Do not add itinerary, calendar, or Google Maps directions planning in this change.
- Do not preserve backwards-compatible Notion sync endpoints after the removal is implemented.

## Decisions

### 1. Remove Notion as a supported surface instead of hiding it behind configuration

The implementation should delete Notion routes, job entrypoints, service wiring, target mapping, and documentation rather than leaving a disabled-by-default feature flag.

Rationale:
- The product decision is that the web trip surface replaces Notion, not that Notion is temporarily disabled.
- A feature flag would keep tests, schemas, settings, and operational documentation alive for a path we no longer want to maintain.

Alternatives considered:
- Keep Notion code behind `ENABLE_NOTION_SYNC=false`.
  - Rejected: this preserves most of the maintenance burden and leaves unclear ownership for future itinerary work.

### 2. Preserve historical fields but stop reading or writing them

Existing Mongo documents may keep `notion_page_id`, `notion_page_url`, sync status, target IDs, and related timestamps. This change should stop producing, displaying, or making decisions from those values, but it should not require a data migration.

Rationale:
- Removing columns from schemaless historical documents is not necessary for product behavior.
- Avoiding data cleanup keeps rollback and deployment simple.

Alternatives considered:
- Delete all `notion_*` fields during deployment.
  - Rejected: destructive cleanup has no immediate user value and increases rollout risk.

### 3. Convert sync commands into enrichment commands

`/整理` should process pending or stale lodging/map enrichment for the active trip. `/全部重來` should force refresh enrichment for the active trip. Both commands should return language about updating the trip data/web page, not syncing to Notion.

Rationale:
- Users still need a manual way to refresh canonical lodging details after pasting links.
- Keeping the command names avoids changing muscle memory while removing the external export behavior.

Alternatives considered:
- Remove `/整理` and `/全部重來` entirely.
  - Rejected: manual refresh remains useful, especially before scheduled refresh is completed.

### 4. Make scheduled refresh terminate at Mongo canonical updates

The scheduled trip refresh design should run per active trip, rerun lodging/map enrichment, and stop after Mongo records are updated. It should not call downstream Notion sync or require Notion target resolution.

Rationale:
- The first-party trip page reads Mongo, so updated records are visible without an export sync.
- Removing downstream sync simplifies failure handling and makes refresh independent of external Notion availability.

Alternatives considered:
- Keep scheduled Notion sync for operators only.
  - Rejected: an operator-only path still requires credentials, target setup, tests, and docs.

## Risks / Trade-offs

- [Existing users may still have useful Notion tables] -> Keep historical Notion data untouched and document that new updates happen only in the app's trip page.
- [Removing API routes is breaking for scripts] -> Treat `/jobs/notion-sync/*` and `app.notion_sync_job` as intentionally removed and call this out in release notes/docs.
- [Command names mention整理 rather than refresh] -> Update help text and replies so the behavior is clear without requiring a command rename.
- [Model cleanup may touch many tests] -> Split implementation into user-path changes, API/job removal, model/schema cleanup, and docs/tests to keep reviewable patches.

## Migration Plan

1. Update LINE command help, capture replies, `/整理`, and `/全部重來` behavior to remove Notion terminology and stop invoking Notion sync.
2. Remove Notion links from trip display models, rendering, LINE preview fallback text, and summary payloads where they are only export shortcuts.
3. Remove Notion sync routers, controllers, service modules, standalone job, app state wiring, settings, schemas, and tests.
4. Update scheduled refresh planning and implementation points to run enrichment-only.
5. Update README and operations docs to describe Mongo, LINE preview, and the trip web page as the supported surfaces.

Rollback strategy:
- Revert the code change if Notion sync must be restored. Since this change does not delete historical Mongo fields or external Notion tables, existing data remains available for a code rollback.

## Open Questions

- Should `/整理` and `/全部重來` keep their current command names, or should a later UX cleanup rename them to `/更新` and `/全部更新`?
- Should a future export capability provide CSV/ICS-style files from Mongo, or is the web trip page enough for the near term?
