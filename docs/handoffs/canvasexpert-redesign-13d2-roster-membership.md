# Toyota handoff 13d2: Canvas group membership operation

Add `roster.membership` only after 13d1. Prepare explicit course/group/student targets in
PRIVATE storage, reload current memberships, and review aggregate counts. Already-present
add and already-absent remove are idempotent skips. Shared/current-state drift blocks the
target; partial retry includes unresolved users only. No identity appears in list/log/test
evidence. Test add/remove, duplicate, drift, deleted group, partial, ambiguous response,
retry, and bulk scope. One commit; stop if membership target identity would enter registry.
