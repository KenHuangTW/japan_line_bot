## ADDED Requirements

### Requirement: Lodging records have a user decision status
The system SHALL store a user-controlled decision status for each captured lodging record, independent from source availability.

#### Scenario: Newly captured lodging defaults to candidate
- **WHEN** the system captures a new lodging link for a trip
- **THEN** the lodging decision status is `candidate`

#### Scenario: Existing lodging without decision status is read as candidate
- **WHEN** the system reads an existing lodging record that does not contain decision status
- **THEN** the lodging is treated as `candidate`

#### Scenario: Availability and decision are independent
- **WHEN** a lodging has source availability `sold_out` and decision status `booked`
- **THEN** the system preserves both values and displays them as separate concepts

### Requirement: Users can mark a candidate lodging as booked from LINE
The system SHALL allow a LINE user to mark a candidate lodging as `booked` through a button-driven postback action.

#### Scenario: Candidate card exposes booked action
- **WHEN** `/清單` renders a candidate lodging card
- **THEN** the card provides an `已訂這間` postback action and a `旅次詳情` action

#### Scenario: Card content opens the source listing
- **WHEN** `/清單` renders a lodging card with a source listing URL
- **THEN** tapping the card image or lodging title opens the source listing URL

#### Scenario: Booked postback updates the lodging
- **WHEN** LINE sends a valid booked postback for a lodging in the current trip scope
- **THEN** the system updates that lodging decision status to `booked`
- **AND** replies with a confirmation naming the lodging

#### Scenario: Invalid booked postback is rejected safely
- **WHEN** LINE sends a booked postback for a lodging outside the current trip scope or with an unknown document id
- **THEN** the system does not update any lodging
- **AND** replies with a concise failure message

### Requirement: Users can revert a booked lodging to candidate
The system SHALL allow a LINE user to change a booked lodging back to `candidate`.

#### Scenario: Booked card exposes revert action
- **WHEN** `/清單` renders a booked lodging card
- **THEN** the card displays an `已預訂` status indicator
- **AND** provides a `改回候選` postback action

#### Scenario: Revert postback updates the lodging
- **WHEN** LINE sends a valid candidate postback for a booked lodging in the current trip scope
- **THEN** the system updates that lodging decision status to `candidate`
- **AND** replies with a confirmation naming the lodging

### Requirement: Users can dismiss unsuitable lodgings without crowding the LINE card
The system SHALL support changing a lodging decision status to `dismissed` while keeping dismissal out of the default `/清單` card footer.

#### Scenario: Candidate card does not expose dismissal in the default footer
- **WHEN** `/清單` renders a candidate lodging card
- **THEN** the default footer does not include `不考慮這間`

#### Scenario: Trip detail exposes dismissal management
- **WHEN** the trip detail page renders candidate lodging management controls
- **THEN** it provides a `不考慮這間` action for each candidate lodging

#### Scenario: Dismissed lodging can be restored
- **WHEN** the trip detail page renders a dismissed lodging
- **THEN** it provides a way to change the lodging back to `candidate`

### Requirement: Decision status affects default trip display
The system SHALL make booked and candidate lodgings visible by default and hide dismissed lodgings from default review surfaces.

#### Scenario: Default list excludes dismissed lodgings
- **WHEN** a trip contains candidate, booked, and dismissed lodgings
- **THEN** `/清單` and the default trip detail view include candidate and booked lodgings
- **AND** they exclude dismissed lodgings from the visible cards

#### Scenario: Display summary counts all decision states
- **WHEN** `/清單` or trip detail renders a trip summary
- **THEN** the summary includes counts for booked, candidate, and dismissed lodgings

#### Scenario: Dismissed filter reveals dismissed lodgings
- **WHEN** the trip detail page is filtered to dismissed lodgings
- **THEN** dismissed lodgings are shown with their status and restore action

### Requirement: Decision status is available to downstream surfaces
The system SHALL expose lodging decision status through trip display payloads and Notion sync output.

#### Scenario: Trip display payload includes decision status
- **WHEN** the system builds a trip display payload
- **THEN** each lodging item includes its decision status

#### Scenario: Notion sync includes decision status
- **WHEN** the system syncs a lodging record to a managed Notion target
- **THEN** the Notion page includes a decision-status select value matching the lodging decision status

#### Scenario: Decision status metadata is persisted on changes
- **WHEN** a user changes a lodging decision status
- **THEN** the system stores the update timestamp
- **AND** stores the LINE user id when it is available
