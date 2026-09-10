# -*- coding: utf-8 -*-
"""새로 다운로드된 증권사 리포트 PDF를 Gemini로 구조화 요약해 텔레그램 전송.
- 리포트당 JSON으로 구조화 추출(핵심요약/기술설명/종목설명/거시경제/산업특화지표 등).
- 텔레그램 메시지(4096자 제한)에는 핵심요약+컨센서스대비+향후일정만 간단히 전송.
- 전체 상세 내용(기술설명/종목설명/거시경제 등 포함)은 마크다운 파일로 첨부 전송.
토큰 절약을 위해 PDF는 텍스트만 추출하고, 리포트당 텍스트는 MAX_CHARS_PER_REPORT로 자른다.
"""
import html
import json
import os
import re
import time
from datetime import datetime

from pypdf import PdfReader
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

import telegram_notifier

MODEL = "gemini-flash-latest"
MAX_CHARS_PER_REPORT = 20000
MAX_OUTPUT_TOKENS = 2800  # 필드가 늘어나 출력 토큰 증가 (기존 1000 -> 2800)
CALL_INTERVAL_SEC = 1.0  # 연속 호출 사이 최소 간격 (레이트리밋 방지)

# 폴더명(=산업분류, organize_downloaded_files의 KEYWORD_MAP 기준)별 특화 지표 안내.
# 여기 없는 그룹(예: 보유 종목 폴더명 = 종목명)에는 범용 안내를 사용.
INDUSTRY_HINTS = {
    "반도체_IT": "D램/낸드 가격 동향, 파운드리 가동률, 반도체 장비/소재 수급",
    "2차전지": "리튬/니켈/코발트 등 원자재 가격 동향, 배터리 수율 및 증설 계획",
    "화학_에너지": "국제 유가, 정제마진, 화학제품 스프레드",
    "바이오_헬스": "임상 진행 단계, 신약 승인/허가 일정, 기술수출 계약 조건",
    "금융_지주": "순이자마진(NIM), 대손충당금, 자기자본이익률(ROE)",
    "자동차_운송": "글로벌 완성차 판매량, 전기차 침투율, 운임 지수",
    "조선_기계_건설": "해상운임지수(BDI 등), 중고선박 가격지수, 수주잔고",
    "소비재_플랫폼": "MAU/트래픽 지표, 광고 단가, 소비 트렌드 변화",
}
DEFAULT_INDUSTRY_HINT = "언급된 산업의 가격지수, 수급, 가동률 등 특화 지표"

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


def _build_prompt(title, industry, text):
    hint = INDUSTRY_HINTS.get(industry, DEFAULT_INDUSTRY_HINT)
    return f"""다음은 증권사 리서치 리포트 본문에서 추출한 텍스트야. 아래 JSON 스키마에 맞춰
한국어로 내용을 추출해줘. 리포트에 없는 정보는 절대 지어내지 말고 반드시 null로 채워줘.
출력은 다른 설명 없이 JSON 객체 하나만 출력해줘 (코드블록 표시(```)도 쓰지 마).

[이 리포트의 산업분류: {industry}]
이 산업분류에서는 특히 "{hint}" 관련 내용이 있는지 확인해서, 언급되어 있다면
반드시 "산업특화지표"에 포함시켜줘.

JSON 스키마:
{{
  "핵심요약": "리포트의 핵심 내용을 5~7문장으로 요약. 결론뿐 아니라 배경 설명과 인과관계를 포함",
  "기술설명": [
    {{"기술명": "예: HBM(고대역폭메모리)", "설명": "이 기술이 무엇이고 왜 중요한지, 시장에 미치는 영향을 2~3문장으로"}}
  ],
  "종목설명": [
    {{"종목명": "예: LG이노텍", "설명": "레포트에서 이 종목에 대해 설명한 사업 내용, 실적 배경, 투자 포인트를 2~3문장으로"}}
  ],
  "반도체투자전망": "반도체 설비투자(CAPEX), 파운드리 가동률, 공급/수요 전망 관련 내용이 있으면 요약. 없으면 null",
  "거시경제요인": {{
    "금리전망": "언급 있으면 요약, 없으면 null",
    "환율전망": "언급 있으면 요약, 없으면 null",
    "유가전망": "언급 있으면 요약, 없으면 null"
  }},
  "산업특화지표": "위 안내에 따른 산업 특화 지표 언급이 있으면 요약, 없으면 null",
  "컨센서스대비": "실적/전망치가 시장 컨센서스 대비 상회/하회/부합했는지와 그 근거. 언급 없으면 null",
  "향후일정": ["향후 catalyst 일정(실적발표일, 신제품 출시, 정책 발표 등). 없으면 빈 배열"],
  "공급망정보": "주요 고객사, 원재료 의존도 등 공급망 관련 언급이 있으면 요약. 없으면 null",
  "밸류에이션코멘트": "PER/PBR 등 밸류에이션 관련 코멘트가 있으면 요약. 없으면 null"
}}

기술설명, 종목설명, 향후일정에 해당 내용이 없으면 빈 배열 []로 둬.
투자의견/목표주가가 있으면 핵심요약에 포함시켜줘.

[리포트 제목: {title}]

{text}"""


