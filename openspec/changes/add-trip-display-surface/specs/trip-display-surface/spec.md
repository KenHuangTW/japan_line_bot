## ADDED Requirements

### Requirement: `/清單` SHALL return a readable trip display entrypoint
The system SHALL return a human-readable trip preview for the active trip and SHALL provide an entrypoint to a richer display surface instead of relying only on a Notion table link.

#### Scenario: Active trip list command returns preview and detail entrypoint
- **WHEN** a user sends `/清單` in a LINE chat that has an active trip with captured lodging records
- **THEN** the system replies with a readable preview of that trip's lodging candidates and includes a link or button to open the trip detail surface

#### Scenario: List command still works without a Notion target
- **WHEN** a user sends `/清單` for an active trip that has no configured Notion target
- **THEN** the system still returns the trip preview and detail entrypoint based on Mongo data

### Requirement: The system SHALL provide a read-only trip detail surface
The system SHALL expose a mobile-friendly, read-only trip detail surface that renders lodging records for a specific trip directly from canonical storage.

#### Scenario: Trip detail page shows active trip lodging records
- **WHEN** a user opens the generated trip detail link for a valid trip display token
- **THEN** the system renders that trip's lodging records with readable fields such as lodging name, platform, availability, pricing, and map links

#### Scenario: Trip detail page supports lightweight filtering and sorting
- **WHEN** a user opens the trip detail surface for a trip with multiple lodging records
- **THEN** the system allows the user to apply basic filters or sorting options without editing the underlying lodging records

#### Scenario: Invalid detail token is rejected
- **WHEN** a user opens a trip detail link with an unknown or invalid token
- **THEN** the system returns a not-found or invalid-link response instead of exposing unrelated trip data

### Requirement: Display surfaces SHALL treat Notion as an optional export target
The system SHALL build trip display surfaces from canonical lodging data and SHALL treat Notion links as optional secondary actions rather than the primary rendered content.

#### Scenario: Detail surface can include a Notion export shortcut
- **WHEN** a trip has an associated Notion export target
- **THEN** the trip detail surface may include a secondary link to open that Notion view

#### Scenario: Display continues when Notion schema changes
- **WHEN** the Notion table for a trip is outdated, unavailable, or absent
- **THEN** the LINE preview and trip detail surface continue to render from canonical storage without requiring a Notion migration first
