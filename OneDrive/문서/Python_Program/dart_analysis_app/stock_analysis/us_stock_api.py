# -*- coding: utf-8 -*-
"""
미국 주식 데이터 분석 전용
- FinanceDataReader 1차 사용, 실패 시 yfinance
- 2년치 로드 후 MA200 등 지표 계산, 최근 N일만 출력
"""
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import time

try:
    import FinanceDataReader as fdr
except ImportError:
    fdr = None

import yfinance as yf

# ==========================================
# ⭐ Blue Sky님의 미국 관심 종목 (티커 입력)
# ==========================================
MY_US_FAVORITES = ['GGLL', 'SOXL', 'TSLL', 'TQQQ', 'RKLB', 'PLTR']


def _fetch_ohlcv_us_fdr(symbol, start_dt, end_dt):
    """FinanceDataReader로 미국 주식 OHLCV 조회."""
    if fdr is None:
        return None
    try:
        df = fdr.DataReader(symbol, start_dt, end_dt)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if "Close" not in df.columns:
        return None
    return df.copy()


def _fetch_ohlcv(symbol, period="2y"):
    """미국 주식: FinanceDataReader 1차 → 실패 시 yfinance."""
    import warnings
    symbol = str(symbol).strip()
    end_dt = datetime.now()
    if period == "max":
        start_dt = end_dt - timedelta(days=365 * 30)
    else:
        start_dt = end_dt - timedelta(days=365 * 2 + 60)

    data = _fetch_ohlcv_us_fdr(symbol, start_dt, end_dt)

    if data is None or data.empty:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("ignore")
            try:
                data = yf.Ticker(symbol).history(start=start_dt, end=end_dt, auto_adjust=True)
            except Exception:
                pass
    if data is None or data.empty:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("ignore")
            try:
                data = yf.download(
                    symbol, start=start_dt, end=end_dt,
                    progress=False, auto_adjust=True, threads=False, ignore_tz=True
                )
            except Exception:
                pass

    if data is None or data.empty:
        return None

    # 컬럼 정리
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)
    if "Close" not in data.columns:
        for k in ["Close", "Adj Close"]:
            if k in data.columns:
                data["Close"] = data[k]
                break
    if "Close" not in data.columns:
        return None
    return data


def calculate_rsi(series, period=14):
    """RSI(상대강도지수) 계산"""
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _add_technical_indicators(df):
    """
    전체 데이터프레임에 MA20, MA200, RSI 등 기술적 지표 계산.
    상장 200일 미만 종목은 MA200은 NaN 유지 (예외 처리).
    """
    if df is None or df.empty:
        return df
    close = df["Close"]
    df = df.copy()
    df["MA5"] = close.rolling(window=5).mean()
    df["MA20"] = close.rolling(window=20).mean()
    df["MA200"] = close.rolling(window=200).mean()  # 200일 미만이면 NaN
    df["RSI"] = calculate_rsi(close)
    return df


def _format_ma200(value, prefix=""):
    """MA200이 NaN이면 '데이터 부족' 표기. prefix 예: '$'"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "데이터 부족"
    return f"{prefix}{value:,.2f}"


def get_us_stock_data(ticker, days=10, period="2y"):
    """
    미국 주식 데이터 분석 프롬프트 생성.
    데이터: 미국은 FinanceDataReader 1차 → yfinance 보조. 2년치 로드 후 MA200 등 지표 계산, 최근 days일만 출력.
    """
    # 1. 데이터 호출 (최소 2년: MA200 계산용)
    df = _fetch_ohlcv(ticker, period=period)
    if df is None or df.empty:
        return f"❌ {ticker} 데이터를 찾을 수 없습니다."

    # 2. 전체 df에 기술적 지표 계산 (슬라이싱 전에 수행)
    df = _add_technical_indicators(df)
    if df is None or df.empty:
        return f"❌ {ticker} 지표 계산 실패."

    # 3. 지표 계산 완료 후, 출력/분석용으로 최근 days일만 슬라이싱
    recent_df = df.tail(days)
    if recent_df.empty:
        return f"❌ {ticker} 최근 {days}일 데이터 없음."
    last_row = recent_df.iloc[-1]

    # 4. 예외 처리: MA200 NaN이면 '데이터 부족' 표기
    ma200_str = _format_ma200(last_row.get("MA200"), prefix="$")

    # 추세 / RSI
    trend = "상승추세 (정배열)" if last_row["MA5"] > last_row["MA20"] else "조정/하락 (역배열)"
    rsi_val = last_row.get("RSI")
    if pd.isna(rsi_val):
        rsi_status = "RSI 계산 불가"
    else:
        rsi_status = (
            f"과매수({rsi_val:.1f})"
            if rsi_val > 70
            else f"과매도({rsi_val:.1f})" if rsi_val < 30 else f"중립({rsi_val:.1f})"
        )

    # 프롬프트 생성
    prompt = f"""
[제미나이 미국주식 분석 요청]
미국 주식 '{ticker}'의 기술적 흐름을 분석해줘.

1. **핵심 요약**:
   - 현재가: ${last_row['Close']:,.2f}
   - 기술적 추세: {trend}
   - RSI 지표: {rsi_status}
   - 200일 이동평균선: {ma200_str} (장기 추세 기준, 상장 200일 미만 시 데이터 부족)

2. **일별 상세 데이터 (최근 {days}일)**:
   (단위: 달러 / 거래량)
"""
    for date, row in recent_df.iterrows():
        date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)[:10]
        prev_close = df["Close"].shift(1).loc[date] if date in df.index else np.nan
        if pd.notna(prev_close) and prev_close != 0:
            chg_pct = ((row["Close"] - prev_close) / prev_close) * 100
        else:
            chg_pct = 0.0
        icon = "🔺" if chg_pct > 0 else "🔹" if chg_pct < 0 else "-"
        vol = row.get("Volume", 0)
        if pd.isna(vol):
            vol = 0
        prompt += f"   - {date_str}: {icon} ${row['Close']:,.2f} ({chg_pct:+.2f}%) | Vol: {vol:,.0f}\n"

    prompt += """
3. **분석 요청 사항**:
   - **기술적 위치**: 현재 주가가 20일선/200일선 대비 어디에 있는지(지지/저항) 분석해줘.
   - **RSI 분석**: 현재 과매수/과매도 구간인지, 진입 시점인지 판단해줘.
   - **종합 의견**: 보수적인 관점에서 매수/매도/관망 의견을 줘.
"""
    return prompt


# ==========================================
# 🚀 실행 부분
# ==========================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🗽 Blue Sky님의 [미국 주식] 분석 시스템")
    print("=" * 60)

    for ticker in MY_US_FAVORITES:
        print(f"\n🇺🇸 '{ticker}' 데이터 분석 중...")
        report = get_us_stock_data(ticker)
        print("-" * 50)
        print(report)
        print("-" * 50)
        time.sleep(1)  # Yahoo API 연속 요청 시 차단 완화

    print("\n" + "=" * 60)
    ask = input("❓ 추가 분석할 미국 티커 (예: NVDA, AAPL / 종료: 엔터): ").strip()
    if ask:
        print(get_us_stock_data(ask.strip().upper()))
    else:
        print("Good Night! 🌙")
