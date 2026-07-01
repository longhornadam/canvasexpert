# PowerGrader Scheduled Auto-Push State Model

## Background

Canvas Expert already has scheduled PowerGrader autoscore work that creates draft
sessions only. The next implementation slices are allowed to add a teacher-controlled
auto-push path for assignments that are intentionally set up for that workflow.

This handoff defines the queue and state model only. It does not implement Canvas
pushes yet.

## Goal

Define a queue/job model that can support scheduled PowerGrader runs which:

- create scored drafts first,
- decide per student whether a Canvas grade/comment push is allowed,
- push only when the teacher explicitly opted into auto-push for that specific job
  or assignment,
- preserve an audit trail in the PRIVATE workspace,
- stay safe across multiple machines sharing the same synced workspace.

## Non-Goals

- No global auto-push setting.
- No default auto-push behavior.
- No New Quizzes support in this slice.
- No public or cloud scheduler.
- No automatic overwrite of teacher work beyond the explicit, reviewed push policy.
- No edits to `LLM_Modules/*_Base.md`.

## Product Rule

Scheduled auto-push is permitted only when all of these are true:

1. The teacher explicitly opted in for that specific scheduled PowerGrader job or
   assignment.
2. The job is treated as assignment-specific, not global or tenant-wide.
3. Policy checks, idempotency checks, and audit receipt capture have passed.
4. Only eligible students can be auto-pushed.
5. Any uncertain, blocked, unsupported, or policy-failing case is routed to review.

If any condition fails, behavior stays draft-only.

## Queue File Shape

Primary source of truth:

- `<workspace>/PowerGrader/autoscore_queue.json`

Suggested top-level shape:

```json
{
  "version": 2,
  "machine_last_writer": "machine-a",
  "updated_at": "2026-07-01T12:00:00-05:00",
  "jobs": []
}
```

The queue file should remain sync-friendly and append/update oriented. It should not
contain secrets, raw student content, or Canvas tokens. Preserve the existing
`version` field used by `api/powergrader/autoscore_queue.py`; do not introduce a
parallel top-level schema field unless a migration helper is added.

## Job Schema Additions

Each job should keep the existing assignment and session references, then add a
teacher opt-in block and push-state fields.

Suggested fields:

```json
{
  "job_id": "pg_auto_20260701_001",
  "course_id": "123",
  "assignment_id": "456",
  "mode": "auto_score",
  "status": "scheduled",
  "scheduled_at": "2026-07-01T17:00:00-05:00",
  "created_at": "2026-07-01T10:00:00-05:00",
  "updated_at": "2026-07-01T10:00:00-05:00",
  "claimed_by": null,
  "claimed_at": null,
  "lease_until": null,
  "machine_id": null,
  "auto_push": true,
  "push_policy": {
    "enabled": true,
    "require_teacher_opt_in": true,
    "allow_grade_push": true,
    "allow_comment_push": true,
    "require_policy_clear": true,
    "require_idempotency_match": true,
    "require_review_for_blocked": true
  },
  "scoring": {
    "status": "pending"
  },
  "push": {
    "status": "pending",
    "attempts": 0,
    "last_attempt_at": null
  },
  "students": [],
  "audit": {
    "private_dir": "PowerGrader/private/autoscore_receipts",
    "receipt_ids": []
  }
}
```

Field intent:

- `auto_push`: explicit per-job opt-in, never implied by schedule creation.
- `push_policy`: durable policy snapshot for this job; later slices can decide whether
  to read assignment defaults and clone them here.
- `claimed_by`, `claimed_at`, `lease_until`, `machine_id`: multi-machine coordination.
- `audit`: references for PRIVATE-only receipts and push records.

## Suggested Status Vocabulary

Queue/job statuses should support both scoring and push phases:

- `scheduled`
- `running`
- `session_ready`
- `push_ready`
- `auto_pushing`
- `auto_pushed`
- `partial_auto_pushed`
- `needs_review`
- `failed`
- `cancelled`

Suggested state meaning:

- `scheduled`: queued but not yet claimed.
- `running`: claimed and actively building or refreshing the scoring session.
- `session_ready`: scoring artifacts exist and are ready for policy evaluation.
- `push_ready`: scoring is done, but push policy has not yet been executed.
- `auto_pushing`: Canvas push is in progress.
- `auto_pushed`: all eligible student updates were pushed and receipts recorded.
- `partial_auto_pushed`: some students pushed, some routed to review.
- `needs_review`: push was blocked for at least one student or the job policy failed.
- `failed`: unrecoverable operational failure.
- `cancelled`: teacher cancelled the job.

## Per-Student Decision Model

Each job should store a per-student decision object, even if the job never reaches the
push phase.

Suggested fields for each student row:

```json
{
  "student_key": "canvas-user-123",
  "submission_id": "999",
  "scoring_status": "complete",
  "decision": "auto_push_allowed",
  "decision_reason": "policy_clear",
  "review_needed_reason": null,
  "idempotency_key": "pg:456:999:rubric-v3:hash123",
  "canvas_target": {
    "grade_present": true,
    "comment_present": true
  },
  "receipt": {
    "receipt_id": "rcpt_001",
    "pushed_at": "2026-07-01T17:15:00-05:00",
    "canvas_grade_hash": "sha256:...",
    "canvas_comment_hash": "sha256:..."
  }
}
```

