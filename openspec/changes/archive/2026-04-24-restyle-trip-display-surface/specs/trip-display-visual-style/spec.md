## ADDED Requirements

### Requirement: Trip detail page uses a document-style trip log layout
The system SHALL render the trip detail page as a compact document-style trip log rather than a dashboard-style card grid.

#### Scenario: Trip page opens with trip log hierarchy
- **WHEN** a user opens a valid trip detail link
- **THEN** the page shows a centered trip log sheet with the trip title as the primary heading
- **AND** the page shows a small metadata label identifying the surface as a trip record or trip log
- **AND** the page uses thin dividers and a restrained off-white document background

#### Scenario: Trip page avoids dashboard visual treatment
- **WHEN** the trip detail page is rendered
- **THEN** the primary layout does not rely on decorative gradients, large rounded dashboard cards, or pill-only metric chips as the main visual structure

### Requirement: Trip summary is rendered as a compact statistics grid
The system SHALL present trip counts in a compact grid that supports quick comparison without dominating the first viewport.

#### Scenario: Summary shows existing trip counts
- **WHEN** a trip detail page is rendered
- **THEN** the summary includes visible counts for displayed lodgings, total lodgings, booked lodgings, candidate lodgings, dismissed lodgings, available lodgings, sold-out lodgings, and unknown-availability lodgings

#### Scenario: Summary remains readable on narrow screens
- **WHEN** the trip detail page is viewed on a mobile-width viewport
- **THEN** the statistics grid wraps or compresses without causing horizontal scrolling
- **AND** each count remains visually associated with its label

#### Scenario: Summary uses available desktop width
- **WHEN** the trip detail page is viewed on a desktop-width viewport
- **THEN** the document sheet expands beyond the narrow mobile reading width
- **AND** the statistics grid can show all primary count cells across the available desktop width without making the page feel like a phone-sized card

#### Scenario: Desktop layout uses sidebar and list pane
- **WHEN** the trip detail page is viewed on a desktop-width viewport
- **THEN** the page presents a sidebar for trip context and quick navigation
- **AND** the lodging list appears in a separate main pane with its own toolbar and scrolling surface

### Requirement: Lodging records are rendered as compact review rows
The system SHALL render each lodging as a compact review row with stable ordering, metadata, thumbnail treatment, links, and decision actions.

#### Scenario: Lodging row shows review information
- **WHEN** a lodging record is rendered in the trip detail page
- **THEN** the row shows a stable row number, platform label, lodging title, location or address when available, price label, availability label, decision status, and source link

#### Scenario: Lodging row exposes existing secondary links
- **WHEN** a lodging record has map or Notion page URLs
- **THEN** the row includes secondary actions for map and Notion access without making them the primary visual focus

#### Scenario: Lodging row exposes existing decision controls
- **WHEN** a lodging record is rendered in the trip detail page
- **THEN** the row provides the existing decision status actions that allow the user to mark the lodging as booked, candidate, or dismissed according to the current state

### Requirement: Thumbnail presentation is stable and graceful
The system SHALL render lodging thumbnails or fallbacks with stable dimensions so the lodging list remains scannable when images are present, missing, or slow to load.

#### Scenario: Lodging with image renders thumbnail
- **WHEN** a lodging has a usable hero image URL
- **THEN** the lodging row renders the image in a fixed thumbnail area
- **AND** the thumbnail links to the lodging source when a source URL is available

#### Scenario: Lodging without image renders fallback
- **WHEN** a lodging has no usable hero image URL
- **THEN** the lodging row renders a deterministic fallback thumbnail area
- **AND** the fallback includes enough platform or lodging context to avoid an empty visual block

#### Scenario: Thumbnail area does not shift row layout
- **WHEN** lodging rows contain a mix of images and fallback thumbnails
- **THEN** the thumbnail area keeps consistent dimensions within the same responsive breakpoint

### Requirement: Filters and sorting preserve functionality with quieter styling
The system SHALL preserve existing trip display filtering and sorting while restyling controls to fit the trip log document interface.

#### Scenario: Existing filters remain available
- **WHEN** the trip detail page is rendered
- **THEN** platform, availability, decision status, and sort controls are available
- **AND** submitting the controls preserves the existing query-parameter based filtering behavior

#### Scenario: Platform filter can use sidebar links
- **WHEN** the trip detail page is viewed on desktop-width viewport
- **THEN** platform filters may be rendered as sidebar links instead of a top-of-page select
- **AND** choosing a platform preserves the remaining active filters and sort in the generated query

#### Scenario: Reset remains available
- **WHEN** a filtered trip detail page is rendered
- **THEN** the page provides a reset action that returns to the unfiltered trip detail URL

### Requirement: The restyled page remains mobile-first and accessible
The system SHALL keep the restyled trip detail page usable on phone-sized screens with readable text, tappable controls, and no incoherent overlap.

#### Scenario: Layout adapts across desktop, tablet, and phone widths
- **WHEN** the trip detail page viewport changes between desktop, tablet, and phone widths
- **THEN** the sheet width, statistics grid, filter controls, thumbnail size, and row spacing adapt at responsive breakpoints
- **AND** the desktop layout uses more horizontal space while the mobile layout remains compact and readable

#### Scenario: Long lodging titles wrap safely
- **WHEN** a lodging title is long or contains mixed Chinese, Japanese, and English text
- **THEN** the title wraps within its row without overlapping metadata, thumbnails, links, or decision controls

#### Scenario: Action controls remain tappable
- **WHEN** the trip detail page is viewed on a mobile-width viewport
- **THEN** links, filter controls, reset controls, and decision buttons remain large enough to tap and do not overlap adjacent content

#### Scenario: Optional data does not create empty layout gaps
- **WHEN** a lodging lacks address, map URL, Notion page URL, price, or availability data
- **THEN** the row omits or falls back for that field without leaving broken separators, empty links, or misleading labels
