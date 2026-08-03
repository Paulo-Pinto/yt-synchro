"""Regression tests for yt_synchro.cleanup."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from yt_synchro.cleanup import cleanup_by_count, cleanup_by_storage
from yt_synchro.config import Config
from yt_synchro.state import StateManager, VideoState


def make_state(tmp_path):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir(exist_ok=True)
    return StateManager(state_file=state_file, output_dir=output_dir)


def add_video(state, output_dir, video_id, size_bytes=0, age_days=0):
    path = output_dir / f"{video_id}.mp4"
    path.write_bytes(b"x" * size_bytes)
    video = VideoState.create(video_id=video_id, title=video_id, file_path=str(path))
    video.downloaded_at = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    state.add(video)


def test_cleanup_by_storage_persists_state(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)
    config = Config(max_storage_gb=0.000001, output_dir=str(output_dir))

    # 0.000001 GB is 1048 bytes; 2048 bytes deterministically exceeds the limit.
    add_video(state, output_dir, "old", size_bytes=2048, age_days=2)

    cleanup_by_storage(state, config)

    assert state.get("old").status == "removed"
    reloaded = make_state(tmp_path)
    assert reloaded.get("old").status == "removed"


def test_cleanup_by_count_persists_state(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)
    config = Config(max_videos=1, output_dir=str(output_dir))

    add_video(state, output_dir, "first", size_bytes=1, age_days=2)
    add_video(state, output_dir, "second", size_bytes=1, age_days=1)

    cleanup_by_count(state, config)

    assert state.get("first").status == "removed"
    reloaded = make_state(tmp_path)
    assert reloaded.get("first").status == "removed"


def test_cleanup_sandbox_rejects_escape(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)
    config = Config(max_videos=0, output_dir=str(output_dir))

    # File outside the output directory must never be deleted.
    outside = tmp_path / "outside.mp4"
    outside.write_text("precious")
    video = VideoState.create(video_id="evil", title="evil", file_path=str(outside))

    # Adding an escaped path is rejected outright by the sandbox.
    with pytest.raises(ValueError):
        state.add(video)

    # Even if a tampered/legacy state file slips an escaped entry in,
    # cleanup must never delete outside the output directory.
    state._videos["evil"] = video
    cleanup_by_count(state, config)

    assert outside.exists()
    outside.unlink()


def test_cleanup_by_count_deletes_under_output_dir(tmp_path):
    state = make_state(tmp_path)
    output_dir = Path(state._output_dir)
    config = Config(max_videos=0, output_dir=str(output_dir))

    add_video(state, output_dir, "to_remove", size_bytes=1)
    path = output_dir / "to_remove.mp4"
    assert path.exists()

    cleanup_by_count(state, config)

    assert not path.exists()
    assert state.get("to_remove").status == "removed"
