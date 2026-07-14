"""Cleanup module for yt-synchro - manages old video deletion."""

import logging
from pathlib import Path
from typing import Optional

from .state import StateManager
from .config import Config

logger = logging.getLogger(__name__)


def cleanup_old_videos(state: StateManager, config: Config) -> list[dict]:
    removed = state.cleanup_old(config.video_max_age_days)
    results = []
    for video in removed:
        results.append({
            "video_id": video.video_id,
            "title": video.title,
            "status": "removed",
        })
        logger.info(f"Removed old video: {video.title} ({video.video_id})")
    return results


def cleanup_by_storage(state: StateManager, config: Config) -> list[dict]:
    removed = []
    while state.get_total_size() > config.max_storage_gb * 1024 * 1024 * 1024:
        oldest = state.get_oldest()
        if not oldest:
            break
        path = Path(oldest.file_path)
        if path.exists():
            path.unlink()
        oldest.status = "removed"
        removed.append({
            "video_id": oldest.video_id,
            "title": oldest.title,
            "status": "removed",
        })
        logger.info(f"Removed video for storage: {oldest.title} ({oldest.video_id})")
    return removed


def cleanup_by_count(state: StateManager, config: Config) -> list[dict]:
    removed = []
    while state.get_count() > config.max_videos:
        oldest = state.get_oldest()
        if not oldest:
            break
        path = Path(oldest.file_path)
        if path.exists():
            path.unlink()
        oldest.status = "removed"
        removed.append({
            "video_id": oldest.video_id,
            "title": oldest.title,
            "status": "removed",
        })
        logger.info(f"Removed video for count: {oldest.title} ({oldest.video_id})")
    return removed
