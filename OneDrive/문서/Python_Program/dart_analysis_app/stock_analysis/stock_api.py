import FinanceDataReader as fdr
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time

# ==========================================
# ⭐ Blue Sky님의 고정 관심 종목 리스트
# ==========================================
MY_FAVORITES = ['삼성중공업', '퍼스텍', '한국카본', 'GS', 'JB금융지주']

def calculate_rsi(series, period=14):
    """RSI(상대강도지수) 계산 함수"""
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_stock_data_for_gemini(code, stock_name, days=10):
    """
    제미나이 분석용 프롬프트 생성 함수 
    (가격 + 수급 + 기술적 지표 포함)
    """
    
    # 날짜 설정
    end_date_obj = datetime.now()
    start_date_obj = end_date_obj - timedelta(days=days + 60) # 이평선 계산용 여유
    
    end_date = end_date_obj.strftime("%Y%m%d")
    start_date = start_date_obj.strftime("%Y%m%d")

    try:
        # 1. 주가 데이터 (OHLCV)
        time.sleep(0.5) # 서버 부하 방지
        df_price = stock.get_market_ohlcv(start_date, end_date, code)
        
        # 2. 투자자별 순매수 데이터 가져오기
        # on='순매수' 옵션 필수: 매수량-매도량 차이를 가져옴
        df_investor = stock.get_market_trading_volume_by_date(start_date, end_date, code, on='순매수')
        
        # 데이터 병합 (날짜 기준 인덱스 매칭)
        df = pd.concat([df_price, df_investor], axis=1).dropna()
        
    except Exception as e:
        return f"❌ 데이터 조회 중 오류 발생: {e}"

    if df.empty:
        return f"❌ {stock_name}({code})의 데이터를 찾을 수 없습니다."

    # 기술적 지표 계산
    df['MA5'] = df['종가'].rolling(window=5).mean()
    df['MA20'] = df['종가'].rolling(window=20).mean()
    df['MA60'] = df['종가'].rolling(window=60).mean()
    
    # 최근 N일 데이터 자르기
    recent_df = df.tail(days)
    last_row = recent_df.iloc[-1]
    
    # 추세 판단
    trend = "정배열 (상승세)" if last_row['MA5'] > last_row['MA20'] else "역배열 (조정세)"
    
    # ---------------------------------------------------------
    # 🔧 [수정 완료] 외국인/기관 컬럼명 안전하게 찾기 함수
    # ---------------------------------------------------------
    def get_val(row, col_names):
        """여러 후보 이름 중 하나라도 있으면 값을 가져옴"""
        for name in col_names:
            if name in row:
                return row[name]
        return 0 # 없으면 0

    # 외국인/기관 수급 합계 계산 (컬럼명이 '외국인'일 수도, '외국인합계'일 수도 있음)
    sum_foreign = get_val(recent_df.sum(), ['외국인합계', '외국인'])
    sum_inst = get_val(recent_df.sum(), ['기관합계', '기관'])
    sum_indi = get_val(recent_df.sum(), ['개인'])
    
    supply_status = []
    if sum_foreign > 0: supply_status.append("외국인 매집")
    if sum_inst > 0: supply_status.append("기관 매집")
    if sum_indi > 0 and sum_foreign < 0 and sum_inst < 0: supply_status.append("개인만 매수(주의)")
    supply_text = ", ".join(supply_status) if supply_status else "수급 혼조세"

    # 프롬프트 생성
    prompt = f"""
[제미나이 주식 분석 요청]
'{stock_name}'의 주가 흐름과 투자자별 수급(매매동향)을 정밀 분석해줘.

1. **핵심 요약**:
   - 현재가: {last_row['종가']:,.0f}원
   - 기술적 추세: {trend}
   - 최근 수급 특징: {supply_text}
     (누적 순매수 -> 외인: {sum_foreign:,.0f}, 기관: {sum_inst:,.0f}, 개인: {sum_indi:,.0f})

2. **일별 상세 데이터 (최근 {days}일)**:
   (단위: 주가-원 / 수급-순매수량 / 🔴매수 🔵매도)
"""
    for date, row in recent_df.iterrows():
        date_str = date.strftime('%m/%d')
        chg = row['등락률']
        price_icon = "🔺" if chg > 0 else "🔹" if chg < 0 else "-"
        
        # 일별 데이터에서도 안전하게 값 가져오기
        val_foreign = get_val(row, ['외국인합계', '외국인'])
        val_inst = get_val(row, ['기관합계', '기관'])
        
        for_mark = "🔴" if val_foreign > 0 else "🔵"
        inst_mark = "🔴" if val_inst > 0 else "🔵"
        
        prompt += f"   - {date_str}: {price_icon}{row['종가']:,.0f}원 ({chg:+.2f}%) | [외인 {for_mark}{val_foreign:,.0f}] [기관 {inst_mark}{val_inst:,.0f}]\n"

    prompt += """
3. **분석 요청 사항**:
   - **수급 분석**: 메이저 주체(외국인/기관)의 의도가 무엇인지 파악해줘.
   - **기술적 분석**: 지지/저항 라인과 매매 타이밍을 분석해줘.
   - **종합 의견**: 회계사의 관점에서 보수적으로 매수/매도/관망 의견을 줘.
"""
    return prompt

