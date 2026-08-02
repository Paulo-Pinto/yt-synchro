# CLI Separation of Concerns

## Problem
`cli.py` was 377 lines and mixed click decorators, argument parsing, configuration overrides, download orchestration loops, daemon loop, status rendering, table printing, interactive config editor, and manual remove flow. This violated the single-responsibility principle and made the module hard to test and extend.

## Context
The review identified `cli.py` as an oversized module (>250 pure LOC) with a boundary violation: it knew about CLI, orchestration, and UI all at once.

## Decision
Split the module by concern:
- `cli.py` defines click commands and dispatches to other modules.
- `runner.py` owns the `run()` and `daemon()` orchestration loops.
- `display.py` owns terminal UI helpers (panels, tables, prompts).

## Solution
- Extracted `run_sync()` and `run_daemon()` into `runner.py`.
- Extracted `print_status()`, `print_video_table()`, `prompt_for_config()`, and related helpers into `display.py`.
- Updated `cli.py` to import and call these helpers, keeping command definitions thin.
- Updated `AGENTS.md` to document the new module layout and the renamed `config-show` / `config-edit` commands.

## Verification
- `yt-synchro --help` shows all commands.
- `yt-synchro run --help`, `yt-synchro daemon --help`, `yt-synchro config-show`, `yt-synchro config-edit --help`, `yt-synchro list`, and `yt-synchro remove --help` all work.
- `scripts/lint.sh` passes.

## References
- `yt_synchro/cli.py`
- `yt_synchro/runner.py`
- `yt_synchro/display.py`
- `AGENTS.md`

## Date
2026-07-15
