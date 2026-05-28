# -*- coding: utf-8 -*-
"""pykrx 간단 테스트"""
from pykrx import stock
from datetime import datetime, timedelta

code = '010140'
end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

print("=" * 60)
print("[OHLCV by date]")
print("=" * 60)
df = stock.get_market_ohlcv_by_date(start_date, end_date, code)
print(f"컬럼: {list(df.columns)}")
print(df)

