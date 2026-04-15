## ADDED Requirements

### Requirement: Configured control chat SHALL override the target scope for scope-sensitive LINE commands
The system SHALL allow an optional env-based group mapping that treats one LINE group as a control chat and another LINE group as the data target for scope-sensitive commands.

#### Scenario: Current trip command from the control group reads the target group state
- **WHEN** `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID` and `LINE_COMMAND_CONTROL_TARGET_GROUP_ID` are configured and a user sends `/目前旅次` from the configured control group
- **THEN** the system resolves the active trip from the configured target group instead of the control group

#### Scenario: Trip creation command from the control group creates a trip under the target group
- **WHEN** the control-group mapping is configured and a user sends `/建立旅次 東京 2026` from the configured control group
- **THEN** the system creates or switches the trip under the configured target group scope instead of the control group scope

#### Scenario: Unmatched group keeps the original command scope
- **WHEN** a user sends a scope-sensitive LINE command from a group that does not match `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID`
- **THEN** the system resolves the command against that message's original LINE source scope

### Requirement: Trip-scoped command workflows SHALL honor the overridden target scope
The system SHALL apply the configured command target scope consistently across trip-scoped command workflows that depend on chat or active-trip resolution.

#### Scenario: List command returns the target group's active trip surface
- **WHEN** the control-group mapping is configured and a user sends `/清單` from the configured control group
- **THEN** the system builds the list response from the active trip owned by the configured target group

#### Scenario: Pending sync command runs against the target group's active trip
- **WHEN** the control-group mapping is configured and a user sends `/整理` from the configured control group
- **THEN** the system runs enrichment and Notion sync only for the active trip resolved from the configured target group

#### Scenario: Force sync command runs against the target group's active trip
- **WHEN** the control-group mapping is configured and a user sends `/全部重來` from the configured control group
- **THEN** the system retries enrichment and Notion sync only for the active trip resolved from the configured target group

### Requirement: Lodging capture from the control group SHALL persist under the target group while replying in the control group
The system SHALL apply the configured target scope to ordinary lodging-link capture, duplicate lookup, persisted records, and downstream sync jobs, while keeping the LINE reply attached to the original control-group event.

#### Scenario: Lodging link posted in the control group is stored under the target group
- **WHEN** the control-group mapping is configured and a user posts a supported lodging URL in the configured control group without using a LINE command
- **THEN** the system resolves capture eligibility, duplicate lookup, and persisted source fields using the configured target group instead of the control group

#### Scenario: Lodging capture reply stays in the control group
- **WHEN** the control-group mapping is configured and a user posts a supported lodging URL in the configured control group
- **THEN** the system sends duplicate or capture reply messages back through the original control-group event reply channel

#### Scenario: Duplicate lookup uses the target group scope
- **WHEN** the control-group mapping is configured, the configured target group already contains the same lodging URL in its active trip, and a user posts that lodging URL in the control group
- **THEN** the system treats the post as a duplicate of the target group's active trip data instead of creating a new capture under the control group

#### Scenario: Capture requires the target group's active trip
- **WHEN** the control-group mapping is configured, the control group has an active trip, the target group has no active trip, and a user posts a supported lodging URL in the control group
- **THEN** the system rejects capture because the configured target group has no active trip

#### Scenario: Automatic sync after capture uses the target group scope
- **WHEN** the control-group mapping is configured and a control-group lodging post is accepted for capture
- **THEN** any automatic enrichment or Notion sync triggered by that capture runs against the configured target group's scope

### Requirement: Incomplete override configuration SHALL safely fall back to current behavior
The system SHALL ignore the target override and keep the original source-based behavior unless the required control-group and target-group settings are both configured and matched.

#### Scenario: Partial env configuration is ignored
- **WHEN** only one of `LINE_COMMAND_CONTROL_SOURCE_GROUP_ID` or `LINE_COMMAND_CONTROL_TARGET_GROUP_ID` is configured
- **THEN** the system resolves commands and lodging capture against the original LINE source scope

#### Scenario: Non-group source does not use the override
- **WHEN** the configured mapping exists but the LINE event source is a `room` or `user`
- **THEN** the system resolves commands and lodging capture against the original LINE source scope
