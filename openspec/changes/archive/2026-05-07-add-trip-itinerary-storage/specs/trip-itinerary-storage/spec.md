## ADDED Requirements

### Requirement: Itinerary Import Sources
The system SHALL persist each itinerary import input as a trip-scoped source record before generating or applying itinerary changes.

#### Scenario: Direct command text creates a source
- **WHEN** a user sends `/整理行程` followed by itinerary text and the resolved target chat has an active trip
- **THEN** the system stores the command text as an itinerary source associated with that active trip

#### Scenario: Quoted command creates a source from snapshot text
- **WHEN** a user sends `/整理行程` while quoting a previously snapshotted text message and the resolved target chat has an active trip
- **THEN** the system stores the quoted message text as an itinerary source associated with that active trip

#### Scenario: Import requires an active trip
- **WHEN** a user sends `/整理行程` with direct or quoted itinerary text and the resolved target chat has no active trip
- **THEN** the system does not create an itinerary source and replies with the active-trip-required guidance

### Requirement: AI Itinerary Draft Generation
The system SHALL transform each itinerary source into a validated pending draft before changing confirmed itinerary items.

#### Scenario: Structured itinerary produces draft items
- **WHEN** an itinerary source contains dated itinerary rows with time ranges, locations, and notes
- **THEN** the system creates a pending draft containing proposed itinerary items with date, time, timezone, title, location name, description, item type, and status fields

#### Scenario: Optional rows remain tentative
- **WHEN** an itinerary row includes optional wording such as `可選` or free-time wording
- **THEN** the proposed item is marked as optional or tentative instead of confirmed

#### Scenario: Daily notes are preserved without forcing calendar events
- **WHEN** an itinerary source contains day-level note sections such as shopping priorities
- **THEN** the system stores those notes in the draft without requiring them to become timed itinerary events

#### Scenario: Invalid AI output is rejected
- **WHEN** the AI provider returns output that fails schema validation or references source rows that were not parsed
- **THEN** the system does not create an applyable draft and replies that itinerary organization failed

### Requirement: Itinerary Diff Drafts
The system SHALL compare newly proposed itinerary items with existing confirmed items and expose a pending diff draft.

#### Scenario: New itinerary rows are additions
- **WHEN** an imported itinerary contains rows that do not match existing confirmed itinerary items
- **THEN** the pending draft marks those rows as additions

#### Scenario: Changed itinerary rows are updates
- **WHEN** an imported itinerary contains a row that matches an existing item by stable identity but changes time, title, location, or description
- **THEN** the pending draft marks that row as an update to the existing item

#### Scenario: Missing rows are possible deletions
- **WHEN** an imported full itinerary no longer contains a row that exists as a confirmed item
- **THEN** the pending draft marks that item as a possible deletion and does not delete it until the draft is applied according to the deletion policy

### Requirement: Itinerary Draft Confirmation
The system SHALL require explicit user confirmation before pending itinerary drafts modify confirmed itinerary items.

#### Scenario: Apply latest pending draft
- **WHEN** a user sends `/套用行程` and the resolved active trip has a latest pending draft
- **THEN** the system applies the draft changes to confirmed itinerary items and marks the draft as applied

#### Scenario: Discard latest pending draft
- **WHEN** a user sends `/取消行程` and the resolved active trip has a latest pending draft
- **THEN** the system marks the draft as discarded without changing confirmed itinerary items

#### Scenario: Apply command without pending draft
- **WHEN** a user sends `/套用行程` and there is no pending draft for the active trip
- **THEN** the system replies that no itinerary draft is waiting to be applied

### Requirement: Confirmed Itinerary Display
The system SHALL let users read confirmed itinerary items for the active trip from MongoDB.

#### Scenario: List confirmed itinerary
- **WHEN** a user sends `/行程` and the resolved active trip has confirmed itinerary items
- **THEN** the system replies with a chronological itinerary summary grouped by date

#### Scenario: Empty itinerary
- **WHEN** a user sends `/行程` and the resolved active trip has no confirmed itinerary items
- **THEN** the system replies that the trip does not yet have confirmed itinerary data