Decision vocabulary:

- `auto_push_allowed`
- `needs_review`
- `blocked`

Decision guidance:

- `auto_push_allowed`: policy checks passed and the student is eligible.
- `needs_review`: the student is eligible only after teacher review, or the case is
  ambiguous.
- `blocked`: the student must not be auto-pushed.

`student_key` can be a Canvas user/submission identifier already present in the
PRIVATE PowerGrader session. Do not store student names, raw submission text, or SAFE
packet pseudonyms in the queue unless a later slice proves the queue needs them.

`review_needed_reason` should be a short UI-safe string such as:

- `policy_not_cleared`
- `no_submission_text`
- `unsupported_submission_type`
- `existing_teacher_override`
- `idempotency_mismatch`
- `assignment_refetch_changed`
- `canvas_write_conflict`

## Idempotency And Receipt Requirements

Later slices should treat idempotency as mandatory for any Canvas write.

Suggested markers:

- job-level push batch key
- per-student idempotency key
- Canvas comment/grade fingerprint
- receipt record with timestamp, target identifiers, and the exact policy version used

The implementation should be able to tell whether a target student was already pushed,
and should not duplicate a write when a lease is retried, a machine restarts, or a
synced file arrives late.

## Multi-Machine Workflow Assumptions

The synced workspace is the source of truth for queue state. Canvas credentials remain
machine-local. OneDrive sync is eventually consistent, so queue coordination must not
depend on instant file propagation.

That means:

- leases are useful for reducing duplicate work,
- leases are not sufficient by themselves,
- every push must still refetch Canvas state and verify idempotency before writing,
- if the lease expires or the queue file changes unexpectedly, the worker should
  re-evaluate before continuing,
- a machine-local failure must not leave the job in a state that forces manual repo
  repair.

Recommended claim fields:

- `claimed_by`: human-readable worker label or service label
- `claimed_at`: ISO timestamp
- `lease_until`: ISO timestamp
- `machine_id`: stable local machine identifier

## Policy Evaluator Inputs And Outputs

Later slices should centralize push eligibility in a policy evaluator instead of
scattering checks across route code.

Suggested inputs:

- job metadata
- assignment metadata after a fresh Canvas refetch
- scoring output for the student
- student submission/push state
- existing Canvas grade/comment fingerprints
- job opt-in and policy snapshot
- lease and idempotency state

Suggested outputs per student:

```json
{
  "decision": "auto_push_allowed",
  "review_needed_reason": null,
  "blocked_reason": null,
  "policy_checks": {
    "teacher_opt_in": true,
    "submission_supported": true,
    "assignment_unchanged": true,
    "idempotency_clear": true
  }
}
```

The evaluator should return exactly one of:

- `auto_push_allowed`
- `needs_review`
- `blocked`

## Audit Metadata

Audit details belong in the PRIVATE workspace only, not in the repo and not in any
shared/public location.

Suggested audit contents:

- job start/stop timestamps
- claim and lease history
- policy snapshot used for the decision
- student decision list
- Canvas target identifiers
- write attempt metadata
- receipt ids
- failure and review reasons

Suggested storage pattern:

- queue JSON keeps summary state
- PRIVATE receipt files keep detailed records
- no audit record should require student names or raw submission content in the repo

## Acceptance Criteria For Later Slices

1. A queued job can express explicit per-job auto-push opt-in.
2. Auto-push is off by default for newly created jobs.
3. A job can move through scoring and push phases without duplicating work after a
   retry or a second machine sees the same queue file.
4. Eligible students can be auto-pushed only after policy evaluation passes.
5. Blocked and uncertain students are routed to review with reasons.
6. Receipt metadata is written to the PRIVATE workspace only.
7. The system can report whether a job is `auto_pushed`, `partial_auto_pushed`, or
   `needs_review`.

## Tests For Later Slices

Proposed tests should use fake IDs and monkeypatched Canvas calls only.

- queue schema round-trip preserves `auto_push`, `push_policy`, claim fields, student
  decisions, and receipt references
- policy evaluator returns `auto_push_allowed`, `needs_review`, and `blocked` for
  representative inputs
- claim/lease logic prevents two workers from pushing the same job at the same time
- idempotency logic prevents duplicate Canvas writes when a lease is retried
- audit receipt writing stays inside the PRIVATE workspace path
- default queue creation keeps auto-push disabled unless a teacher opts in explicitly
- unsupported or uncertain student cases are routed to review instead of push

## Implementation Boundaries

- Keep this work local-only.
- Keep it FERPA-safe.
- Do not touch `LLM_Modules/*_Base.md`.
- Do not add a global auto-push switch.
- Do not make scheduled auto-push the default path.
- Draft-only behavior remains the baseline unless the teacher explicitly opts in for
  the specific job and the policy evaluator clears the students being pushed.
