## 1. Thumbnail Rendering

- [x] 1.1 Add a trip detail thumbnail helper that selects `hero_image_url` first and falls back to `line_hero_image_url`.
- [x] 1.2 Update lodging card HTML to render a fixed-size thumbnail area with escaped image URL, escaped alt text, and original lodging link behavior.
- [x] 1.3 Add responsive CSS so thumbnail cards remain readable on mobile and desktop, including stable fallback layout for lodgings without images.

## 2. Regression Coverage

- [x] 2.1 Add HTML rendering tests for lodging cards with thumbnails, fallback cards without thumbnails, and mixed image availability.
- [x] 2.2 Add escaping coverage for image URLs and display names used in thumbnail markup.
- [x] 2.3 Add or update route-level tests proving `/trips/{display_token}` returns thumbnail markup without losing existing filters, links, and decision actions.

## 3. Documentation And Validation

- [x] 3.1 Update README trip display documentation to mention that the web detail page shows lodging thumbnails when available.
- [x] 3.2 Run focused trip display and webhook tests for the changed rendering surface.
- [x] 3.3 Run OpenSpec status/validation for `add-trip-webpage-thumbnails` and confirm the change is apply-ready.
