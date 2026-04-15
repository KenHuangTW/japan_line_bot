## 1. Control Mapping Foundation

- [x] 1.1 Add optional settings fields for the control-group and target-group env values, plus a helper that determines whether a LINE command should resolve against an overridden group scope
- [x] 1.2 Update the scope-sensitive command path in `app/controllers/line_webhook_controller.py` so trip-management and trip-scoped commands resolve chat scope through the new helper instead of always using the raw event source
- [x] 1.3 Generalize the helper so ordinary lodging capture can also resolve a target data scope without changing where LINE replies are sent

## 2. Capture And Sync Routing

- [x] 2.1 Update the capture path so active-trip resolution, duplicate lookup, persisted `source_type/group_id/room_id/user_id`, and downstream auto sync all use the target group when the message comes from the control group
- [x] 2.2 Keep duplicate and capture replies attached to the original control-group event so users still see the response in A while data is recorded under B
- [x] 2.3 Ensure fallback behavior stays source-based when env configuration is partial, unmatched, or the event source is not a group

## 3. Regression Tests

- [x] 3.1 Add webhook tests covering `/建立旅次` and `/目前旅次` from the control group, verifying the target group's trip state is created or read
- [x] 3.2 Add webhook tests covering `/清單`、`/整理`、`/全部重來` from the control group, verifying the target group's active trip and repositories are used
- [x] 3.3 Add webhook tests proving a supported lodging URL posted in the control group writes into the target group's active trip while replying in the control group
- [x] 3.4 Add webhook tests proving duplicate lookup and automatic sync for control-group lodging capture both use the target group's scope
- [x] 3.5 Add webhook tests proving capture rejects when the target group lacks an active trip even if the control group has one

## 4. Docs

- [x] 4.1 Update `README.md` and `.env.example` to document the new control-group env settings, the intended A -> B workflow for both commands and lodging capture, and the rule that replies stay in A while records are stored under B
