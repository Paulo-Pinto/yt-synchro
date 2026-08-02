"""Regression tests for yt_synchro.config."""

import pytest

from yt_synchro.config import Config, ensure_config, load_config


def test_save_preserves_falsy_values(tmp_path):
    config = Config(
        playlist_url="",
        output_dir=str(tmp_path / "out"),
        max_storage_gb=0.0,
        max_videos=0,
        parallel=0,
        quality="",
        daemon_interval_minutes=0,
        video_max_age_days=0,
    )
    path = tmp_path / "config.toml"
    config.save(path)

    loaded = Config.from_toml(path)
    assert loaded.playlist_url == ""
    assert loaded.max_storage_gb == 0.0
    assert loaded.max_videos == 0
    assert loaded.parallel == 0
    assert loaded.quality == ""
    assert loaded.daemon_interval_minutes == 0
    assert loaded.video_max_age_days == 0


def test_validate_rejects_invalid_values():
    config = Config()

    with pytest.raises(ValueError):
        config.max_storage_gb = -1.0
        config.validate()

    config = Config()
    with pytest.raises(ValueError):
        config.max_videos = 0
        config.validate()

    config = Config()
    with pytest.raises(ValueError):
        config.parallel = 0
        config.validate()

    config = Config()
    with pytest.raises(ValueError):
        config.daemon_interval_minutes = 0
        config.validate()


def test_validate_accepts_positive_values():
    config = Config()
    config.validate()  # defaults are valid


def test_load_config_validates_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr("yt_synchro.config.CONFIG_FILE", tmp_path / "missing.toml")
    with pytest.raises(ValueError):
        load_config(overrides={"parallel": 0})


def test_ensure_config_creates_valid_file(monkeypatch, tmp_path):
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("yt_synchro.config.CONFIG_FILE", config_file)
    config = ensure_config()
    assert config_file.exists()
    loaded = Config.from_toml(config_file)
    assert loaded.parallel == config.parallel
