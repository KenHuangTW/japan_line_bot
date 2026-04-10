## ADDED Requirements

### Requirement: Manage an active trip context per LINE chat
The system SHALL allow each LINE chat scope to create, switch, inspect, and archive an active trip context before collecting lodging links.

#### Scenario: Create and activate a new trip
- **WHEN** a user sends a trip creation command with a trip title in a LINE chat
- **THEN** the system creates a new trip for that chat scope and marks it as the active trip

#### Scenario: Switch to another open trip
- **WHEN** a user sends a trip switch command that references another existing, non-archived trip in the same LINE chat
- **THEN** the system marks that trip as the active trip for subsequent commands and captures

#### Scenario: Inspect current trip context
- **WHEN** a user sends a current-trip command in a LINE chat that has an active trip
- **THEN** the system replies with the active trip identity and status

#### Scenario: Archive the active trip
- **WHEN** a user sends an archive-trip command for the current active trip
- **THEN** the system marks that trip as archived and clears it as the active trip for that LINE chat

### Requirement: Capture and duplicate lookup SHALL be isolated by trip
The system SHALL store accepted lodging links under the active trip and SHALL treat duplicate lookup as trip-scoped rather than chat-scoped.

#### Scenario: Captured lodging is stored under the active trip
- **WHEN** a LINE message contains a supported lodging URL and the chat has an active trip
- **THEN** the stored lodging record includes the active trip identifier and title

#### Scenario: Same listing in another trip is allowed
- **WHEN** the same lodging URL is posted in the same LINE chat after switching to a different trip
- **THEN** the system stores it as a new trip-specific lodging record instead of treating it as a duplicate

#### Scenario: Capture is blocked without an active trip
- **WHEN** a LINE message contains a supported lodging URL but the chat has no active trip
- **THEN** the system does not capture the lodging link and replies with guidance to create or switch a trip first

### Requirement: Trip-scoped commands SHALL use the active trip target
The system SHALL resolve `/清單`, `/整理`, and `/全部重來` against the active trip rather than only the LINE chat scope.

#### Scenario: List command returns the active trip target
- **WHEN** a user sends `/清單` in a LINE chat with an active trip
- **THEN** the system returns the Notion link associated with that trip

#### Scenario: Pending sync command processes only the active trip
- **WHEN** a user sends `/整理` in a LINE chat with an active trip
- **THEN** the system runs enrichment and Notion sync only for lodging records belonging to that trip

#### Scenario: Force sync command processes only the active trip
- **WHEN** a user sends `/全部重來` in a LINE chat with an active trip
- **THEN** the system retries enrichment and Notion sync only for lodging records belonging to that trip
