## Why

The project now has Mongo-backed LINE previews and a read-only trip web page, so Notion no longer needs to be part of the primary lodging review workflow. Keeping Notion sync in the user path adds schema, credential, retry, target-mapping, and documentation complexity that will slow down upcoming trip itinerary, map, and calendar planning work.

## What Changes

- **BREAKING** Remove Notion sync as a supported API/job surface.
- **BREAKING** Stop exposing Notion links, Notion setup, Notion sync status, and Notion export shortcuts in user-facing LINE and trip display flows.
- Change `/整理` so it only reruns lodging/map enrichment for the active trip and updates Mongo canonical records.
- Change `/全部重來` so it force-reruns lodging/map enrichment for the active trip without creating or syncing Notion targets.
- Remove Notion-specific app wiring, routers, controllers, services, repositories, schemas, settings, environment documentation, and operational docs.
- Preserve existing Mongo `notion_*` fields as ignored historical data during this change; do not require a data migration or destructive cleanup.
- Update scheduled trip refresh planning so refresh ends at Mongo-backed enrichment and display updates rather than downstream Notion sync.

## Capabilities

### New Capabilities
- `notion-decommissioning`: Defines the expected product and system behavior after Notion sync and export surfaces are removed.

### Modified Capabilities
None.

## Impact

- Affected code: `app/controllers/line_webhook_controller.py`, `app/routers/*`, `app/controllers/*`, `app/notion_sync/*`, `app/notion_sync_job.py`, `app/config.py`, `app/trip_display/*`, `app/models/captured_lodging_link.py`, `app/schemas/*`, tests, and `README.md`.
- Affected APIs/jobs: remove `/jobs/notion-sync/*` routes and `python -m app.notion_sync_job`; redefine `/整理` and `/全部重來` as enrichment-only commands.
- Affected configuration: remove Notion environment variables from supported configuration and docs.
- Data impact: no migration required; existing `notion_*` fields may remain in stored documents but are not read for display, command behavior, or refresh decisions.
