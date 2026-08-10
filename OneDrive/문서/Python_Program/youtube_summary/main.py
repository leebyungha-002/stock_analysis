"""유튜브 채널 주간 Top3 요약 앱 - CLI 진입점."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
CHANNELS_FILE = BASE_DIR / "channels.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "youtube_summary.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


def load_channels() -> list[dict[str, str]]:
    if not CHANNELS_FILE.exists():
        logger.error("channels.json 파일이 없습니다: %s", CHANNELS_FILE)
        raise FileNotFoundError(CHANNELS_FILE)

    data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    channels = data.get("channels", [])
    if not channels:
        logger.error("channels.json에 등록된 채널이 없습니다.")
        raise ValueError("등록된 채널이 없습니다. channels.json을 확인하세요.")
    return channels


def run(days: int, top_n: int, whisper_model_size: str) -> Path:
    from report import generate_report
    from summarizer import summarize_transcript
    from telegram_notifier import send_document
    from transcript import get_transcript
    from youtube_client import build_youtube_client, get_top_videos

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY가 설정되지 않았습니다 (.env 확인).")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인).")

    channels = load_channels()
    youtube = build_youtube_client(youtube_api_key)

    results = []
    for channel in channels:
        channel_name = channel["name"]
        channel_id = channel["channel_id"]
        logger.info("채널 처리 시작: %s (%s)", channel_name, channel_id)

        try:
            top_videos = get_top_videos(youtube, channel_id, days=days, top_n=top_n)
        except Exception:
            logger.exception("채널의 영상 목록 조회 실패: %s", channel_name)
            results.append({"channel_name": channel_name, "videos": [], "fetch_failed": True})
            continue

        video_summaries = []
        for video in top_videos:
            logger.info("영상 처리 중: %s (%s)", video["title"], video["video_id"])
            try:
                transcript_text = get_transcript(video["video_id"], whisper_model_size)
                summary = summarize_transcript(transcript_text or "", video["title"])
            except Exception:
                logger.exception("영상 요약 실패: %s", video["title"])
                summary = "(요약 생성 중 오류가 발생했습니다.)"

            video_summaries.append({**video, "summary": summary})

        results.append({"channel_name": channel_name, "videos": video_summaries})

    report_path = generate_report(results)
    logger.info("리포트 생성 완료: %s", report_path)

    caption = f"📺 주간 유튜브 채널 Top3 요약 ({dt.date.today().isoformat()})"
    if send_document(report_path.read_text(encoding="utf-8"), filename=report_path.name, caption=caption):
        logger.info("텔레그램 전송 완료")
    else:
        logger.warning("텔레그램 전송 실패")

    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="유튜브 채널 주간 Top3 요약 리포트 생성")
    parser.add_argument("--days", type=int, default=7, help="최근 며칠간의 영상을 대상으로 할지 (기본값: 7)")
    parser.add_argument("--top-n", type=int, default=3, help="채널별 상위 영상 개수 (기본값: 3)")
    parser.add_argument(
        "--whisper-model",
        type=str,
        default="medium",
        help="faster-whisper 모델 크기 (tiny/base/small/medium/large-v3, 기본값: medium)",
    )
    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")

    try:
        report_path = run(args.days, args.top_n, args.whisper_model)
    except Exception:
        logger.exception("리포트 생성 중 오류가 발생하여 실행을 중단합니다.")
        return 1

    print(f"리포트가 생성되었습니다: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
