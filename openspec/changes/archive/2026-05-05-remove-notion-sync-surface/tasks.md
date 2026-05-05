## 1. User-Facing Command Flow

- [x] 1.1 Rename Notion-oriented constants and help descriptions so `/清單`, `/整理`, and `/全部重來` describe trip preview and enrichment behavior only
- [x] 1.2 Update capture success reply defaults and configuration docs so captured lodging links are saved/整理ed without mentioning Notion sync
- [x] 1.3 Change `/整理` to run eligible active-trip lodging/map enrichment and return enrichment-focused counts
- [x] 1.4 Change `/全部重來` to force active-trip lodging/map enrichment without resolving or creating Notion targets
- [x] 1.5 Add or update LINE webhook controller tests for `/整理`, `/全部重來`, help text, and capture replies without Notion terminology

## 2. Trip Display And Summary Cleanup

- [x] 2.1 Remove Notion export URL and per-lodging Notion page links from trip display query models, rendering, and LINE fallback text
- [x] 2.2 Ensure trip detail pages ignore historical `notion_*` fields while still rendering records that contain them
- [x] 2.3 Remove Notion page URL from lodging decision summary payloads and summary rendering where it is only an export shortcut
- [x] 2.4 Update trip display and summary tests to assert Notion links/status are absent

## 3. Notion API, Job, And Wiring Removal

- [x] 3.1 Remove Notion sync router registration and `/jobs/notion-sync/*` route tests
- [x] 3.2 Remove Notion sync controller, schemas, service, target manager/repository, sync job module, and package exports
- [x] 3.3 Remove app state setup, dependency providers, and imports that only exist for Notion sync
- [x] 3.4 Remove Notion settings, environment parsing, and default constants from supported configuration
- [x] 3.5 Keep historical Mongo documents readable by preserving tolerant model parsing for existing `notion_*` fields or explicitly allowing ignored extras

## 4. Refresh And Documentation

- [x] 4.1 Update scheduled trip refresh planning/implementation references so active-trip refresh ends after Mongo-backed enrichment
- [x] 4.2 Update README and operational docs to remove Notion setup, sync API, sync job, target mapping, and sync status sections
- [x] 4.3 Add release-note style documentation that Notion routes/jobs are intentionally removed and historical Notion tables are not deleted
- [x] 4.4 Run focused tests for webhook commands, trip display, summary, enrichment, and app startup
- [x] 4.5 Run the full test suite and remove or update obsolete Notion sync tests
