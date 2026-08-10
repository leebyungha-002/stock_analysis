"""Gemini API를 이용한 영상 트랜스크립트 요약. 긴 트랜스크립트는 map-reduce로 처리합니다."""
from __future__ import annotations

import logging
import os

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

MODEL = "gemini-flash-latest"
CHUNK_CHAR_SIZE = 12000  # 청크당 대략적인 문자 수 (한/영 혼용 기준 안전 마진)
MAP_REDUCE_THRESHOLD = 12000

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _chunk_text(text: str, size: int = CHUNK_CHAR_SIZE) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _call_gemini(prompt: str, max_tokens: int) -> str:
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            # thinking 토큰이 max_output_tokens 예산을 잠식해 응답이 중간에 잘리는 것을 방지
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )
    return (response.text or "").strip()


def _summarize_chunk(chunk: str, title: str) -> str:
    prompt = (
        f"다음은 유튜브 영상 '{title}'의 트랜스크립트 일부입니다. "
        "핵심 내용을 한국어로 5줄 이내 불릿 포인트로 요약해줘.\n\n"
        f"트랜스크립트:\n{chunk}"
    )
    return _call_gemini(prompt, max_tokens=1500)


def _reduce_summaries(chunk_summaries: list[str], title: str) -> str:
    combined = "\n\n".join(
        f"[구간 {i + 1}]\n{summary}" for i, summary in enumerate(chunk_summaries)
    )
    prompt = (
        f"다음은 유튜브 영상 '{title}'을 구간별로 요약한 내용입니다. "
        "이를 종합해서 이 영상 전체의 핵심 내용을 한국어로 자연스럽게 8줄 이내로 요약해줘. "
        "중복되는 내용은 합치고, 영상의 주제와 결론이 잘 드러나도록 작성해줘.\n\n"
        f"{combined}"
    )
    return _call_gemini(prompt, max_tokens=2000)


def summarize_transcript(transcript: str, title: str) -> str:
    """트랜스크립트를 요약합니다. 길이가 길면 map-reduce 방식을 사용합니다."""
    transcript = transcript.strip()
    if not transcript:
        return "(트랜스크립트를 가져올 수 없어 요약을 생성하지 못했습니다.)"

    try:
        if len(transcript) <= MAP_REDUCE_THRESHOLD:
            prompt = (
                f"다음은 유튜브 영상 '{title}'의 트랜스크립트입니다. "
                "핵심 내용을 한국어로 자연스럽게 8줄 이내로 요약해줘. "
                "영상의 주제와 결론이 잘 드러나도록 작성해줘.\n\n"
                f"트랜스크립트:\n{transcript}"
            )
            return _call_gemini(prompt, max_tokens=2000)

        logger.info("긴 트랜스크립트(%d자) → map-reduce 요약 진행 (title=%s)", len(transcript), title)
        chunks = _chunk_text(transcript)
        chunk_summaries = [_summarize_chunk(chunk, title) for chunk in chunks]
        return _reduce_summaries(chunk_summaries, title)
    except genai_errors.APIError as exc:
        logger.error("Gemini 요약 실패 (title=%s): %s", title, exc)
        raise
