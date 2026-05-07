## ADDED Requirements

### Requirement: Text Message Snapshot Persistence
The system SHALL persist inbound LINE text message snapshots so later quoted-message commands can resolve the original message text.

#### Scenario: Store inbound text message
- **WHEN** the webhook receives a LINE text message event with a message id
- **THEN** the system stores the message id, source scope, sender user id, text body, timestamp, and creation time in the message snapshot collection

#### Scenario: Ignore non-text message bodies
- **WHEN** the webhook receives a non-text message event
- **THEN** the system does not store a text body snapshot for that event

#### Scenario: Snapshot retention is applied
- **WHEN** a text message snapshot is stored
- **THEN** the system records retention metadata so old snapshots can be expired or ignored according to configuration

### Requirement: Quoted Message Resolution
The system SHALL resolve quoted-message command input by looking up the quoted message id within the same effective chat scope.

#### Scenario: Resolve quoted itinerary text
- **WHEN** a user sends `/整理行程` with no inline itinerary text and the webhook message includes `quotedMessageId`
- **THEN** the system looks up the quoted message snapshot and uses its text as the itinerary import input

#### Scenario: Missing quoted snapshot
- **WHEN** a user sends `/整理行程` with `quotedMessageId` but no matching snapshot exists
- **THEN** the system replies that the quoted message content cannot be found and does not create an itinerary draft

#### Scenario: Quoted snapshot is scoped
- **WHEN** a quoted message id exists in a different LINE source scope from the command event
- **THEN** the system does not use that snapshot as itinerary input

### Requirement: LINE Quote Metadata
The system SHALL parse and expose LINE quote metadata from text message webhook events.

#### Scenario: Parse quoted message id
- **WHEN** a LINE text message webhook includes `message.quotedMessageId`
- **THEN** the validated webhook model preserves that quoted message id for command handling

#### Scenario: Preserve quote token for future reply behavior
- **WHEN** a LINE text message webhook includes `message.quoteToken`
- **THEN** the validated webhook model preserves the quote token in the snapshot when available
