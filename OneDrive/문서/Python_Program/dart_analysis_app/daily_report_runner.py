# -*- coding: utf-8 -*-
"""
주식 분석 자동 실행 & 텔레그램 전송 스크립트
  python daily_report_runner.py          → 전체 분석 + 텔레그램 전송
  python daily_report_runner.py --test   → 텔레그램 전송만 테스트 (분석 생략)
"""
import sys
import os
import time
from datetime import datetime, timedelta

# Windows UTF-8 출력 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# stock_analysis 폴더를 import 경로에 추가
_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_STOCK_DIR = os.path.join(_THIS_DIR, 'stock_analysis')
if _STOCK_DIR not in sys.path:
    sys.path.insert(0, _STOCK_DIR)

import pandas as pd

from kr_market_indicators import get_market_indicators
from us_market_indicators  import get_us_market_indicators
from kr_stock_api          import MY_FAVORITES, find_stock_code, get_stock_data_for_gemini
from us_stock_api          import MY_US_FAVORITES, _fetch_ohlcv, _add_technical_indicators
from telegram_notifier     import send_message

try:
    from pykrx import stock as pykrx_stock
except ImportError:
    pykrx_stock = None


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def _arrow(val: float) -> str:
    if val > 0: return "🔺"
    if val < 0: return "🔹"
    return "➖"


# ─────────────────────────────────────────────
# 섹션 빌더
# ─────────────────────────────────────────────
def build_kr_market_section() -> str:
    """한국 시장지수 + 거시경제 지표 요약 문자열 반환"""
    lines = []
    try:
        df, _, market_indices = get_market_indicators(days=5)

        if market_indices:
            lines.append("\n📈 <b>한국 시장 지수</b>")
            for idx_name, data in market_indices.items():
                c, ch, pct = data['current'], data['change'], data['pct_change']
                lines.append(f" · {idx_name}: {c:,.2f} ({_arrow(ch)} {ch:+.2f} / {pct:+.2f}%)")

        if not df.empty:
            latest = df.iloc[-1]
            lines.append("\n🇰🇷 <b>한국 거시경제</b>")
            for col in ['환율(원달러)', '미국국채10년', 'WTI원유', 'CPI(물가)', '실업률(%)']:
                if col in df.columns and pd.notna(latest[col]):
                    lines.append(f" · {col}: {latest[col]:,.2f}")
    except Exception as e:
        lines.append(f"\n⚠️ 한국 지표 수집 오류: {e}")
    return "\n".join(lines)


def build_us_market_section() -> str:
    """미국 거시경제 지표 요약 문자열 반환"""
    lines = []
    try:
        df, _ = get_us_market_indicators(days=5)
        if not df.empty:
            latest = df.iloc[-1]
            lines.append("\n🇺🇸 <b>미국 거시경제</b>")
            for col in ['VIX(공포)', '달러인덱스', '금(Gold)', '미국채10년', '기준금리(%)']:
                if col in df.columns and pd.notna(latest[col]):
                    lines.append(f" · {col}: {latest[col]:,.2f}")

            # 장단기 금리차
            if '미국채10년' in df.columns and '미국채2년' in df.columns:
                diff = latest['미국채10년'] - latest['미국채2년']
                signal = "정상" if diff > 0 else "역전(침체 신호)"
                lines.append(f" · 장단기금리차(10Y-2Y): {diff:+.2f}%p ({signal})")

            # 금/구리 비율
            if '금/구리비율' in df.columns and pd.notna(latest.get('금/구리비율')):
                ratio = latest['금/구리비율']
                if len(df) >= 2:
                    ch = ratio - df.iloc[-2]['금/구리비율']
                    note = "경기둔화 신호" if ch > 0 else "경기회복 신호"
                    lines.append(f" · 금/구리비율: {ratio:.2f} ({_arrow(ch)} {note})")
                else:
                    lines.append(f" · 금/구리비율: {ratio:.2f}")
    except Exception as e:
        lines.append(f"\n⚠️ 미국 지표 수집 오류: {e}")
    return "\n".join(lines)


def _extract_daily_lines(prompt: str) -> str:
    """프롬프트에서 일별 상세 데이터 줄만 추출"""
    lines = []
    in_daily = False
    for line in prompt.splitlines():
        if '일별 상세 데이터' in line:
            in_daily = True
            continue
        if in_daily:
            if line.strip().startswith('3.'):
                break
            if line.strip().startswith('- '):
                lines.append(line.strip())
    return "\n".join(lines)


