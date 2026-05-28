import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# 📌 화면 출력 설정
# ==========================================
pd.set_option('display.unicode.east_asian_width', True)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def get_market_indicators(days=365):
    """
    한국 시장 지표와 거시경제 지표를 가져오는 함수 (Source 정보 포함)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 100) 
    
    # -------------------------------------------------------
    # 1. 수집 대상 및 출처 정의
    # -------------------------------------------------------
    # [Daily] Yahoo Finance (FDR 기본)
    daily_symbols = {
        'USD/KRW': ('환율(원달러)', 'Yahoo Finance'),
        'US10YT': ('미국국채10년', 'Yahoo Finance'), 
        'CL=F': ('WTI원유', 'Yahoo Finance (NYMEX)')
    }
    
    # [Monthly] FRED (세인트루이스 연준)
    fred_symbols = {
        'FRED:KORCPIALLMINMEI': ('CPI(물가)', 'FRED (OECD/통계청)'),
        'FRED:LRHUTTTTKRM156S': ('실업률(%)', 'FRED (OECD/통계청)'),
        'FRED:MYAGM2KRM189N': ('M2(조원)', 'FRED (한국은행)'),
        'FRED:XTEXVA01KRM667S': ('수출(억불)', 'FRED (한국은행/관세청)')
    }

    df_list = []
    source_info = {} # 출처 정보를 담을 딕셔너리

    print(f"🔄 한국 경제 지표 수집 및 정렬 중 (최근 {days}일)...")
    
    # -------------------------------------------------------
    # 2. 데이터 수집 로직
    # -------------------------------------------------------
    # (1) Daily 지표
    for ticker, (name, source) in daily_symbols.items():
        try:
            tmp = fdr.DataReader(ticker, start_date, end_date)
            if not tmp.empty:
                col = 'Close' if 'Close' in tmp.columns else 'Adj Close'
                tmp = tmp[[col]].rename(columns={col: name})
                df_list.append(tmp)
                source_info[name] = f"{source} [{ticker}]"
        except: pass

    # (2) Monthly 지표
    for ticker, (name, source) in fred_symbols.items():
        try:
            tmp = fdr.DataReader(ticker, start_date, end_date)
            if not tmp.empty:
                tmp.columns = [name]
                df_list.append(tmp)
                source_info[name] = f"{source} [{ticker}]"
        except: pass

    # -------------------------------------------------------
    # 3. 데이터 병합 및 정리
    # -------------------------------------------------------
    if df_list:
        result_df = pd.concat(df_list, axis=1).sort_index().ffill().tail(days)
        
        # 단위 보정
        if 'M2(조원)' in result_df.columns:
             result_df['M2(조원)'] = result_df['M2(조원)'] / 1000000000000
        if '수출(억불)' in result_df.columns:
             result_df['수출(억불)'] = result_df['수출(억불)'] / 100000000 

        return result_df.round(2), source_info
    else:
        return pd.DataFrame(), {}

# ==========================================
# 🧪 실행 테스트
# ==========================================
if __name__ == "__main__":
    df, sources = get_market_indicators(days=10)
    
    if not df.empty:
        print("\n✅ [한국 거시경제 현황판]")
        print("=" * 120)
        print(df)
        print("=" * 120)
        
        print("\n📝 [데이터 출처(Source) 및 티커]")
        for col, src in sources.items():
            print(f" • {col} : {src}")
        print("-" * 60)
    else:
        print("❌ 데이터를 가져오지 못했습니다.")