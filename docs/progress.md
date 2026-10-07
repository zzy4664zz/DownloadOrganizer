# Implementation ledger — download organizer

Plan: docs/superpowers/plans/2026-10-07-download-organizer.md

User approved the design and authorized continuous implementation and GitHub publication. Plan/spec reviews are performed inline under that instruction.

Pre-flight: GUI consumes Plan/Result and execute/undo from core; tests and UI use the same interfaces. Packaging calls main.py. Existing isolated checkout retained.

Task 1: complete — 18 temporary-directory tests pass on Python 3.12.14. RED: missing organizer module/API; GREEN: classification, post-preview collision, changed source, intact bytes after move/undo, malformed history, links, interrupted move and interrupted undo, partial failure, explicit acceptance of results. Fixed collision numbering to derive from the original source name rather than a previously numbered preview name.

Publication diagnosis: native Git read succeeds. GitHub API and gh auth are forbidden in this runtime even with existing injected authentication; do not infer that Git push is unavailable. Use native Git and public GitHub pages for publication verification, and report any remaining CI visibility limitation.

Task 2: complete — 24/24 full-suite tests passed with a real Xorg display; startup smoke check is next. GUI tests exercise real preview, move, restart, persistent undo, cancellation, error reporting, and conflicts. Windows launcher and release pipelines are ready for platform validation.

Diagnosis: Tcl_AsyncDelete in the first GUI suite was caused by destroyed Tk interpreters surviving in cycles until a later worker triggered GC. Test teardown now collects those cycles on the creating thread. The UI joins the completed worker before permitting close so the worker task releases GUI references first.

Final independent review: gpt-6-astra reviewed core, UI, launcher and workflow. Three P2 findings entered one fix pass.

Final: fixed stale-instance history deletion — core stale-token and GUI stale-window tests RED→GREEN. SHA-256 journal revisions plus random batch IDs guard undo/acceptance under the shared lock, including identical repeated batches.

Final: fixed Windows timestamp-preserving source changes — preview captures SHA-256, execution compares contents; equal-length changed content with restored timestamps and emulated Windows metadata RED→GREEN.

Final: fixed interrupted undo after an empty category is removed — verify source-only recovery before checking category; regression RED→GREEN.

Final: fixed default-window footer clipping — screenshot exposed unmapped log; real-widget visibility test RED→GREEN after switching to a weighted grid.

Final verification: 31/31 tests pass with Python 3.13.5 / Tk 8.6 and actual Xorg display; source smoke check passes. No deferred reviewer findings. Cloud Tk 9 lacks Xft-style CJK rendering, so visual verification uses the system Tk 8.6. Native Windows CI and exe publication remain pending until pushed tag workflow completes.

Task 3: complete — main pushed by native HTTPS Git (non-force fast-forward); annotated v1.0.0 points to 4fab131. Linux/Windows CI run 37576760036 succeeds. Windows release run 37576788256 succeeds, including real desktop tests, batch startup in CI, compiled-exe smoke check and release creation. Public Release assets verified; downloaded 11,625,434-byte x64 exe matches published SHA-256. Documentation follow-up changes only describe verified results; release functional source remains the tagged commit.
