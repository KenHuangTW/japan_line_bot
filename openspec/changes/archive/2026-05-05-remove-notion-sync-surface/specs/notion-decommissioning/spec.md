## ADDED Requirements

### Requirement: User-facing trip surfaces SHALL not expose Notion
The system SHALL render LINE replies, LINE previews, trip detail pages, and summary outputs without Notion setup links, Notion page links, Notion export shortcuts, or Notion sync status.

#### Scenario: Trip list reply excludes Notion export
- **WHEN** a user sends `/清單` for an active trip with lodging records
- **THEN** the system replies with the Mongo-backed trip preview and trip detail entrypoint
- **AND** the reply does not include a Notion export URL or Notion sync status

#### Scenario: Trip detail page excludes Notion links
- **WHEN** a user opens a valid trip detail page for a trip whose historical records contain `notion_*` fields
- **THEN** the page renders lodging details from canonical Mongo fields
- **AND** the page does not render Notion export shortcuts or per-lodging Notion page links

#### Scenario: Capture reply avoids Notion terminology
- **WHEN** the system successfully captures lodging links from LINE
- **THEN** the reply describes the records as saved or queued for app-side整理
- **AND** the reply does not claim that records will sync to Notion

### Requirement: Manual整理 commands SHALL refresh Mongo canonical lodging data only
The system SHALL keep active-trip manual整理 commands available while removing Notion sync behavior from those commands.

#### Scenario: Pending整理 refreshes active trip enrichment
- **WHEN** a user sends `/整理` in a LINE chat with an active trip
- **THEN** the system reruns eligible lodging/map enrichment work only for that active trip
- **AND** the system updates Mongo canonical records without creating, resolving, or syncing a Notion target

#### Scenario: Force整理 refreshes all active trip records
- **WHEN** a user sends `/全部重來` in a LINE chat with an active trip
- **THEN** the system force-reruns lodging/map enrichment for lodging records in that active trip
- **AND** the system updates Mongo canonical records without creating, resolving, or syncing a Notion target

#### Scenario:整理 response reports app data refresh
- **WHEN** `/整理` or `/全部重來` completes
- **THEN** the LINE reply reports enrichment or trip data refresh results
- **AND** the reply does not report Notion synced, failed, skipped, or target-created counts

### Requirement: Notion sync APIs and jobs SHALL be removed from the supported application surface
The system SHALL no longer expose Notion sync HTTP routes, standalone jobs, configuration, or app startup wiring.

#### Scenario: Notion sync routes are unavailable
- **WHEN** a client requests a `/jobs/notion-sync/*` endpoint
- **THEN** the application does not route the request to a supported Notion sync handler

#### Scenario: Notion standalone job is not supported
- **WHEN** operators review documented background jobs
- **THEN** no supported `app.notion_sync_job` workflow is documented or required

#### Scenario: Application starts without Notion configuration
- **WHEN** the application starts with no Notion environment variables configured
- **THEN** app startup, LINE commands, trip display, summary, and enrichment behavior remain available according to their own configuration requirements

### Requirement: Scheduled refresh SHALL not depend on Notion
The system SHALL run active-trip scheduled refresh through lodging/map enrichment and Mongo updates without downstream Notion sync.

#### Scenario: Scheduled refresh updates Mongo records
- **WHEN** the scheduled trip refresh processes an active trip
- **THEN** it refreshes lodging/map data for records in that trip and persists updates to Mongo
- **AND** the trip detail page can show refreshed data without a Notion sync step

#### Scenario: Scheduled refresh skips Notion target resolution
- **WHEN** the scheduled trip refresh runs for active trips
- **THEN** it does not resolve Notion targets, create Notion data sources, or call Notion sync services

### Requirement: Historical Notion fields SHALL be treated as ignored legacy data
The system SHALL tolerate existing `notion_*` fields in Mongo documents while no longer reading or mutating them for product behavior.

#### Scenario: Existing records with Notion fields remain readable
- **WHEN** a stored lodging record contains historical Notion identifiers, URLs, sync status, or timestamps
- **THEN** trip display, summaries, duplicate lookup, and enrichment processing continue to read the record successfully
- **AND** those Notion fields do not affect rendered output or processing decisions

#### Scenario: New enrichment does not write Notion status
- **WHEN** lodging records are captured or refreshed after Notion decommissioning
- **THEN** the system does not initialize or update Notion sync status, Notion IDs, Notion URLs, or Notion target metadata as part of the active workflow
