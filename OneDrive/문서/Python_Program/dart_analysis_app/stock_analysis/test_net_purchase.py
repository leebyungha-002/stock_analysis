# -*- coding: utf-8 -*-
"""pykrx get_market_trading_volume_by_date 테스트"""
from pykrx import stock
from datetime import datetime, timedelta

code = '010140'
end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")

print(f"기간: {start_date} ~ {end_date}")
print("=" * 60)

try:
    df = stock.get_market_trading_volume_by_date(start_date, end_date, code, on='순매수')
    print(f"컬럼: {list(df.columns)}")
    print(f"데이터 크기: {df.shape}")
    print(f"\n데이터:\n{df}")
    
    if not df.empty:
        print("\n✅ 성공! 순매수 데이터가 있습니다.")
    else:
        print("\n❌ 데이터가 비어있습니다.")
        
except Exception as e:
    print(f"❌ 오류: {e}")
    import traceback
    traceback.print_exc()
