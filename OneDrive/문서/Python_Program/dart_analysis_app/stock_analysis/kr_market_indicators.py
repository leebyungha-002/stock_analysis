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
    코스피/코스닥 지수 정보 포함
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
    market_indices = {} # 한국 시장 지수 정보 (코스피/코스닥)

    print(f"🔄 한국 경제 지표 수집 및 정렬 중 (최근 {days}일)...")
    
    # -------------------------------------------------------
    # 2. 한국 시장 지수 수집 (코스피/코스닥)
    # -------------------------------------------------------
    index_symbols = {
        'KS11': '코스피',
        'KQ11': '코스닥'
    }
    
    for ticker, index_name in index_symbols.items():
        try:
            # 최근 2일 데이터 가져오기 (전일 대비 계산용)
            tmp = fdr.DataReader(ticker, end_date - timedelta(days=5), end_date)
            if not tmp.empty and len(tmp) >= 2:
                # 최신 데이터 (오늘)
                latest = tmp.iloc[-1]
                # 전일 데이터
                prev = tmp.iloc[-2]
                
                current_price = latest['Close'] if 'Close' in latest else latest['Adj Close']
                prev_price = prev['Close'] if 'Close' in prev else prev['Adj Close']
                
                # 등락폭과 등락률 계산
                change = current_price - prev_price
                pct_change = (change / prev_price) * 100 if prev_price != 0 else 0
                
                market_indices[index_name] = {
                    'current': current_price,
                    'change': change,
                    'pct_change': pct_change
                }
                source_info[index_name] = f"FinanceDataReader [{ticker}]"
        except Exception as e:
            print(f"⚠️ {index_name} 지수 수집 중 오류: {e}")
            pass
    
    # -------------------------------------------------------
    # 3. 데이터 수집 로직
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
    # 4. 데이터 병합 및 정리
    # -------------------------------------------------------
    if df_list:
        result_df = pd.concat(df_list, axis=1).sort_index().ffill().tail(days)
        
        # 단위 보정
        if 'M2(조원)' in result_df.columns:
             result_df['M2(조원)'] = result_df['M2(조원)'] / 1000000000000
        if '수출(억불)' in result_df.columns:
             result_df['수출(억불)'] = result_df['수출(억불)'] / 100000000 

        return result_df.round(2), source_info, market_indices
    else:
        return pd.DataFrame(), {}, market_indices

# ==========================================
# 🧪 실행 테스트
# ==========================================
if __name__ == "__main__":
    df, sources, market_indices = get_market_indicators(days=10)
    
    if not df.empty or market_indices:
        print("\n✅ [1. 거시경제 지표]")
        print("=" * 120)
        
        # 한국 시장 지수 출력 (가장 위에 배치)
        if market_indices:
            print("\n📈 [한국 시장 지수]")
            for index_name, data in market_indices.items():
                current = data['current']
                change = data['change']
                pct_change = data['pct_change']
                
                # 상승/하락 이모지 결정
                icon = "🔺" if change > 0 else "🔹" if change < 0 else "➖"
                
                # 등락폭 부호 표시
                change_sign = "+" if change > 0 else ""
                pct_sign = "+" if pct_change > 0 else ""
                
                print(f"   - {index_name} 지수: {current:,.2f} ({icon} {change_sign}{change:.2f} / {pct_sign}{pct_change:.2f}%)")
            print("-" * 120)
        
        # 기존 거시경제 지표 출력
        if not df.empty:
            print("\n📊 [기타 거시경제 지표]")
            print(df)
            print("=" * 120)
        
        print("\n📝 [데이터 출처(Source) 및 티커]")
        for col, src in sources.items():
            print(f" • {col} : {src}")
        print("-" * 60)
    else:
        print("❌ 데이터를 가져오지 못했습니다.")