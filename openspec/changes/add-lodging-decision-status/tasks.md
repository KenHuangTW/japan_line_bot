## 1. Data Model And Repository

- [x] 1.1 Add lodging decision status literals, default values, and metadata fields to captured lodging models
- [x] 1.2 Treat existing Mongo documents without decision status as `candidate` when building trip display surfaces
- [x] 1.3 Extend captured lodging repository protocols and Mongo implementation with scoped decision-status update methods
- [x] 1.4 Add unit tests for default status handling, status metadata, and scoped update success/failure

## 2. Trip Display Surface

- [x] 2.1 Extend `TripDisplayFilters`, `TripDisplayLodging`, and `TripDisplaySurface` with decision-status filtering and counts
- [x] 2.2 Update default trip display queries to include booked and candidate lodgings while excluding dismissed lodgings
- [x] 2.3 Update trip display summary payloads to include lodging decision status and decision-state counts
- [x] 2.4 Add trip display tests covering candidate/booked/dismissed counts, default filtering, and dismissed filtering

## 3. LINE Postback Flow

- [x] 3.1 Extend LINE webhook schemas to parse postback events and postback data
- [x] 3.2 Add a decision-status service/controller path that validates action, lodging id, source scope, and active trip before updating state
- [x] 3.3 Update `/清單` Flex cards so candidate cards use content tap targets for source listing, `已訂這間` postback as primary action, and `旅次詳情` as secondary action
- [x] 3.4 Update booked lodging cards to show `已預訂`, expose `改回候選`, and preserve the trip detail action
- [x] 3.5 Add webhook tests for valid booked/revert postbacks, stale or out-of-scope postbacks, and Flex card action layout

## 4. Dismissal And Trip Detail Management

- [x] 4.1 Add decision-status controls and filters to the trip detail page for candidate, booked, and dismissed states
- [x] 4.2 Expose `不考慮這間` from trip detail candidate management without adding it to the default `/清單` card footer
- [x] 4.3 Expose restore-to-candidate behavior for dismissed lodgings from the trip detail management surface
- [x] 4.4 Add route/rendering tests for dismissal controls, dismissed filtering, and restore controls

## 5. Notion And Documentation

- [x] 5.1 Add decision-status property support to Notion schema setup and lodging page property mapping
- [x] 5.2 Update README or operator docs to explain `已訂這間`, `改回候選`, and `不考慮這間`
- [x] 5.3 Document that decision status is user-owned and independent from source availability

## 6. Verification

- [x] 6.1 Run focused tests for trip display, webhook, repository, and Notion sync behavior
- [x] 6.2 Run the full test suite and fix regressions
- [x] 6.3 Manually inspect rendered `/清單` Flex payloads to confirm the footer remains compact