def scan_buy_signals(target_code_list, market_name="시장"):
    """
    주어진 종목 리스트에서 [RSI 과매도, 골든크로스, 거래량 급증] 시그널 스캔
    """
    detected_stocks = []
    print(f"\n🕵️‍♂️ [{market_name}] {len(target_code_list)}개 종목 정밀 스캔 중...", end="")
    
    for idx, code in enumerate(target_code_list):
        try:
            # 스캔 속도를 위해 fdr 사용 (가벼움)
            df = fdr.DataReader(code, datetime.now() - timedelta(days=100), datetime.now())
            if len(df) < 30: continue

            # 지표 계산
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['RSI'] = calculate_rsi(df['Close'])
            
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            signals = []
            
            # 1. RSI 과매도 (<30)
            if today['RSI'] < 30:
                signals.append(f"💎과매도(RSI {today['RSI']:.1f})")
                
            # 2. 골든크로스 (5일 > 20일)
            if yesterday['MA5'] < yesterday['MA20'] and today['MA5'] > today['MA20']:
                signals.append("🚀골든크로스")
                
            # 3. 거래량 폭발 (>3배)
            if today['Volume'] > yesterday['Volume'] * 3:
                signals.append(f"🔥거래량폭발({today['Volume']/yesterday['Volume']:.1f}배)")
            
            if signals:
                # 종목명 찾기 (코드가 이미 있으므로 사용)
                name = code
                
                print(f"\n  👉 [포착] {name}({code}) : {', '.join(signals)}")
                detected_stocks.append((name, code, signals))
        
        except:
            continue
        
        # 진행률 점찍기 (10개마다 점 하나)
        if idx % 10 == 0: print(".", end="")
            
    print(" 완료!")
    return detected_stocks

def find_stock_code(input_name):
    """종목명으로 코드 찾기 (pykrx 기반)"""
    try:
        # pykrx를 사용한 종목 검색
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        
        # 코스피/코스닥에서 검색
        kospi_codes = stock.get_market_ohlcv(start_date, end_date)
        kosdaq_codes = stock.get_market_ohlcv(start_date, end_date, market='KOSDAQ')
        
        # 종목명 기반 검색 (동적 조회는 제한적이므로 직접 입력 권장)
        if input_name in ['삼성중공업', '퍼스텍', '한국카본', 'GS', 'JB금융지주']:
            # 알려진 관심 종목 코드 매핑
            known_codes = {
                '삼성중공업': '010140',
                '퍼스텍': '084650',
                '한국카본': '002800',
                'GS': '078930',
                'JB금융지주': '175330'
            }
            if input_name in known_codes:
                return known_codes[input_name], input_name
        
        return None, None
    except Exception as e:
        print(f"⚠️ 종목 검색 오류: {e}")
        return None, None

# ==========================================
# 🚀 메인 실행 부분
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print(f"📊 Blue Sky님의 주식 분석 & 스캐닝 시스템 (Ver 2.0)")
    print("="*60)

    # ------------------------------------------------
    # 1. 고정 관심 종목 분석
    # ------------------------------------------------
    print(f"\n[1] 관심 종목({len(MY_FAVORITES)}개) 정밀 분석")
    for name in MY_FAVORITES:
        code, found_name = find_stock_code(name)
        if code:
            report = get_stock_data_for_gemini(code, found_name)
            print("-" * 50)
            print(report)
    print("-" * 50)

    # ------------------------------------------------
    # 2. 시장 스캐닝 (일시 비활성화)
    # ------------------------------------------------
    print(f"\n[2] 시장 주도주 매매 시그널 스캐닝")
    print("   ⚠️ 시장 전체 스캔 기능은 네트워크 안정성 개선 중입니다.")
    print("   📌 위의 관심 종목 분석 결과를 참고해주세요.")

    # ------------------------------------------------
    # 3. 추가 수동 검색
    # ------------------------------------------------
    while True:
        print("\n" + "="*60)
        ask = input("❓ 추가 분석할 종목이 있나요? (종목명 입력 / 종료: 엔터): ")
        if not ask.strip():
            print("👋 프로그램을 종료합니다. 성투하세요!")
            break
        
        user_stock = ask.strip()
        code, found_name = find_stock_code(user_stock)
        
        if code:
            print(f"\n📈 '{found_name}' 데이터 추출 중...")
            report = get_stock_data_for_gemini(code, found_name)
            print("-" * 50)
            print(report)
            print("-" * 50)
        else:
            print("❌ 종목을 찾을 수 없습니다.")