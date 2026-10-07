# Download Organizer Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline. The user requests continuous execution and GitHub publication.

**Goal:** Deliver a Chinese Windows folder organizer with preview and persistent safe undo.

**Architecture:** A standard-library file engine owns planning and journaled moves. Tkinter presents the workflow and executes I/O in a background thread. A Windows release pipeline packages the app.

**Tech Stack:** Python 3.12+, tkinter, unittest, GitHub Actions, PyInstaller 6.16.0 for packaging only.

**Spec:** `docs/superpowers/specs/2026-10-07-download-organizer-design.md`

## Global Constraints

- Do not overwrite existing files or organize nested directories.
- Skip links/reparse points, hidden files and unfinished downloads.
- Persist recoverable move records before moving files; verify SHA-256 before undo.
- Keep runtime dependency-free and use Chinese user-facing text.
- Use the existing isolated cloud checkout; do not create another worktree.
- Publish only after checks pass; do not claim Windows validation before Windows CI completes.

## Review Focus

- A destination is occupied after preview: allocate a fresh name and preserve both files.
- A previewed source changes: skip it and report an error.
- App termination between a move and its journal update: recover pending records.
- A user creates a new file at the original path: undo reports a conflict without overwriting.
- Two instances or malformed history: refuse unsafe writes and report actionable errors.

## Task 1: File engine

**Files:** `organizer/core.py`, `tests/test_core.py`, `organizer/__init__.py`.

**Interfaces:** `preview(folder: Path) -> Plan`, `execute(plan: Plan, history: Path, progress=None) -> Result`, `undo(history: Path, progress=None) -> Result`, `has_history(history: Path) -> bool`.

- [ ] Write real temporary-directory tests for preview, classification, collisions, changed sources, persistent undo, conflicts, crash recovery, links, damaged journals, and locking.
- [ ] Run `python3 -m unittest discover -s tests -v`; observe missing implementation failures.
- [ ] Implement the engine and durable journal with no-overwrite moves.
- [ ] Run the full suite; verify exact bytes and paths, not mocked calls.
- [ ] Commit the tested engine and update the ledger.

## Task 2: Desktop app and Windows startup

**Files:** `organizer/app.py`, `main.py`, `启动整理助手.bat`, `tests/test_app.py`, `README.md`, `.gitignore`.

**Interfaces:** consumes the Task 1 engine; produces `OrganizerApp(root, initial_folder=None, history_dir=None)` and `main()`.

- [ ] Write GUI integration tests for preview, organize, restart and undo with a temporary folder and a real Tk root.
- [ ] Run those tests under a display; observe the missing app failure.
- [ ] Implement Chinese UI, worker progress/errors, default download folder and launch script.
- [ ] Run core and GUI tests with a virtual display; document native Windows execution requirements.
- [ ] Commit the tested app and update the ledger.

## Task 3: Verification and publication

**Files:** `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `docs/TESTING.md`.

- [ ] Add Linux and Windows tests plus Windows exe packaging on version tags.
- [ ] Verify the startup command, smoke test and full test suite; review safety and usability.
- [ ] Commit, push the branch to GitHub main through a non-force fast-forward, then push v1.0.0.
- [ ] Inspect remote refs and, when API access permits, Windows CI and release assets.
- [ ] Report precisely what is published and any unverified platform-specific behavior.
