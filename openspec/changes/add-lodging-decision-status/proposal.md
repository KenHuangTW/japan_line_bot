## Why

Users can collect and review lodging candidates, but they currently cannot mark which lodging has already been booked or move unsuitable options out of the main candidate list. This matters now because `/清單` has become the primary trip review surface, and users need a low-friction, button-driven way to record lodging decisions without typing command IDs.

## What Changes

- Add a user-controlled lodging decision status separate from objective availability.
- Support three decision states for each lodging record: candidate, booked, and dismissed.
- Update `/清單` LINE Flex cards so candidate cards keep the content tap target for opening the source listing, expose `已訂這間` as the primary decision action, and keep `旅次詳情` as the secondary action.
- Keep dismissal out of the crowded `/清單` main card footer; expose `不考慮這間` from the trip detail surface and any later secondary action surface.
- Show booked lodgings distinctly and allow reverting them back to candidate.
- Hide dismissed lodgings from the default `/清單` candidate set while preserving access from trip detail filters.

## Capabilities

### New Capabilities
- `lodging-decision-status`: Tracks user decisions for lodging candidates and defines how booked, candidate, and dismissed states appear across LINE preview, trip detail, and downstream sync surfaces.

### Modified Capabilities
- None.

## Impact

- Affected code: `app/models/captured_lodging_link.py`, `app/controllers/line_webhook_controller.py`, `app/schemas/line_webhook.py`, `app/trip_display/*`, `app/notion_sync/*`, `tests/*`, `README.md`
- Data/API: Adds decision status fields to lodging Mongo documents; adds LINE postback handling for status transitions; extends trip display filtering and payloads.
- UX: `/清單` remains compact by prioritizing booking confirmation on LINE and moving dismissal/cleanup actions to the trip detail surface.
- Dependencies/systems: No new external dependency expected; Notion export should include decision status if the configured schema can be updated.
