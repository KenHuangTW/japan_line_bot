## 1. Trip Log Shell

- [x] 1.1 Replace the current gradient hero and dashboard grid CSS in `app/trip_display/rendering.py` with a centered document sheet layout, restrained palette, thin dividers, and system serif/sans/mono font stacks
- [x] 1.2 Update the trip header markup to show the trip log eyebrow, trip title, compact statistics grid, and optional Notion export action within the document sheet
- [x] 1.3 Restyle filter and sort controls so platform, availability, decision status, sort, apply, and reset remain functional while matching the quieter trip log visual language

## 2. Lodging Review Rows

- [x] 2.1 Refactor lodging item markup from large dashboard cards into compact review rows with row number, platform metadata, decision badges, thumbnail area, lodging title, and secondary metadata
- [x] 2.2 Preserve source, map, Notion, and decision-status actions in the new row layout with wrapping mobile-safe controls
- [x] 2.3 Implement stable thumbnail and fallback markup so rows keep consistent dimensions when images are present or missing
- [x] 2.4 Update the empty state so it matches the document style and does not look like a separate dashboard card

## 3. Responsive And Accessibility Checks

- [x] 3.1 Add mobile media rules that keep the sheet, controls, thumbnails, long titles, links, and decision buttons from overlapping or creating horizontal scroll
- [x] 3.2 Ensure optional fields such as address, maps URL, Notion page URL, price, availability, and image URL are omitted or replaced with clear fallbacks without broken separators

## 4. Tests And Verification

- [x] 4.1 Update `tests/test_trip_display.py` to assert the new trip log shell, statistics grid, row classes, thumbnail/fallback behavior, filter controls, and decision actions
- [x] 4.2 Run focused trip display tests
- [x] 4.3 Run the full test suite if the focused tests pass

## 5. Desktop RWD Refinement

- [x] 5.1 Expand the desktop trip log shell beyond the mobile-sized sheet so desktop users get a wider lodging review surface
- [x] 5.2 Add tablet and phone breakpoints for statistics, controls, thumbnail dimensions, and row spacing
- [x] 5.3 Update tests to assert the desktop width and responsive breakpoint hooks
- [x] 5.4 Re-run focused and full tests

## 6. Desktop Reference Alignment

- [x] 6.1 Rework the desktop trip detail layout to follow the provided sidebar-plus-list reference instead of the centered single-sheet layout
- [x] 6.2 Move platform and quick-filter navigation into the sidebar while keeping availability, decision status, sort, apply, and reset controls available in the main toolbar
- [x] 6.3 Refine lodging rows to match the desktop reference structure with index column, larger thumbnail, tag row, inline actions, and muted secondary links
- [x] 6.4 Update tests and re-run focused/full suites after the desktop reference alignment
