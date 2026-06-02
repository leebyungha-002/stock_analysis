# -*- coding: utf-8 -*-
"""
시장 지표 자동 실행 & 텔레그램 전송 스크립트
  python market_indicator_runner.py --kr   → 한국 시장 지표 (오후 4시)
  python market_indicator_runner.py        → 기본 시장 지표 (오전 8시)
"""
import sys
import os
from datetime import datetime

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_STOCK_DIR = os.path.join(_THIS_DIR, 'stock_analysis')
if _STOCK_DIR not in sys.path:
    sys.path.insert(0, _STOCK_DIR)

import pandas as pd
from telegram_notifier import send_document


def _arrow(val: float) -> str:
    if val > 0: return "🔺"
    if val < 0: return "🔹"
    return "➖"


def run_kr_market_report(now_str: str):
    """kr_market_indicators.py → 코스피/코스닥 + 한국 거시경제"""
    from kr_market_indicators import get_market_indicators

    print("🔄 한국 시장 지표 수집 중...")
    df, sources, market_indices = get_market_indicators(days=5)

    lines = [f"🇰🇷 한국 시장 지표 리포트\n{now_str}"]

    if market_indices:
        lines.append("\n📈 한국 시장 지수")
        for name, data in market_indices.items():
            c, ch, pct = data['current'], data['change'], data['pct_change']
            lines.append(f" · {name}: {c:,.2f} ({_arrow(ch)} {ch:+.2f} / {pct:+.2f}%)")

    if not df.empty:
        latest = df.iloc[-1]
        lines.append("\n🇰🇷 거시경제 지표")
        for col in df.columns:
            val = latest[col]
            if pd.notna(val):
                lines.append(f" · {col}: {val:,.2f}")

    report   = "\n".join(lines)
    filename = f"kr_market_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    caption  = f"🇰🇷 한국 시장 지표 ({now_str})"

    print("📨 텔레그램 전송 중...")
    ok = send_document(report, filename=filename, caption=caption)
    print("✅ 전송 완료!" if ok else "⚠️  전송 실패.")


def run_market_report(now_str: str):
    """us_market_indicators.py → 미국 거시경제 (VIX/달러/금/국채/기준금리 등)"""
    from us_market_indicators import get_us_market_indicators

    print("🔄 미국 시장 지표 수집 중...")
    df, sources = get_us_market_indicators(days=5)

    lines = [f"🇺🇸 미국 시장 지표 리포트\n{now_str}"]

    if not df.empty:
        latest = df.iloc[-1]
        lines.append("\n🇺🇸 거시경제 지표")
        for col in df.columns:
            val = latest[col]
            if pd.notna(val):
                lines.append(f" · {col}: {val:,.2f}")

        if '미국채10년' in df.columns and '미국채2년' in df.columns:
            diff = latest['미국채10년'] - latest['미국채2년']
            signal = "정상" if diff > 0 else "역전(침체 신호)"
            lines.append(f"\n · 장단기금리차(10Y-2Y): {diff:+.2f}%p ({signal})")
    else:
        lines.append("\n⚠️ 데이터를 가져오지 못했습니다.")

    report   = "\n".join(lines)
    filename = f"us_market_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    caption  = f"🇺🇸 미국 시장 지표 ({now_str})"

    print("📨 텔레그램 전송 중...")
    ok = send_document(report, filename=filename, caption=caption)
    print("✅ 전송 완료!" if ok else "⚠️  전송 실패.")


def main():
    kr_mode = '--kr' in sys.argv[1:]
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    print(f"\n{'='*60}")
    print(f"📊 시장 지표 자동 실행 - {now_str}")
    print(f"{'='*60}")

    if kr_mode:
        run_kr_market_report(now_str)
    else:
        run_market_report(now_str)

    print(f"\n{'='*60}")
    print("✅ 완료!")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
