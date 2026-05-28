import sys
import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta

# Windows cp949 콘솔에서 이모지/한글 출력 오류 방지
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==========================================
# 📌 화면 출력 설정
# ==========================================
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.unicode.east_asian_width', True)

def get_us_market_indicators(days=365):
    """
    미국 시장 지표와 거시경제 지표를 가져오는 함수 (Source 정보 포함)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 100)
    
    # -------------------------------------------------------
    # 1. 수집 대상 및 출처 정의
    # -------------------------------------------------------
    # [Daily] Yahoo Finance
    daily_symbols = {
        'US10YT': ('미국채10년', 'Yahoo Finance (Bond)'),
        'US2YT': ('미국채2년', 'Yahoo Finance (Bond)'),
        'VIX': ('VIX(공포)', 'Yahoo Finance (CBOE)'),
        'DX-Y.NYB': ('달러인덱스', 'Yahoo Finance (ICE)'),
        'GC=F': ('금(Gold)', 'Yahoo Finance (COMEX)'),
        'HG=F': ('구리(Copper)', 'Yahoo Finance (COMEX)')
    }
    
    # [Monthly] FRED
    fred_symbols = {
        'FRED:CPIAUCSL': ('CPI(물가)', 'FRED (미국 노동통계국)'),
        'FRED:PCEPILFE': ('Core_PCE', 'FRED (미국 상무부)'),
        'FRED:UNRATE': ('실업률(%)', 'FRED (미국 노동통계국)'),
        'FRED:FEDFUNDS': ('기준금리(%)', 'FRED (연준 FOMC)'),
        'FRED:M2SL': ('M2(조달러)', 'FRED (연준)')
    }

    df_list = []
    source_info = {}

    print(f"🗽 미국 경제 지표 수집 중 (최근 {days}일)...")

    # -------------------------------------------------------
    # 2. 데이터 수집 로직
    # -------------------------------------------------------
    # (1) Daily
    for ticker, (name, source) in daily_symbols.items():
        try:
            tmp = fdr.DataReader(ticker, start_date, end_date)
            if not tmp.empty:
                col = 'Close' if 'Close' in tmp.columns else 'Adj Close'
                tmp = tmp[[col]].rename(columns={col: name})
                df_list.append(tmp)
                source_info[name] = f"{source} [{ticker}]"
        except: pass

    # (2) Monthly
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
        
        # M2 단위 조정
        if 'M2(조달러)' in result_df.columns:
             result_df['M2(조달러)'] = result_df['M2(조달러)'] / 1000
        
        # 금/구리 비율 계산 (Gold-to-Copper Ratio)
        # 이 비율은 경기 선행 지표로 활용됨: 상승 시 안전자산 선호 강화, 하락 시 실물 경기 회복 신호
        if '금(Gold)' in result_df.columns and '구리(Copper)' in result_df.columns:
            # 0으로 나누기 방지
            result_df['금/구리비율'] = result_df['금(Gold)'] / result_df['구리(Copper)'].replace(0, pd.NA)
            source_info['금/구리비율'] = "계산값 [금(Gold) / 구리(Copper)]"
             
        return result_df.round(2), source_info
    else:
        return pd.DataFrame(), {}

# ==========================================
# 🧪 실행 테스트
# ==========================================
if __name__ == "__main__":
    df, sources = get_us_market_indicators(days=10)
    
    if not df.empty:
        print("\n🇺🇸 [미국 거시경제 현황판]")
        print("=" * 120)
        print(df)
        print("=" * 120)
        
        # 장단기 금리차 계산
        if '미국채10년' in df.columns and '미국채2년' in df.columns:
            latest = df.iloc[-1]
            diff = latest['미국채10년'] - latest['미국채2년']
            print(f"📢 [Key Check] 장단기 금리차(10년-2년): {diff:.2f}%p")
        
        # 금/구리 비율 분석 및 시장 의미 설명
        if '금/구리비율' in df.columns:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            
            current_ratio = latest['금/구리비율']
            prev_ratio = prev['금/구리비율'] if len(df) >= 2 else current_ratio
            
            # 비율 변화 계산
            ratio_change = current_ratio - prev_ratio if pd.notna(prev_ratio) else 0
            
            print(f"\n📊 [금/구리 비율 분석]")
            print(f"   현재 비율: {current_ratio:.2f}")
            if len(df) >= 2 and pd.notna(prev_ratio):
                change_icon = "🔺" if ratio_change > 0 else "🔹" if ratio_change < 0 else "➖"
                change_sign = "+" if ratio_change > 0 else ""
                print(f"   전일 대비: {change_icon} {change_sign}{ratio_change:.2f}")
            
            print(f"\n💡 [시장 의미 분석]")
            # 금/구리 비율의 시장 의미 설명
            if ratio_change > 0:
                print("   → 비율 상승: 안전자산 선호 강화 및 경기 둔화 우려 (Defensive)")
                print("   → 금 가격이 구리 대비 상대적으로 강세 → 리스크 회피 심리 확산")
            elif ratio_change < 0:
                print("   → 비율 하락: 실물 경기 회복 및 위험자산 선호 강화 (Risk-on)")
                print("   → 구리 가격이 금 대비 상대적으로 강세 → 경기 회복 기대")
            else:
                print("   → 비율 유지: 시장 심리 중립적")
            
            print(f"\n   📌 참고: 금/구리 비율은 경기 선행 지표로 활용됩니다.")
            print(f"      - 금: 안전자산, 인플레이션 헤지, 불확실성 증가 시 선호")
            print(f"      - 구리: 실물 경기 지표, 건설/제조업 수요 반영")
            print(f"      - 비율 상승 = 경기 둔화 신호, 비율 하락 = 경기 회복 신호")
        
        print("\n📝 [데이터 출처(Source) 및 티커]")
        for col, src in sources.items():
            print(f" • {col} : {src}")
        print("-" * 60)
    else:
        print("❌ 데이터를 가져오지 못했습니다.")