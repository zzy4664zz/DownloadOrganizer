# Implementation ledger — download organizer

Plan: docs/superpowers/plans/2026-10-07-download-organizer.md

User approved the design and authorized continuous implementation and GitHub publication. Plan/spec reviews are performed inline under that instruction.

Pre-flight: GUI consumes Plan/Result and execute/undo from core; tests and UI use the same interfaces. Packaging calls main.py. Existing isolated checkout retained.

Task 1: complete — 18 temporary-directory tests pass on Python 3.12.14. RED: missing organizer module/API; GREEN: classification, post-preview collision, changed source, intact bytes after move/undo, malformed history, links, interrupted move and interrupted undo, partial failure, explicit acceptance of results. Fixed collision numbering to derive from the original source name rather than a previously numbered preview name.

Publication diagnosis: native Git read succeeds. GitHub API and gh auth are forbidden in this runtime even with existing injected authentication; do not infer that Git push is unavailable. Use native Git and public GitHub pages for publication verification, and report any remaining CI visibility limitation.

Task 2: complete — 24/24 full-suite tests passed with a real Xorg display; startup smoke check is next. GUI tests exercise real preview, move, restart, persistent undo, cancellation, error reporting, and conflicts. Windows launcher and release pipelines are ready for platform validation.

Diagnosis: Tcl_AsyncDelete in the first GUI suite was caused by destroyed Tk interpreters surviving in cycles until a later worker triggered GC. Test teardown now collects those cycles on the creating thread. The UI joins the completed worker before permitting close so the worker task releases GUI references first.
