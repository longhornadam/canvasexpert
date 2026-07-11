# Toyota handoff 12b4: persona, pattern, and folder UX

Migrate only accepted 12b0 persona/pattern selection and folder-opening/management rows
into the PowerGrader Workbench. Preserve existing settings, safe path checks, workspace
folder names, and APIs. This is UI orchestration, not a scoring or storage rewrite. Test
path rejection, missing folder, selection persistence, keyboard/focus, both themes, and
legacy parity with zero external calls. One commit; stop if Name Manager/privacy admin
would be pulled into grading.
