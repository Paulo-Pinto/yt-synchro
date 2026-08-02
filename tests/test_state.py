"""Regression tests for yt_synchro.state."""

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from yt_synchro.state import StateManager, VideoState


def test_path_sandbox_rejects_escape(tmp_path):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    state = StateManager(state_file=state_file, output_dir=output_dir)

    bad = VideoState.create(
        video_id="abc123def45",
        title="escape",
        file_path=str(tmp_path / "evil.txt"),
    )
    with pytest.raises(ValueError):
        state.add(bad)


def test_atomic_save_keeps_previous_state_on_failure(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    state = StateManager(state_file=state_file, output_dir=output_dir)
    state.add(
        VideoState.create(video_id="vid1", title="one", file_path=str(output_dir / "1.mp4"))
    )

    original_dump = json.dump

    def exploding_dump(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", exploding_dump)

    with pytest.raises(OSError):
        state.add(
            VideoState.create(video_id="vid2", title="two", file_path=str(output_dir / "2.mp4"))
        )

    # Previous state must still be readable.
    monkeypatch.setattr(json, "dump", original_dump)
    reloaded = StateManager(state_file=state_file, output_dir=output_dir)
    assert reloaded.get("vid1") is not None
    assert reloaded.get("vid2") is None


def test_thread_safe_concurrent_adds(tmp_path):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    state = StateManager(state_file=state_file, output_dir=output_dir)

    def add_video(index: int):
        state.add(
            VideoState.create(
                video_id=f"vid{index:04d}",
                title=f"video {index}",
                file_path=str(output_dir / f"{index}.mp4"),
            )
        )

    threads = [threading.Thread(target=add_video, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    reloaded = StateManager(state_file=state_file, output_dir=output_dir)
    assert len(reloaded.get_all()) == 50


def test_get_oldest_orders_by_datetime(tmp_path):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    state = StateManager(state_file=state_file, output_dir=output_dir)

    now = datetime.now(timezone.utc)
    old = VideoState.create(video_id="old", title="old", file_path=str(output_dir / "old.mp4"))
    old.downloaded_at = (now - timedelta(days=2)).isoformat()
    new = VideoState.create(video_id="new", title="new", file_path=str(output_dir / "new.mp4"))
    new.downloaded_at = (now - timedelta(days=1)).isoformat()

    state.add(new)
    state.add(old)

    assert state.get_oldest().video_id == "old"


def test_load_skips_invalid_datetime(tmp_path):
    state_file = tmp_path / "state.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    state_file.write_text(
        json.dumps(
            {
                "videos": [
                    {
                        "video_id": "bad",
                        "title": "bad",
                        "file_path": str(output_dir / "bad.mp4"),
                        "downloaded_at": "not-a-date",
                        "status": "downloaded",
                    },
                    {
                        "video_id": "good",
                        "title": "good",
                        "file_path": str(output_dir / "good.mp4"),
                        "downloaded_at": datetime.now(timezone.utc).isoformat(),
                        "status": "downloaded",
                    },
                ]
            }
        )
    )

    state = StateManager(state_file=state_file, output_dir=output_dir)
    assert state.get("good") is not None
    # Invalid entry should be dropped or repaired, never crash.
    assert state.get("bad") is None or state.get("bad").downloaded_at != "not-a-date"
