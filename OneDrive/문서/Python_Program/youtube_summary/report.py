"""채널별 주간 Top3 영상 요약 결과를 마크다운 리포트로 생성합니다."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def generate_report(results: list[dict[str, Any]], report_date: dt.date | None = None) -> Path:
    """채널별 Top3 영상 요약 결과를 마크다운 리포트로 저장하고 파일 경로를 반환합니다.

    results 형식: [{"channel_name": str, "videos": [{"title", "url", "view_count",
    "published_at", "summary"}, ...]}]
    """
    report_date = report_date or dt.date.today()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [f"# 주간 유튜브 채널 Top3 요약 ({report_date.isoformat()})", ""]

    if not results:
        lines.append("이번 주에는 요약할 영상이 없습니다.")
    else:
        for channel in results:
            lines.append(f"## {channel['channel_name']}")
            lines.append("")

            videos = channel.get("videos", [])
            if not videos:
                if channel.get("fetch_failed"):
                    lines.append("⚠️ 조회 실패 — 영상 목록을 가져오지 못했습니다. (logs/youtube_summary.log 확인)")
                else:
                    lines.append("최근 7일간 업로드된 영상이 없습니다.")
                lines.append("")
                continue

            for rank, video in enumerate(videos, start=1):
                lines.append(f"### {rank}. {video['title']}")
                lines.append(f"- 조회수: {video['view_count']:,}회")
                lines.append(f"- 게시일: {video['published_at']}")
                lines.append(f"- 링크: {video['url']}")
                lines.append("")
                lines.append(video["summary"])
                lines.append("")

    report_path = REPORTS_DIR / f"{report_date.isoformat()}_weekly_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
