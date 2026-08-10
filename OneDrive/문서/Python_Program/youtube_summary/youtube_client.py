"""YouTube Data API v3 클라이언트: 채널별 최근 N일 업로드 영상 중 조회수 상위 영상을 조회합니다."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


def build_youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _get_uploads_playlist_id(youtube, channel_id: str) -> str | None:
    response = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    items = response.get("items", [])
    if not items:
        logger.warning("채널을 찾을 수 없습니다: %s", channel_id)
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _get_recent_video_ids(youtube, playlist_id: str, since: dt.datetime) -> list[str]:
    video_ids: list[str] = []
    page_token = None

    while True:
        response = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute()
        )

        stop = False
        for item in response.get("items", []):
            published_at = dt.datetime.strptime(
                item["contentDetails"]["videoPublishedAt"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=dt.timezone.utc)
            if published_at < since:
                stop = True
                break
            video_ids.append(item["contentDetails"]["videoId"])

        page_token = response.get("nextPageToken")
        if stop or not page_token:
            break

    return video_ids


def _get_video_details(youtube, video_ids: list[str]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        response = (
            youtube.videos().list(part="snippet,statistics", id=",".join(batch)).execute()
        )
        for item in response.get("items", []):
            videos.append(
                {
                    "video_id": item["id"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                    "view_count": int(item["statistics"].get("viewCount", 0)),
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                }
            )
    return videos


def get_top_videos(youtube, channel_id: str, days: int = 7, top_n: int = 3) -> list[dict[str, Any]]:
    """지정한 채널의 최근 N일 업로드 영상 중 조회수 상위 top_n개를 반환합니다."""
    try:
        playlist_id = _get_uploads_playlist_id(youtube, channel_id)
        if not playlist_id:
            return []

        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        video_ids = _get_recent_video_ids(youtube, playlist_id, since)
        if not video_ids:
            return []

        videos = _get_video_details(youtube, video_ids)
        videos.sort(key=lambda v: v["view_count"], reverse=True)
        return videos[:top_n]
    except HttpError as exc:
        logger.error("YouTube API 오류 (channel_id=%s): %s", channel_id, exc)
        raise
