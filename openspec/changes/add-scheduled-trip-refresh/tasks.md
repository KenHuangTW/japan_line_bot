## 1. Refresh Coordinator

- [ ] 1.1 Add a trip refresh job that enumerates active trips and coordinates per-trip refresh execution
- [ ] 1.2 Wire the coordinator to trip-scoped enrichment and Notion sync flows
- [ ] 1.3 Add tests covering active-trip-only enumeration and archived-trip skipping

## 2. Failure Isolation And Reporting

- [ ] 2.1 Add per-trip failure handling so one failed trip does not abort the whole refresh batch
- [ ] 2.2 Add tests covering mixed success/failure scheduled runs and resulting batch summaries

## 3. Operations Documentation

- [ ] 3.1 Update README and operational docs with the recommended 12-hour external refresh schedule and job usage
