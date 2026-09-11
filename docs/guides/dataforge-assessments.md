# DataForge assessments workflow

DataForge turns offline assessment history into a teacher-reviewed grouping
proposal.

1. Open **Assessments** and import a supported assessment export. The app keeps
   source history in the local DataForge workspace and shows standards coverage.
2. Use `get_standards_profile()` when an MCP assistant needs the published
   standards profile. It is pseudonymized, not anonymous; the private Identity
   Vault never travels with it.
3. Open **Students** and preview the proposal. The preview must cover the current
   roster exactly, include **No Data**, and produce **Support**, **Core**,
   **Accelerate**, and **Extend**; tiers with no students remain in the preview with
   count 0 so the four-tier shape is stable.
4. Review the counts and membership, then use the existing bulk group-apply
   action. CanvasExpert does not apply groups automatically.

The workflow is local and review-first. A real active course is not needed to
inspect imported history or verify the profile and preview path; a course is
needed only when the teacher chooses to apply a reviewed group change.