def _parse_json_response(raw_text):
    """모델 출력에서 JSON 객체를 파싱. 코드펜스가 섞여 나와도 처리."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _summarize_one(path, industry):
    """PDF 한 건을 구조화 요약. 반환: {"title", "data": dict|None, "error": str|None}"""
    title = os.path.splitext(os.path.basename(path))[0]
    text = _extract_pdf_text(path)

    if not text.strip():
        return {"title": title, "data": None, "error": "본문 텍스트를 추출하지 못했습니다."}

    prompt = _build_prompt(title, industry, text)

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
                response_mime_type="application/json",
            ),
        )
        raw_text = (response.text or "").strip()
    except genai_errors.APIError as e:
        return {"title": title, "data": None, "error": f"요약 실패: {e}"}

    data = _parse_json_response(raw_text)
    if data is None:
        return {"title": title, "data": None, "error": "JSON 파싱 실패", "raw": raw_text}

    return {"title": title, "data": data, "error": None}


# ---------------------------------------------------------------------------
# 마크다운 포맷팅
# ---------------------------------------------------------------------------

def _fmt_list_of_dicts(items, name_key, desc_key):
    """[{"기술명": "...", "설명": "..."}] -> "- 기술명: 설명" 줄바꿈 목록."""
    if not items or not isinstance(items, list):
        return None
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get(name_key) or "").strip()
        desc = (item.get(desc_key) or "").strip()
        if not name and not desc:
            continue
        lines.append(f"- {name}: {desc}" if name else f"- {desc}")
    return "\n".join(lines) if lines else None


def _fmt_macro(macro):
    if not macro or not isinstance(macro, dict):
        return None
    labels = {"금리전망": "금리전망", "환율전망": "환율전망", "유가전망": "유가전망"}
    lines = []
    for key, label in labels.items():
        val = macro.get(key)
        if val:
            lines.append(f"- {label}: {val}")
    return "\n".join(lines) if lines else None


def _fmt_schedule(items):
    if not items or not isinstance(items, list):
        return None
    lines = [f"- {str(x).strip()}" for x in items if str(x).strip()]
    return "\n".join(lines) if lines else None


def _detail_markdown(title, result):
    """리포트 1건의 전체 상세 마크다운 섹션."""
    if result.get("error") and not result.get("data"):
        return f"### {title}\n\n_({result['error']})_\n"

    data = result["data"]
    parts = [f"### {title}\n"]

    core = (data.get("핵심요약") or "").strip()
    parts.append(core or "_(핵심요약 없음)_")

    tech = _fmt_list_of_dicts(data.get("기술설명"), "기술명", "설명")
    if tech:
        parts.append(f"\n**기술설명**\n{tech}")

    stocks = _fmt_list_of_dicts(data.get("종목설명"), "종목명", "설명")
    if stocks:
        parts.append(f"\n**종목설명**\n{stocks}")

    if data.get("반도체투자전망"):
        parts.append(f"\n**반도체 투자전망**: {data['반도체투자전망']}")

    macro = _fmt_macro(data.get("거시경제요인"))
    if macro:
        parts.append(f"\n**거시경제 요인**\n{macro}")

    industry_metric = data.get("산업특화지표")
    if isinstance(industry_metric, dict):
        industry_metric = industry_metric.get("설명")
    if industry_metric:
        parts.append(f"\n**산업특화지표**: {industry_metric}")

    if data.get("컨센서스대비"):
        parts.append(f"\n**컨센서스 대비**: {data['컨센서스대비']}")

    schedule = _fmt_schedule(data.get("향후일정"))
    if schedule:
        parts.append(f"\n**향후일정**\n{schedule}")

    if data.get("공급망정보"):
        parts.append(f"\n**공급망정보**: {data['공급망정보']}")

    if data.get("밸류에이션코멘트"):
        parts.append(f"\n**밸류에이션 코멘트**: {data['밸류에이션코멘트']}")

    return "\n".join(parts) + "\n"


def _short_html(title, result):
    """텔레그램 메시지용 간단 요약(핵심요약+컨센서스대비+향후일정). HTML 이스케이프 처리."""
    if result.get("error") and not result.get("data"):
        return f"<b>{html.escape(title)}</b>\n({html.escape(result['error'])})"

    data = result["data"]
    lines = [f"<b>{html.escape(title)}</b>"]

    core = (data.get("핵심요약") or "").strip()
    if core:
        lines.append(html.escape(core))

    if data.get("컨센서스대비"):
        lines.append(f"· 컨센서스 대비: {html.escape(str(data['컨센서스대비']))}")

    schedule = data.get("향후일정")
    if schedule and isinstance(schedule, list):
        sched_items = [str(x).strip() for x in schedule if str(x).strip()]
        if sched_items:
            lines.append("· 향후일정: " + ", ".join(html.escape(x) for x in sched_items))

    return "\n".join(lines)


_TELEGRAM_MAX_LEN = 4096
_TELEGRAM_SEND_INTERVAL_SEC = 0.5  # 연속 메시지 전송 사이 최소 간격 (레이트리밋 방지)


def _pack_messages(sections, header=None, max_len=_TELEGRAM_MAX_LEN):
    """header + 리포트별 섹션들을 리포트 경계에서만 잘라 max_len 이내 메시지 묶음으로 합친다.
    (리포트 중간이나 <b> 태그 중간에서 자르지 않아 HTML 파싱 오류를 피한다.)"""
    messages = []
    current = header or ""
    for section in sections:
        candidate = current + "\n\n" + section if current else section
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            messages.append(current)
        # 리포트 한 건 자체가 max_len을 넘는 극단적인 경우는 그대로 별도 메시지로 보낸다
        # (send_message의 자체 길이 분할에 맡김. 흔치 않은 경우라 태그 잘림 위험을 감수).
        current = section
    if current:
        messages.append(current)
    return messages


def summarize_and_notify(file_paths):
    """file_paths의 PDF들을 구조화 요약해, 소속 폴더(섹터/종목명)별로 정리 후 텔레그램 전송.
    - 간단 요약(핵심요약+컨센서스대비+향후일정): 텔레그램 메시지로 바로 전송
    - 전체 상세 내용: 마크다운 파일로 첨부 전송
    """
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

        results = []
        for path in paths:
            done += 1
            title = os.path.splitext(os.path.basename(path))[0]
            print(f"    [{done}/{total}] {os.path.basename(path)}")
            results.append((title, _summarize_one(path, group)))
            if done < total:
                time.sleep(CALL_INTERVAL_SEC)

        # 1) 간단 요약 -> 텔레그램 메시지 (리포트 경계에서만 잘라 여러 건으로 묶어서 전송.
        #    리포트마다 메시지를 따로 보내면 건수가 많을 때 스팸처럼 느껴지고
        #    레이트리밋 위험도 커지므로, 4096자 안에서 최대한 묶는다.)
        header = f"<b>{html.escape(group)} 리포트 요약 ({date_str})</b>\n신규 리포트 {len(paths)}건"
        short_sections = [_short_html(t, r) for t, r in results]
        packed = _pack_messages(short_sections, header=header)

        msg_ok = True
        for i, msg in enumerate(packed):
            ok = telegram_notifier.send_message(msg)
            msg_ok = msg_ok and ok
            if i < len(packed) - 1:
                time.sleep(_TELEGRAM_SEND_INTERVAL_SEC)
        print(f"    텔레그램 메시지 전송: {'성공' if msg_ok else '실패'} ({len(packed)}건으로 압축)")
        time.sleep(_TELEGRAM_SEND_INTERVAL_SEC)

        # 2) 전체 상세 -> 마크다운 파일 첨부
        detail_sections = [_detail_markdown(t, r) for t, r in results]
        md = (
            f"# {group} 리포트 상세 ({date_str})\n\n"
            f"신규 리포트 {len(paths)}건\n\n"
            + "\n---\n\n".join(detail_sections)
        )
        doc_ok = telegram_notifier.send_document(
            md,
            filename=f"report_detail_{group}_{date_str}.md",
            caption=f"{group} 상세 리포트 {len(paths)}건 ({date_str})",
        )
        print(f"    텔레그램 파일 전송: {'성공' if doc_ok else '실패'}")
