# -*- coding: utf-8 -*-
"""새로 다운로드된 증권사 리포트 PDF를 Gemini로 요약해 마크다운으로 텔레그램 전송.
토큰 절약을 위해 PDF는 텍스트만 추출하고, 리포트당 텍스트는 MAX_CHARS_PER_REPORT로 자른다.
"""
import os
import time
from datetime import datetime

from pypdf import PdfReader
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

import telegram_notifier

MODEL = "gemini-flash-latest"
MAX_CHARS_PER_REPORT = 20000
CALL_INTERVAL_SEC = 1.0  # 연속 호출 사이 최소 간격 (레이트리밋 방지)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _extract_pdf_text(path, max_chars=MAX_CHARS_PER_REPORT):
    try:
        reader = PdfReader(path)
        parts = []
        total = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            if not t:
                continue
            parts.append(t)
            total += len(t)
            if total >= max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except Exception as e:
        print(f"    [PDF 텍스트 추출 실패] {os.path.basename(path)}: {e}")
        return ""


def _summarize_one(path):
    title = os.path.splitext(os.path.basename(path))[0]
    text = _extract_pdf_text(path)

    if not text.strip():
        return f"### {title}\n\n_(본문 텍스트를 추출하지 못했습니다.)_\n"

    prompt = (
        "다음은 증권사 리서치 리포트 본문에서 추출한 텍스트야. "
        "핵심 내용을 한국어 마크다운 불릿 포인트 4~6개로 요약해줘. "
        "투자의견/목표주가/핵심 근거가 있으면 포함하고, 없으면 산업 동향 요지 위주로 정리해줘. "
        "제목이나 인사말 없이 불릿 포인트만 출력해줘.\n\n"
        f"[리포트 제목: {title}]\n\n{text}"
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1000,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )
        summary = (response.text or "").strip() or "_(빈 응답)_"
    except genai_errors.APIError as e:
        summary = f"_(요약 실패: {e})_"

    return f"### {title}\n\n{summary}\n"


def summarize_and_notify(file_paths):
    """file_paths의 PDF들을 요약해, 소속 폴더(섹터/종목명)별로 마크다운 파일을 나눠 텔레그램 전송."""
    if not file_paths:
        print("  요약할 신규 리포트가 없습니다.")
        return

    groups = {}
    for path in file_paths:
        group = os.path.basename(os.path.dirname(path))
        groups.setdefault(group, []).append(path)

    total = len(file_paths)
    print(f"=== 4. 리포트 요약 ({total}건, {len(groups)}개 그룹, model={MODEL}) ===")

    date_str = datetime.now().strftime("%Y-%m-%d")
    done = 0
    for group in sorted(groups):
        paths = groups[group]
        print(f"  [그룹: {group}] {len(paths)}건")
        sections = []
        for path in paths:
            done += 1
            print(f"    [{done}/{total}] {os.path.basename(path)}")
            sections.append(_summarize_one(path))
            if done < total:
                time.sleep(CALL_INTERVAL_SEC)

        md = (
            f"# {group} 리포트 요약 ({date_str})\n\n"
            f"신규 리포트 {len(paths)}건\n\n"
            + "\n---\n\n".join(sections)
        )

        ok = telegram_notifier.send_document(
            md,
            filename=f"report_summary_{group}_{date_str}.md",
            caption=f"{group} 리포트 요약 {len(paths)}건 ({date_str})",
        )
        print(f"    텔레그램 전송: {'성공' if ok else '실패'}")
