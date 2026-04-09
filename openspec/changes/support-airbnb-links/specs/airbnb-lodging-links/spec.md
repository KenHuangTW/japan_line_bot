## ADDED Requirements

### Requirement: Capture supported Airbnb listing URLs
The system SHALL treat public Airbnb room listing URLs whose canonical path matches a single listing page as supported lodging links, and SHALL ignore Airbnb URLs that do not represent an individual lodging listing.

#### Scenario: Direct Airbnb room listing is extracted
- **WHEN** a LINE message contains `https://www.airbnb.com/rooms/123456789`
- **THEN** the extractor returns a lodging link match with platform `airbnb` and hostname `airbnb.com`

#### Scenario: Non-listing Airbnb pages are ignored
- **WHEN** a LINE message contains Airbnb search, category, wishlist, profile, or other non-room URLs
- **THEN** lodging-link filtering excludes those URLs from captured lodging records

### Requirement: Canonicalize Airbnb listings for duplicate lookup
The system SHALL normalize accepted Airbnb listing URLs so that duplicate lookup and persistence treat the same listing as equivalent across optional `www` hostnames and tracking query parameters.

#### Scenario: Query parameters do not create a new record
- **WHEN** the same Airbnb listing is received in the same chat scope once with tracking query parameters and once without them
- **THEN** duplicate detection treats both URLs as the same lodging record

#### Scenario: Accepted Airbnb listing keeps canonical metadata
- **WHEN** an Airbnb listing passes lodging validation
- **THEN** the stored match retains `platform = airbnb` and stores the canonical resolved listing URL for downstream lookup

### Requirement: Enrich Airbnb listings with best-effort public metadata
The system SHALL send accepted Airbnb listings through the existing enrichment pipeline and SHALL populate any metadata that can be derived from public page HTML or structured data without rejecting the listing when some fields are unavailable.

#### Scenario: Structured data provides listing metadata
- **WHEN** an Airbnb listing page exposes public metadata for listing name and location
- **THEN** enrichment stores the available property, address, coordinate, room-detail, amenity, and pricing fields on the lodging record

#### Scenario: Partial metadata still produces a usable enrichment result
- **WHEN** an Airbnb listing page exposes only partial public metadata such as title or address
- **THEN** enrichment preserves the listing, fills the available fields, and leaves unavailable fields empty instead of failing the capture flow

### Requirement: Sync Airbnb records to Notion as a first-class platform
The system SHALL allow Airbnb lodging records to sync to Notion without manual schema edits and SHALL expose `airbnb` as a selectable platform value.

#### Scenario: Notion target includes Airbnb platform option
- **WHEN** the Notion sync service ensures or updates the target data source schema
- **THEN** the platform property definition contains an `airbnb` option

#### Scenario: Synced Notion page retains Airbnb platform
- **WHEN** an Airbnb lodging record is created or updated in Notion
- **THEN** the page stores `airbnb` in the platform property and keeps the listing URL in the lodging URL property
