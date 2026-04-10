## ADDED Requirements

### Requirement: Generate a structured decision summary for the active trip
The system SHALL provide an on-demand decision summary for the active trip using the trip's collected lodging data.

#### Scenario: Summary command returns candidate-oriented output
- **WHEN** a user sends the summary command in a LINE chat with an active trip that already has lodging records
- **THEN** the system returns a summary containing candidate accommodations, pros, cons, missing information, and discussion points for that trip

#### Scenario: Empty trip returns an actionable empty state
- **WHEN** a user sends the summary command in a LINE chat with an active trip that has no lodging records
- **THEN** the system replies that there is no lodging data to summarize for the current trip

#### Scenario: Summary command requires an active trip
- **WHEN** a user sends the summary command in a LINE chat that has no active trip
- **THEN** the system replies with guidance to create or switch a trip before requesting a summary

### Requirement: AI summary input and output SHALL be structured and deterministic
The system SHALL build the AI summary request from normalized lodging fields for the active trip and SHALL validate the model output against a defined response schema before rendering it to LINE.

#### Scenario: Summary request uses normalized lodging fields
- **WHEN** the system prepares an AI summary request for the active trip
- **THEN** it sends structured lodging attributes such as property name, platform, price, availability, location, amenities, and timestamps instead of raw LINE chat transcripts

#### Scenario: Model output matches the summary schema
- **WHEN** the AI provider returns a valid summary response
- **THEN** the system parses it against the summary schema and renders the validated sections into the LINE reply

### Requirement: Summary generation SHALL fail safely
The system SHALL isolate AI summary failures so that they do not mutate lodging or trip data.

#### Scenario: AI provider failure returns a user-facing error
- **WHEN** the AI provider times out, is unavailable, or returns invalid output for a summary request
- **THEN** the system replies that the summary could not be generated and leaves the trip and lodging records unchanged