def build_kr_stocks_section() -> str:
    """한국 관심종목 수급 요약 + 일별 데이터 문자열 반환"""
    lines = [f"\n🇰🇷 <b>한국 관심종목</b> ({len(MY_FAVORITES)}개)"]
    anomalies = []

    for name in MY_FAVORITES:
        code, found_name = find_stock_code(name)
        if not code:
            lines.append(f"\n · {name}: 코드 없음")
            continue

        try:
            prompt, supply = get_stock_data_for_gemini(code, found_name, days=10)

            # 현재가 조회 (pykrx)
            price, change = 0, 0.0
            if pykrx_stock:
                try:
                    end   = datetime.now()
                    start = end - timedelta(days=10)
                    df_p  = pykrx_stock.get_market_ohlcv(
                        start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), code)
                    if not df_p.empty:
                        price  = int(df_p.iloc[-1]['종가'])
                        change = float(df_p.iloc[-1]['등락률'])
                except Exception:
                    pass

            f_acc = supply.get('foreign_accumulated', 0)
            i_acc = supply.get('inst_accumulated', 0)
            f_con = supply.get('foreign_consecutive', 0)
            i_con = supply.get('inst_consecutive', 0)
            f5    = supply.get('foreign_5day_continuous', False)
            i5    = supply.get('inst_5day_continuous', False)

            f_mark = "🔴" if f_acc > 0 else "🔵" if f_acc < 0 else "➖"
            i_mark = "🔴" if i_acc > 0 else "🔵" if i_acc < 0 else "➖"

            price_str = f"{price:,}원" if price else "-"
            chg_str   = f"{change:+.2f}%" if change else "-"
            star      = " ⭐" if (f5 or i5) else ""

            # 종목 헤더
            lines.append(
                f"\n<b>▪ {found_name}</b>: {price_str} {_arrow(change)}{chg_str}"
                f" | 외인{f_mark}{f_con}일 기관{i_mark}{i_con}일{star}"
            )

            # 일별 상세 데이터
            if isinstance(prompt, str):
                daily = _extract_daily_lines(prompt)
                if daily:
                    lines.append(daily)

            for a in supply.get('anomalies', []):
                anomalies.append(f" · {found_name}: {a}")

            time.sleep(0.5)
        except Exception as e:
            lines.append(f" · {name}: 분석 오류 ({str(e)[:40]})")

    if anomalies:
        lines.append("\n⭐ <b>수급 특이사항</b>")
        lines.extend(anomalies)

    return "\n".join(lines)


def build_us_stocks_section() -> str:
    """미국 관심종목 기술적 분석 요약 문자열 반환"""
    lines = [f"\n🇺🇸 <b>미국 관심종목</b> ({len(MY_US_FAVORITES)}개)\n"]

    for ticker in MY_US_FAVORITES:
        try:
            df = _fetch_ohlcv(ticker, period="2y")
            if df is None or df.empty:
                lines.append(f" · {ticker}: 데이터 없음")
                continue

            df   = _add_technical_indicators(df)
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else last

            price   = last['Close']
            chg_pct = ((price - prev['Close']) / prev['Close'] * 100) if prev['Close'] else 0.0

            rsi = last.get('RSI')
            if pd.isna(rsi):
                rsi_str = "RSI:-"
            elif rsi > 70:
                rsi_str = f"RSI:과매수({rsi:.0f})"
            elif rsi < 30:
                rsi_str = f"RSI:과매도({rsi:.0f})"
            else:
                rsi_str = f"RSI:중립({rsi:.0f})"

            trend = "상승" if last['MA5'] > last['MA20'] else "조정"
            lines.append(f" · {ticker}: ${price:.2f} {_arrow(chg_pct)}{chg_pct:+.2f}% | {rsi_str} {trend}추세")
            time.sleep(0.5)
        except Exception as e:
            lines.append(f" · {ticker}: 분석 오류 ({str(e)[:40]})")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main():
    test_mode = '--test' in sys.argv
    now_str   = datetime.now().strftime('%Y-%m-%d %H:%M')

    print(f"\n{'='*60}")
    print(f"📊 주식 분석 자동 실행 - {now_str}")
    print(f"{'='*60}")

    if test_mode:
        print("\n[테스트 모드] 텔레그램 연결만 확인합니다.")
        ok = send_message(f"✅ 텔레그램 연결 테스트 성공!\n{now_str}")
        print("✅ 연결 성공!" if ok else "❌ 연결 실패 - .env 파일을 확인하세요.")
        return

    # ── 섹션 수집 ──────────────────────────────
    print("\n[1/4] 한국 거시경제 수집 중...")
    kr_market = build_kr_market_section()

    print("[2/4] 미국 거시경제 수집 중...")
    us_market = build_us_market_section()

    print("[3/4] 한국 관심종목 분석 중... (약 2~3분 소요)")
    kr_stocks = build_kr_stocks_section()

    print("[4/4] 미국 관심종목 분석 중...")
    us_stocks = build_us_stocks_section()

    # ── 텔레그램 전송 ──────────────────────────
    print("\n📨 텔레그램 전송 중...")
    results = []

    # 메시지 1: 거시경제 요약
    msg1 = f"<b>📊 주식 분석 리포트</b>\n{now_str}\n{kr_market}\n{us_market}"
    results.append(send_message(msg1))
    time.sleep(1)

    # 메시지 2: 한국 관심종목 (일별 데이터 포함, 길어서 자동 분할됨)
    results.append(send_message(kr_stocks))
    time.sleep(1)

    # 메시지 3: 미국 관심종목
    results.append(send_message(us_stocks))

    if all(results):
        print("✅ 텔레그램 전송 완료!")
    else:
        print("⚠️  일부 메시지 전송 실패. .env 파일을 확인하세요.")

    print(f"\n{'='*60}")
    print("✅ 분석 완료!")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
