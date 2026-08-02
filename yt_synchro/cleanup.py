"""Cleanup module for yt-synchro - manages old video deletion."""

import logging

from .config import Config
from .state import StateManager

logger = logging.getLogger(__name__)


def _make_result(video) -> dict:
    return {
        "video_id": video.video_id,
        "title": video.title,
        "status": "removed",
    }


def cleanup_old_videos(state: StateManager, config: Config) -> list[dict]:
    removed = state.cleanup_old(config.video_max_age_days)
    results = []
    for video in removed:
        results.append(_make_result(video))
        logger.info(f"Removed old video: {video.title} ({video.video_id})")
    return results


def cleanup_by_storage(state: StateManager, config: Config) -> list[dict]:
    limit_bytes = config.max_storage_gb * 1024 * 1024 * 1024
    removed = []
    while state.get_total_size() > limit_bytes:
        oldest = state.get_oldest()
        if not oldest:
            break
        if state.remove_video(oldest):
            removed.append(_make_result(oldest))
            logger.info(f"Removed video for storage: {oldest.title} ({oldest.video_id})")
    return removed


def cleanup_by_count(state: StateManager, config: Config) -> list[dict]:
    removed = []
    while state.get_count() > config.max_videos:
        oldest = state.get_oldest()
        if not oldest:
            break
        if state.remove_video(oldest):
            removed.append(_make_result(oldest))
            logger.info(f"Removed video for count: {oldest.title} ({oldest.video_id})")
    return removed
