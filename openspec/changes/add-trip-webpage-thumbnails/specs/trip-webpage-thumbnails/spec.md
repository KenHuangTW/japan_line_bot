## ADDED Requirements

### Requirement: Trip detail page SHALL render lodging thumbnails
The system SHALL render a visual thumbnail area for each lodging card on the trip detail page using canonical lodging image metadata when available.

#### Scenario: Lodging with image shows thumbnail
- **WHEN** a user opens `/trips/{display_token}` for a trip whose lodging record has an image URL in canonical trip display data
- **THEN** the lodging card includes an HTML image thumbnail for that lodging while preserving the lodging name, platform, status, price, links, and decision actions

#### Scenario: Thumbnail links preserve lodging navigation
- **WHEN** a lodging card renders a thumbnail and the lodging has a target URL
- **THEN** the thumbnail links to the lodging target URL using the same external-link behavior as the text link

### Requirement: Trip detail thumbnails SHALL degrade gracefully
The system SHALL keep the trip detail page readable and stable when a lodging record has no usable image URL.

#### Scenario: Lodging without image shows fallback
- **WHEN** a user opens `/trips/{display_token}` for a trip containing lodging records without image URLs
- **THEN** those lodging cards render a fixed-size fallback area instead of omitting the media area or breaking the card layout

#### Scenario: Mixed image availability keeps layout consistent
- **WHEN** a trip detail page contains both lodgings with thumbnails and lodgings without thumbnails
- **THEN** the cards maintain consistent spacing and the filters, links, and decision controls remain usable on mobile and desktop viewports

### Requirement: Trip detail thumbnail rendering SHALL be safe
The system SHALL escape image URLs and text used in thumbnail markup before rendering the read-only trip detail HTML.

#### Scenario: Image fields contain special characters
- **WHEN** a lodging image URL or display name contains characters that require HTML attribute escaping
- **THEN** the rendered thumbnail markup escapes those values and does not introduce executable HTML or broken attributes
