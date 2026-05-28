# -*- coding: utf-8 -*-
"""pykrx에서 투자자별 거래량/거래값 데이터 테스트"""
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd

code = '010140'  
end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")

print(f"조회 기간: {start_date} ~ {end_date}")
print("=" * 60)

# 1단계: 기본 OHLCV
print("\n[1] get_market_ohlcv_by_date")
try:
    df = stock.get_market_ohlcv_by_date(start_date, end_date, code)
    print(f"컬럼: {list(df.columns)}")
    print(f"행: {len(df)}")
    print(df.head(2))
except Exception as e:
    print(f"오류: {e}")

# 2단계: 거래량과 거래값
print("\n[2] get_market_trading_value_and_volume_by_ticker")
try:
    # 월별 데이터
    yearmonth = datetime.now().strftime("%Y%m")
    df = stock.get_market_trading_value_and_volume_by_ticker(yearmonth)
    if isinstance(df, pd.DataFrame) and not df.empty:
        print(f"결과: {len(df)}개 종목")
        print(f"컬럼: {list(df.columns[:5])}")
        if code in df.index or code.lstrip('0') in df.index.astype(str):
            print("종목 찾음")
    else:
        print("데이터 없음")
except Exception as e:
    print(f"오류: {e}")

# 3단계: 내부 함수 직접 호출 시도
print("\n[3] get_market_trading_volume_and_value (날짜 범위)")
try:
    df = stock.get_market_trading_value_by_date(start_date, end_date, code)
    print(f"컬럼: {list(df.columns)}")
    print(df)
except Exception as e:
    print(f"오류: {e}")

# 4단계: 원본 데이터 구조 확인
print("\n[4] 내부 구조 확인")
try:
    # stock._get_base_url() 등으로 API URL 확인 시도
    import inspect
    print("stock.get_market_trading_volume_by_date 소스:")
    print(inspect.getsource(stock.get_market_trading_volume_by_date)[:500])
except Exception as e:
    print(f"소스 확인 불가: {e}")
