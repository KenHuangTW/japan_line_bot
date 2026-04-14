## 1. Trip Models And Persistence

- [x] 1.1 Add trip models, repository interfaces, and MongoDB persistence for trip lifecycle and active-trip resolution per LINE chat scope
- [x] 1.2 Extend captured lodging documents and duplicate lookup queries to store and filter by `trip_id` and `trip_title`
- [x] 1.3 Add tests covering trip creation, switching, archive behavior, and trip-scoped duplicate lookup

## 2. LINE Commands And Scope Resolution

- [x] 2.1 Implement LINE trip management commands for create, switch, inspect, and archive active trips
- [x] 2.2 Update webhook capture flow so supported lodging URLs require an active trip before they can be stored
- [x] 2.3 Update `/清單`、`/整理`、`/全部重來` to resolve against the active trip and add controller tests for the new scope behavior

## 3. Notion Targeting And Documentation

- [x] 3.1 Refactor Notion target resolution and related queries to use trip-scoped targets
- [x] 3.2 Add regression tests covering trip-isolated Notion target setup and sync behavior
- [x] 3.3 Update README and operational docs for trip commands and active-trip workflow
