# C2-M3 open questions

1. **Company roles of OSP A in `stub-companies.json`.** README 14.3 lists `ONBOARDING_SERVICE_PROVIDER` and `ACTIVE_PARTICIPANT`; FRAMEWORK 7a and `testdata/osp-a-company.json` also list `APP_PROVIDER` and `SERVICE_PROVIDER`. Implemented: the four roles of FRAMEWORK 7a (AGENTS rule 7).
2. **README 7.9, filter `companyId`.** It does not say whether co-viewed accounts match. Implemented: only accounts owned by the company.
3. **README 7.4, `roles` of a subscription account.** 6.5 says the assignable-roles check does not apply to subscription accounts, 7.4 says "check as in 7.2 step 3". Implemented: subscription accounts are only checked for existing roles; own accounts also for assignability.
4. **README 11.3, `PROCESS_STUB`.** `services/process_stub.py` implements it, but it only runs once `router.py` subscribes `handle_event` through `on_event`; the router is not changed in this branch.
