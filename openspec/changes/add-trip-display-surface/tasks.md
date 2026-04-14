## 1. Trip Display Data Model

- [x] 1.1 Add the trip display token or share-link model needed to open a read-only trip detail surface without exposing raw LINE scope ids
- [x] 1.2 Implement canonical trip display queries that aggregate lodging records, trip metadata, and optional Notion export metadata from Mongo
- [x] 1.3 Add tests covering valid trip display lookup, invalid token handling, and trips without Notion targets

## 2. Display Surfaces

- [x] 2.1 Add a mobile-friendly read-only trip detail route and template that render lodging candidates with basic filtering and sorting
- [x] 2.2 Update `/清單` to return a readable LINE preview plus a link or button to the trip detail surface instead of only a Notion URL
- [x] 2.3 Add controller and integration tests covering LINE preview output, detail page rendering, and missing active trip behavior

## 3. Product Positioning And Docs

- [x] 3.1 Update README and operator docs to describe Mongo as source of truth, the new trip detail surface, and Notion as an optional export target
- [x] 3.2 Document the integration point with `add-lodging-decision-summary`, so AI summaries can consume the same canonical trip display payload later
