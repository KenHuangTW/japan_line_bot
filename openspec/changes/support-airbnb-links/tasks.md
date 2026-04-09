## 1. Airbnb Link Detection

- [x] 1.1 Add Airbnb to supported domain defaults and user-facing copy that lists supported lodging platforms
- [x] 1.2 Implement an Airbnb lodging-link classifier and wire it into `LodgingLinkService`, canonical URL normalization, and resolution planning
- [x] 1.3 Add unit tests for Airbnb extraction, non-listing rejection, and canonical duplicate lookup behavior

## 2. Airbnb Enrichment And Capture Flow

- [x] 2.1 Extend map enrichment parsing and fallback logic so Airbnb listings can produce best-effort public metadata
- [x] 2.2 Update webhook and repository flow coverage for Airbnb listing capture, duplicate detection, and partial enrichment outcomes
- [x] 2.3 Add enrichment service and API/job tests for Airbnb full-metadata and partial-metadata scenarios

## 3. Notion Sync And Documentation

- [x] 3.1 Add `airbnb` as a first-class platform option in Notion schema management and sync payload generation
- [x] 3.2 Add Notion sync tests covering Airbnb records and target schema updates
- [x] 3.3 Update README and related documentation to describe Airbnb support and first-phase limitations
