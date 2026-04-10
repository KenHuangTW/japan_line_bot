## 1. AI Summary Foundation

- [ ] 1.1 Add Gemini summary configuration, client abstraction, and request/response schemas for structured output validation
- [ ] 1.2 Implement a decision summary service that builds normalized lodging payloads from the active trip data
- [ ] 1.3 Add unit tests for schema validation, payload construction, and provider failure handling

## 2. LINE Summary Flow

- [ ] 2.1 Implement the LINE summary command and active-trip resolution flow for summary requests
- [ ] 2.2 Add safe fallback behavior for missing active trips, empty trips, timeouts, and invalid AI output
- [ ] 2.3 Add controller tests covering successful summaries and all failure cases

## 3. Documentation

- [ ] 3.1 Update README and operational docs for Gemini setup and summary command usage
