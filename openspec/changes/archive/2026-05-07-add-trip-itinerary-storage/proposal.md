## Why

Users want to paste or quote a full trip plan in LINE and have the bot turn it into structured itinerary data without manually entering each event. The project already has Mongo-backed trip context and Gemini structured output, so the next step is to make itinerary storage the source of truth before adding external calendar or map exports.

## What Changes

- Add Mongo-backed itinerary source, draft, and confirmed item persistence scoped to the active `LineTrip`.
- Add `/整理行程` to import a full itinerary from command text or from a quoted LINE message.
- Add LINE message snapshot persistence so quoted-message imports can resolve the original text by `quotedMessageId`.
- Add an AI-assisted normalization flow that turns raw itinerary text into a pending draft with add/update/delete diff information.
- Add confirmation commands to apply or discard the latest pending itinerary draft.
- Add `/行程` to read confirmed itinerary items from Mongo and return a trip-scoped itinerary summary.
- Keep Google Calendar, Google Maps export, OAuth, and external sync out of this change.

## Capabilities

### New Capabilities
- `trip-itinerary-storage`: Stores imported itinerary sources, AI-generated drafts, confirmed itinerary items, and trip-scoped itinerary command behavior.
- `line-message-snapshots`: Stores inbound LINE text message snapshots so commands can use quoted message ids as itinerary import input.

### Modified Capabilities
- None.

## Impact

- Affected code: `app/schemas/line_webhook.py`, `app/controllers/line_webhook_controller.py`, `app/main.py`, new itinerary models/services/repositories/schemas/rendering modules, tests, and README.
- Affected data: new Mongo collections for LINE message snapshots, itinerary sources, itinerary drafts, and itinerary items.
- Affected AI integration: add a Gemini structured-output client/service for itinerary draft generation while reusing the current provider configuration pattern.
- External systems: no Google Calendar or Google Maps API integration in this change.
