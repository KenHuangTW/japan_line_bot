## ADDED Requirements

### Requirement: Refresh job SHALL process active trips only
The system SHALL provide a batch refresh job that targets active trips and skips archived trips.

#### Scenario: Scheduled refresh enumerates active trips
- **WHEN** the trip refresh job is triggered by an external scheduler
- **THEN** the system discovers the currently active trips and schedules refresh work only for those trips

#### Scenario: Archived trips are skipped
- **WHEN** the trip refresh job encounters a trip that has been archived
- **THEN** the system does not refresh lodging records for that trip

### Requirement: Refresh work SHALL stay within each trip scope
The system SHALL rerun lodging refresh and downstream sync per trip using that trip's lodging records only.

#### Scenario: Refresh reruns enrichment for one trip
- **WHEN** the trip refresh job starts processing an active trip
- **THEN** it reruns lodging enrichment only for records belonging to that trip

#### Scenario: Refresh syncs updated trip records to Notion
- **WHEN** an active trip refresh completes for a trip that has a configured Notion target
- **THEN** the system syncs the refreshed records back to that trip's Notion data source

### Requirement: Refresh execution SHALL tolerate per-trip failures
The system SHALL continue processing other trips when one trip fails during a scheduled refresh run.

#### Scenario: One trip failure does not abort the batch
- **WHEN** refresh fails for one active trip during a scheduled run
- **THEN** the system records that failure and continues refreshing the remaining active trips
