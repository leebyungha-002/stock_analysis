"""영상 자막(트랜스크립트) 추출: youtube-transcript-api 우선, faster-whisper로 폴백합니다."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

logger = logging.getLogger(__name__)

PREFERRED_LANGUAGES = ["ko", "en"]


def get_transcript_via_api(video_id: str) -> str | None:
    """youtube-transcript-api로 자막을 가져옵니다 (한국어 우선, 없으면 영어)."""
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = transcript_list.find_transcript(PREFERRED_LANGUAGES)
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(PREFERRED_LANGUAGES)
        entries = transcript.fetch()
        return " ".join(entry.text for entry in entries if entry.text.strip())
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as exc:
        logger.info("자막 API 사용 불가 (video_id=%s): %s", video_id, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("자막 API 조회 중 오류 (video_id=%s): %s", video_id, exc)
        return None


def _download_audio(video_id: str, dest_dir: Path) -> Path | None:
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = str(dest_dir / f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:  # noqa: BLE001
        logger.error("오디오 다운로드 실패 (video_id=%s): %s", video_id, exc)
        return None

    audio_path = dest_dir / f"{video_id}.mp3"
    return audio_path if audio_path.exists() else None


def get_transcript_via_whisper(video_id: str, model_size: str = "medium") -> str | None:
    """자막이 없을 때 yt-dlp로 오디오를 받아 faster-whisper로 전사합니다."""
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = _download_audio(video_id, Path(tmp_dir))
        if audio_path is None:
            return None

        try:
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments, _info = model.transcribe(str(audio_path), beam_size=5)
            text = " ".join(segment.text.strip() for segment in segments)
            return text if text.strip() else None
        except Exception as exc:  # noqa: BLE001
            logger.error("faster-whisper 전사 실패 (video_id=%s): %s", video_id, exc)
            return None


def get_transcript(video_id: str, whisper_model_size: str = "medium") -> str | None:
    """자막을 우선 시도하고, 실패 시 faster-whisper로 폴백합니다."""
    text = get_transcript_via_api(video_id)
    if text:
        return text

    logger.info("자막 없음 → faster-whisper 폴백 시도 (video_id=%s)", video_id)
    return get_transcript_via_whisper(video_id, model_size=whisper_model_size)
