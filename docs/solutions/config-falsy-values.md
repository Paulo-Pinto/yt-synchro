# Config Serialization Must Preserve Falsy Values

## Problem
`Config.save()` used `if value:` before writing each key. This silently dropped empty strings and zeros, so valid user settings like `max_videos = 0`, `parallel = 0`, `daemon_interval_minutes = 0`, or `playlist_url = ""` were lost on save. The `DEFAULTS` dict also duplicated the dataclass defaults, creating a maintenance hazard.

## Context
Config is a simple dataclass loaded from / saved to TOML. The hand-rolled serializer was minimal and only handled strings and booleans, which also risked producing invalid TOML as the dataclass evolved.

## Decision
Serialize every field unconditionally and derive defaults from the dataclass itself instead of maintaining a parallel dictionary.

## Solution
- Removed the `DEFAULTS` dict from `config.py`.
- Changed `Config.save()` to write every key from `asdict(self)` regardless of truthiness.
- Added `Config.validate()` to reject truly broken values (negative storage, non-positive `max_videos`/`parallel`/`daemon_interval_minutes`, invalid quality) while still allowing zero where it is meaningful.
- Called `config.validate()` after every `load_config()` so invalid CLI overrides or config files fail fast.

## Verification
- Manual QA saved a config with all-zero / empty-string values and confirmed a round-trip preserved them exactly.
- `scripts/lint.sh` passes.

## References
- `yt_synchro/config.py` (`Config.save`, `Config.validate`, `load_config`)

## Date
2026-07-15
