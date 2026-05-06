# -*- coding: utf-8 -*-
"""
한국 주식 분석 & 스캐닝 (로컬 PC 실행용)
[필수 설치] 터미널에서 한 번에 설치:
  pip install finance-datareader pykrx pandas requests beautifulsoup4 openpyxl
"""
import sys
import os

# Windows/Mac 로컬 환경 한글 깨짐 방지 (콘솔 출력)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import FinanceDataReader as fdr
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time
import re
from bs4 import BeautifulSoup
# get_market_indicators는 __main__에서만 import (get_stock_reports 단독 테스트 시 오류 방지)

# ------------------------------------------------
# 증권사 리포트 크롤링 (속도 중시: timeout=3, 실패 시 조용히 패스)
# ------------------------------------------------
try:
    import requests
except ImportError:
    requests = None

# ==========================================
# ⭐ Blue Sky님의 고정 관심 종목 리스트
# ==========================================
MY_FAVORITES = ['삼성중공업', '퍼스텍', '한국카본', 'GS', 'JB금융지주', '에스티아이','두산테스나', '테스']

def get_stock_reports(code):
    """
    네이버 금융에서 리포트 및 컨센서스 목표가를 가져옵니다.
    (BeautifulSoup 사용으로 안정성 강화)
    """
    if not requests:
        return []

    code = str(code).strip().zfill(6)
    reports = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # 1. 컨센서스(평균 목표가) 먼저 확인 (가장 정확함)
    try:
        url_consensus = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url_consensus, headers=headers, timeout=3)
        res.encoding = 'euc-kr'  # 한글 깨짐 방지

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')

            # '투자의견 목표주가' 섹션 찾기
            analysis_div = soup.find('div', {'class': 'r_cop_anal'})
            if analysis_div:
                target_price_em = analysis_div.find('em', {'class': 'no_up'})
                if not target_price_em:
                    target_price_em = analysis_div.find('em', {'class': 'no_down'})

                if target_price_em:
                    price_text = target_price_em.get_text(strip=True)
                    reports.append({
                        "제목": "증권사 평균 컨센서스",
                        "증권사": "Market Consensus",
                        "목표가": price_text
                    })
    except Exception as e:
        print(f"⚠️ 컨센서스 조회 실패: {e}")

    # 2. 개별 리포트 목록 크롤링
    try:
        url_report = f"https://finance.naver.com/item/research.naver?code={code}"
        res = requests.get(url_report, headers=headers, timeout=3)
        res.encoding = 'euc-kr'

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')

            # 리포트 테이블 찾기 (class='type1')
            table = soup.find('table', {'class': 'type1'})
            if table:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        title_cell = cols[1].find('a')
                        if title_cell:
                            title = title_cell.get_text(strip=True)
                        else:
                            title = cols[1].get_text(strip=True)

                        broker = cols[2].get_text(strip=True)
                        target_price = "-"

                        # 제목에서 숫자(목표가) 추출 시도
                        possible_prices = re.findall(r'(\d{1,3}(?:,\d{3})*)', title)
                        if possible_prices:
                            candidates = [p for p in possible_prices if len(p.replace(',', '')) >= 4]
                            if candidates:
                                target_price = candidates[-1]

                        if title and broker and len(title) > 2:
                            reports.append({
                                "제목": title,
                                "증권사": broker,
                                "목표가": target_price
                            })

                    if len(reports) >= 4:
                        break
    except Exception as e:
        pass

    return reports[:3]

def _scrape_investor_data_from_naver(code, start_date, end_date):
    """
    네이버 금융에서 투자자별 수급 데이터를 시도합니다.
    주: 현재 네이버 금융의 HTML 구조상 직접적인 거래량 데이터는 제한적입니다.
    
    반환: [{'날짜': '20260401', '외국인_순매수': 100, ...}, ...]
    """
    if not requests:
        return []
    
    investor_data = []
    
    try:
        code = str(code).strip().zfill(6)
        url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page=1"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = 'euc-kr'
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table', {'class': 'type2'})
            
            if table:
                rows = table.find_all('tr')
                
                for row in rows[2:]:  # 헤더 제외
                    cols = row.find_all('td')
                    
                    if len(cols) < 7:
                        continue
                    
                    try:
                        date_str = cols[0].get_text(strip=True)
                        
                        # 날짜 형식 변환
                        if '.' in date_str:
                            date_obj = datetime.strptime(date_str, '%Y.%m.%d')
                            date_str_yyyymmdd = date_obj.strftime('%Y%m%d')
                        else:
                            continue
                        
                        # 주: 현재 페이지의 type2 테이블에는 투자자별 거래량이 표시되지 않음
                        # 대신 공시정보나 다른 API 활용이 필요함
                        # 임시로 0 값 반환 (추후 데이터 소스 추가 시 수정)
                        
                        investor_data.append({
                            '날짜': date_str_yyyymmdd,
                            '외국인_순매수': 0,
                            '기관_순매수': 0,
                            '개인_순매수': 0
                        })
                    except:
                        continue
    
    except Exception as e:
        pass
    
    return investor_data

def calculate_rsi(series, period=14):
    """RSI(상대강도지수) 계산 함수"""
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_5day_continuous_buying(series):
    """
    최근 5일 연속 순매수 여부 확인 (외국인/기관용)
    Returns: (is_5day_continuous, recent_5day_list)
    """
    if len(series) < 5:
        return False, []
    
    try:
        recent_5 = series.tail(5)
        # 5일치 값을 float로 변환
        recent_5_values = []
        for val in recent_5.values:
            try:
                recent_5_values.append(float(val))
            except:
                recent_5_values.append(0)
        
        # 최근 5일이 모두 양수(순매수)이고, 누적값이 양수인지 확인
        is_continuous = all(val > 0 for val in recent_5_values)
        total_5day = sum(recent_5_values)
        
        # 5일 연속 순매수 AND 누적값이 100 이상 (신뢰성 강화)
        is_5day_continuous = is_continuous and total_5day > 100
        
        return is_5day_continuous, recent_5_values
    except Exception as e:
        return False, []

def get_stock_data_for_gemini(code, stock_name, days=10):
    """
    제미나이 분석용 프롬프트 생성 함수 
    (가격 + 수급 + 기술적 지표 포함)
    """
    
    # 날짜 설정 (MA200 계산을 위해 최소 250거래일 이상 확보)
    end_date_obj = datetime.now()
    start_date_obj = end_date_obj - timedelta(days=days + 350)  # 이평선(특히 200일선) 계산용 여유
    
    end_date = end_date_obj.strftime("%Y%m%d")
    start_date = start_date_obj.strftime("%Y%m%d")

    try:
        # 1. 주가 데이터 (OHLCV)
        time.sleep(0.5) # 서버 부하 방지
        df_price = stock.get_market_ohlcv(start_date, end_date, code)
        
        # 2. 투자자별 수급 데이터 가져오기 (pykrx의 get_market_trading_volume_by_date 사용)
        try:
            df_investor = stock.get_market_trading_volume_by_date(start_date, end_date, code, on='순매수')

            if df_investor.empty:
                print(f"\n⚠️ 주의: {stock_name}({code})의 투자자별 수급 데이터가 비어 있습니다.")
                print("   (pykrx API 또는 KRX 데이터 서버 점검 중일 수 있습니다.)")
                df_investor = pd.DataFrame()
            else:
                # 인덱스를 날짜형으로 통일
                df_investor.index = pd.to_datetime(df_investor.index)
        except Exception as e:
            print(f"\n⚠️ {stock_name}({code}) 투자자 수급 조회 실패: {e}")
            df_investor = pd.DataFrame()
        
        # 데이터 병합 (날짜 기준 인덱스 매칭)
        # dropna(subset=['종가']): 가격 데이터가 있는 행은 보존 (수급 데이터 없어도 유지)
        if not df_investor.empty:
            df_price.index = pd.to_datetime(df_price.index)
            df = pd.concat([df_price, df_investor], axis=1).dropna(subset=['종가'])
        else:
            df = df_price.copy()
        
    except Exception as e:
        error_msg = f"❌ 데이터 조회 중 오류 발생: {e}"
        return error_msg, {'foreign_consecutive': 0, 'inst_consecutive': 0, 'foreign_accumulated': 0, 'inst_accumulated': 0, 'foreign_5day_continuous': False, 'inst_5day_continuous': False, 'anomalies': []}

    if df.empty:
        error_msg = f"❌ {stock_name}({code})의 데이터를 찾을 수 없습니다."
        return error_msg, {'foreign_consecutive': 0, 'inst_consecutive': 0, 'foreign_accumulated': 0, 'inst_accumulated': 0, 'foreign_5day_continuous': False, 'inst_5day_continuous': False, 'anomalies': []}

    # 기술적 지표 계산 (전체 df 기준, 200일 미만 상장 종목은 MA200 NaN)
    df['MA5'] = df['종가'].rolling(window=5).mean()
    df['MA20'] = df['종가'].rolling(window=20).mean()
    df['MA60'] = df['종가'].rolling(window=60).mean()
    df['MA200'] = df['종가'].rolling(window=200).mean()
    
    # 최근 N일 데이터 자르기
    recent_df = df.tail(days)
    last_row = recent_df.iloc[-1]
    
    # 디버그: 데이터 구조 확인 (첫 실행 시만)
    if False:  # 디버그 모드 (필요시 True로 변경)
        print(f"\n[DEBUG] {stock_name}({code}) 컬럼: {list(df.columns)}")
        print(f"[DEBUG] 최근 행: {recent_df.iloc[-1].to_dict()}")
    
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

    # 외국인/기관 수급 합계 계산 (pykrx 컬럼명 우선: 외국인합계, 기관합계)
    sum_foreign = get_val(recent_df.sum(), ['외국인합계', '외국인_순매수', '외국인', 'Foreign'])
    sum_inst = get_val(recent_df.sum(), ['기관합계', '기관_순매수', '기관', 'Institutional'])
    sum_indi = get_val(recent_df.sum(), ['개인', '개인_순매수', 'Individual'])
    
    # ==========================================
    # 📊 [신규] 연속 순매수 일수 계산 로직
    # ==========================================
    def calculate_consecutive_buy_days(series):
        """연속 순매수 일수 계산 (최근부터 역순으로 카운트, 정확성 개선)"""
        consecutive_days = 0
        # 최근 데이터부터 역순으로 확인
        if len(series) == 0:
            return 0
        
        for val in reversed(series.values):
            try:
                val_num = float(val)
                if val_num > 0:  # 순매수인 경우
                    consecutive_days += 1
                else:  # 순매도 또는 0인 경우 중단
                    break
            except:
                break
        return consecutive_days
    
    # 외국인/기관 컬럼명 찾기 (더 정확한 매칭)
    foreign_col = None
    inst_col = None
    for col in recent_df.columns:
        col_str = str(col).lower()
        # 외국인 컬럼 매칭 (순매수 포함)
        if '외국인' in col_str:
            foreign_col = col
            break
    
    for col in recent_df.columns:
        col_str = str(col).lower()
        # 기관 컬럼 매칭 (순매수 포함)
        if '기관' in col_str:
            inst_col = col
            break
    
    # 연속 순매수 일수 계산 및 초기화
    foreign_consecutive = 0
    inst_consecutive = 0
    foreign_5day_continuous = False
    inst_5day_continuous = False
    foreign_5day_values = []
    inst_5day_values = []
    
    try:
        if foreign_col and foreign_col in recent_df.columns:
            foreign_series = recent_df[foreign_col]
            foreign_consecutive = calculate_consecutive_buy_days(foreign_series)
            # 5일 연속 매수 여부 확인
            foreign_5day_continuous, foreign_5day_values = check_5day_continuous_buying(foreign_series)
    except Exception as e:
        pass
    
    try:
        if inst_col and inst_col in recent_df.columns:
            inst_series = recent_df[inst_col]
            inst_consecutive = calculate_consecutive_buy_days(inst_series)
            # 5일 연속 매수 여부 확인
            inst_5day_continuous, inst_5day_values = check_5day_continuous_buying(inst_series)
    except Exception as e:
        pass
    
    # 수급 특이사항 문자열 생성 (3일 이상 연속 매수 시 강조)
    supply_anomalies = []
    if foreign_consecutive >= 3:
        supply_anomalies.append(f"🔥외국인 {foreign_consecutive}일 연속 매집")
    if inst_consecutive >= 3:
        supply_anomalies.append(f"🔥기관 {inst_consecutive}일 연속 매집")
    
    # 5일 연속 매수 특이사항 강조
    if foreign_5day_continuous:
        supply_anomalies.append(f"⭐ 외국인 5일 연속 매집 (강력)")
    if inst_5day_continuous:
        supply_anomalies.append(f"⭐ 기관 5일 연속 매집 (강력)")
    
    supply_status = []
    if sum_foreign > 0: supply_status.append("외국인 매집")
    if sum_inst > 0: supply_status.append("기관 매집")
    if sum_indi > 0 and sum_foreign < 0 and sum_inst < 0: supply_status.append("개인만 매수(주의)")
    supply_text = ", ".join(supply_status) if supply_status else "수급 혼조세"
    
    # 수급 분석 결과 딕셔너리 (반환용)
    supply_analysis = {
        'foreign_consecutive': foreign_consecutive,
        'inst_consecutive': inst_consecutive,
        'foreign_accumulated': sum_foreign,
        'inst_accumulated': sum_inst,
        'foreign_5day_continuous': foreign_5day_continuous,
        'inst_5day_continuous': inst_5day_continuous,
        'anomalies': supply_anomalies
    }

    # 증권사 리포트 크롤링 (get_stock_data_for_gemini 내부에서만 호출, 스캐닝에는 미사용)
    report_consensus_text = ""
    try:
        report_list = get_stock_reports(code)
        if report_list:
            lines = []
            for i, r in enumerate(report_list, 1):
                title = r.get("제목", "-") or "-"
                broker = r.get("증권사", "-") or "-"
                target = r.get("목표가", "-") or "-"
                lines.append(f"   {i}. [{broker}] {title} | 목표가: {target}")
            report_consensus_text = "\n   - **[최신 증권사 컨센서스]**\n" + "\n".join(lines)
        else:
            report_consensus_text = "\n   - **[최신 증권사 컨센서스]**: 리포트 정보 없음"
    except Exception:
        report_consensus_text = "\n   - **[최신 증권사 컨센서스]**: 리포트 정보 없음"

    # 프롬프트 생성
    # 수급 특이사항 문자열 생성
    anomaly_text = ""
    if supply_anomalies:
        anomaly_text = f"\n   - **[수급 특이사항]**: {', '.join(supply_anomalies)}"

    # 200일선 표기 (상장 200일 미만이면 NaN → '데이터 부족')
    ma200_val = last_row.get('MA200')
    ma200_str = f"{ma200_val:,.0f}원" if (ma200_val is not None and pd.notna(ma200_val)) else "데이터 부족"
    
    prompt = f"""
[제미나이 주식 분석 요청]
'{stock_name}'의 주가 흐름과 투자자별 수급(매매동향)을 정밀 분석해줘.

1. **핵심 요약**:
   - 현재가: {last_row['종가']:,.0f}원
   - 기술적 추세: {trend}
   - 200일 이동평균선: {ma200_str} (장기 추세 기준)
   - 최근 수급 특징: {supply_text}
     (누적 순매수 -> 외인: {sum_foreign:,.0f}, 기관: {sum_inst:,.0f}, 개인: {sum_indi:,.0f})
     (연속 매수 일수 -> 외인: {foreign_consecutive}일, 기관: {inst_consecutive}일){anomaly_text}
{report_consensus_text}

2. **일별 상세 데이터 (최근 {days}일)**:
   (단위: 주가-원 / 순매수-주)
"""
    for date, row in recent_df.iterrows():
        date_str = date.strftime('%m/%d')
        chg = row['등락률']
        price_icon = "🔺" if chg > 0 else "🔹" if chg < 0 else "-"

        # 거래량 추출
        vol = int(row['거래량']) if '거래량' in row.index and pd.notna(row.get('거래량')) else 0

        # 순매수 데이터 추출
        val_foreign_net = get_val(row, ['외국인합계', '외국인_순매수', '외국인'])
        val_inst_net = get_val(row, ['기관합계', '기관_순매수', '기관'])

        # 순매수/순매도 마크 (양수=매집, 음수=매도)
        for_mark = "🔴" if val_foreign_net > 0 else "🔵" if val_foreign_net < 0 else "➖"
        inst_mark = "🔴" if val_inst_net > 0 else "🔵" if val_inst_net < 0 else "➖"

        prompt += f"   - {date_str}: {price_icon}{row['종가']:,.0f}원 ({chg:+.2f}%) 거래량:{vol:,.0f} | [외인 {for_mark}{val_foreign_net:+,.0f}] [기관 {inst_mark}{val_inst_net:+,.0f}]\n"

    prompt += """
3. **분석 요청 사항**:
   - **수급 분석**: 메이저 주체(외국인/기관)의 의도가 무엇인지 파악해줘.
   - **기술적 분석**: 20일선·200일선 대비 위치(지지/저항)와 매매 타이밍을 분석해줘.
   - **종합 의견**: 회계사의 관점에서 보수적으로 매수/매도/관망 의견을 줘.
"""
    return prompt, supply_analysis

def scan_buy_signals(target_code_list, market_name="시장"):
    """
    주어진 종목 리스트에서 [RSI 과매도, 골든크로스, 거래량 급증] 시그널 스캔
    """
    detected_stocks = []
    print(f"\n🕵️‍♂️ [{market_name}] {len(target_code_list)}개 종목 정밀 스캔 중...", end="")
    
    for idx, code in enumerate(target_code_list):
        try:
            # 스캔 속도를 위해 fdr 사용 (가벼움)
            time.sleep(0.2)  # 서버 부하 방지
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
                # 종목명 찾기
                try:
                    name_row = fdr.StockListing('KRX')
                    name = name_row[name_row['Code'] == code]['Name'].values[0]
                except:
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
    """종목명으로 코드 찾기 (관심 종목 딕셔너리 기반)"""
    # MY_FAVORITES 종목의 코드 매핑 (pykrx 기반, fdr 제거)
    known_codes = {
        '삼성중공업': '010140',
        '퍼스텍': '010820',
        '한국카본': '017960',
        'GS': '078930',
        'JB금융지주': '175330',
        '에스티아이': '039440',
        '두산테스나': '131970',
        '테스': '095610'
    }
    
    if input_name in known_codes:
        return known_codes[input_name], input_name
    else:
        return None, None

# ==========================================
# 💾 파일 저장 관련 함수
# ==========================================

def create_daily_reports_folder():
    """daily_reports 폴더 생성 (없으면 생성, 있으면 패스)"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(current_dir, 'daily_reports')
    
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
    
    return reports_dir

def save_analysis_results(excel_data, text_content, date_str, reports_dir):
    """
    분석 결과를 3개 파일로 저장
    1. 엑셀 파일 (.xlsx): 수급 데이터 표
    2. 텍스트 파일 (.txt): 제미나이 프롬프트 내용
    3. 마크다운 파일 (.md): 제미나이 답변용 빈 파일
    """
    try:
        # 1. 엑셀 파일 저장
        excel_path = os.path.join(reports_dir, f'kr_stock_data_{date_str}.xlsx')
        excel_data.to_excel(excel_path, index=False, engine='openpyxl')
        
        # 2. 텍스트 파일 저장
        txt_path = os.path.join(reports_dir, f'kr_stock_summary_{date_str}.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        # 3. 마크다운 파일 생성 (빈 파일)
        md_path = os.path.join(reports_dir, f'Gemini_Insight_{date_str}.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# 제미나이 분석 결과 - {date_str}\n\n")
            f.write("(제미나이의 답변을 여기에 붙여넣으세요)\n")
        
        return True
    except Exception as e:
        print(f"❌ 파일 저장 중 오류 발생: {e}")
        return False

# ==========================================
# 🚀 메인 실행 부분
# ==========================================
if __name__ == "__main__":
    from kr_market_indicators import get_market_indicators

    print("\n" + "="*60)
    print(f"📊 Blue Sky님의 주식 분석 & 스캐닝 시스템 (Ver 2.0)")
    print("="*60)

    # ------------------------------------------------
    # 0. 거시경제 지표 수집 (코스피/코스닥 포함)
    # ------------------------------------------------
    market_indices_text = ""  # 파일 저장용
    try:
        df_indicators, sources, market_indices = get_market_indicators(days=10)
        
        if market_indices or not df_indicators.empty:
            print("\n✅ [1. 거시경제 지표]")
            print("=" * 60)
            
            # 파일 저장용 텍스트 생성
            market_indices_text = "\n✅ [1. 거시경제 지표]\n"
            market_indices_text += "=" * 60 + "\n"
            
            # 한국 시장 지수 출력 (가장 위에 배치)
            if market_indices:
                print("\n📈 [한국 시장 지수]")
                market_indices_text += "\n📈 [한국 시장 지수]\n"
                for index_name, data in market_indices.items():
                    current = data['current']
                    change = data['change']
                    pct_change = data['pct_change']
                    
                    # 상승/하락 이모지 결정
                    icon = "🔺" if change > 0 else "🔹" if change < 0 else "➖"
                    
                    # 등락폭 부호 표시
                    change_sign = "+" if change > 0 else ""
                    pct_sign = "+" if pct_change > 0 else ""
                    
                    line = f"   - {index_name} 지수: {current:,.2f} ({icon} {change_sign}{change:.2f} / {pct_sign}{pct_change:.2f}%)\n"
                    print(line.rstrip())
                    market_indices_text += line
                print("-" * 60)
                market_indices_text += "-" * 60 + "\n"
            
            # 기타 거시경제 지표 출력 (간략히)
            if not df_indicators.empty:
                print("\n📊 [기타 거시경제 지표]")
                market_indices_text += "\n📊 [기타 거시경제 지표]\n"
                # 최신 데이터만 출력
                latest_row = df_indicators.iloc[-1]
                for col in df_indicators.columns:
                    if col not in market_indices:  # 시장 지수는 이미 출력했으므로 제외
                        value = latest_row[col]
                        if pd.notna(value):
                            line = f"   - {col}: {value:,.2f}\n"
                            print(line.rstrip())
                            market_indices_text += line
                print("=" * 60)
                market_indices_text += "=" * 60 + "\n"
    except Exception as e:
        print(f"\n⚠️ 거시경제 지표 수집 중 오류 발생: {e}")
        print("=" * 60)
        market_indices_text = f"\n⚠️ 거시경제 지표 수집 중 오류 발생: {e}\n" + "=" * 60 + "\n"

    # ------------------------------------------------
    # 1. 고정 관심 종목 분석
    # ------------------------------------------------
    print(f"\n[1] 관심 종목({len(MY_FAVORITES)}개) 정밀 분석")
    
    # 수급 특이사항 종합 리스트
    all_supply_anomalies = []
    foreign_5day_stocks = []  # 외국인 5일 연속 매수 종목
    inst_5day_stocks = []     # 기관 5일 연속 매수 종목
    
    # 파일 저장을 위한 데이터 수집
    stock_data_list = []  # 엑셀 저장용 데이터
    all_reports_text = []  # 텍스트 파일 저장용 (모든 프롬프트 내용)
    
    for name in MY_FAVORITES:
        code, found_name = find_stock_code(name)
        if code:
            try:
                report, supply_analysis = get_stock_data_for_gemini(code, found_name)
                print("-" * 50)
                print(report)
                
                # 텍스트 파일 저장용 데이터 수집
                all_reports_text.append(report)
                all_reports_text.append("\n" + "="*60 + "\n")
                
                # 엑셀 저장용 데이터 수집
                if supply_analysis:
                    # 최근 데이터 가져오기 (현재가 등)
                    try:
                        end_date_obj = datetime.now()
                        start_date_obj = end_date_obj - timedelta(days=10 + 60)
                        end_date = end_date_obj.strftime("%Y%m%d")
                        start_date = start_date_obj.strftime("%Y%m%d")
                        
                        df_price = stock.get_market_ohlcv(start_date, end_date, code)
                        if not df_price.empty:
                            last_price = df_price.iloc[-1]['종가']
                            last_change = df_price.iloc[-1]['등락률']
                        else:
                            last_price = 0
                            last_change = 0
                    except:
                        last_price = 0
                        last_change = 0
                    
                    stock_data_list.append({
                        '종목명': found_name,
                        '종목코드': code,
                        '현재가(원)': last_price,
                        '등락률(%)': last_change,
                        '외국인_연속매수일': supply_analysis.get('foreign_consecutive', 0),
                        '기관_연속매수일': supply_analysis.get('inst_consecutive', 0),
                        '외국인_누적순매수': supply_analysis.get('foreign_accumulated', 0),
                        '기관_누적순매수': supply_analysis.get('inst_accumulated', 0),
                        '수급특이사항': ', '.join(supply_analysis.get('anomalies', [])) if supply_analysis.get('anomalies') else '-'
                    })
                
                # 5일 연속 매수 종목 수집
                if supply_analysis:
                    if supply_analysis.get('foreign_5day_continuous'):
                        foreign_5day_stocks.append((found_name, code, supply_analysis.get('foreign_accumulated', 0)))
                    if supply_analysis.get('inst_5day_continuous'):
                        inst_5day_stocks.append((found_name, code, supply_analysis.get('inst_accumulated', 0)))
                
                # 수급 특이사항이 있으면 리스트에 추가
                if supply_analysis and supply_analysis.get('anomalies'):
                    for anomaly in supply_analysis['anomalies']:
                        all_supply_anomalies.append(f"{found_name}: {anomaly}")
            except Exception as e:
                # 반환값이 1개인 경우 (에러 메시지)
                try:
                    if 'report' in locals() and isinstance(report, str):
                        print("-" * 50)
                        print(report)
                        all_reports_text.append(report)
                        all_reports_text.append("\n" + "="*60 + "\n")
                except:
                    print(f"❌ {name} 분석 중 오류: {e}")
    
    print("-" * 50)
    
    # 🌟 외국인/기관 5일 연속 매수 종목 강조 출력
    if foreign_5day_stocks or inst_5day_stocks:
        print("\n" + "="*60)
        print("🌟 [외국인/기관 5일 연속 매집 종목 - 강력 매집 신호]")
        print("="*60)
        
        if foreign_5day_stocks:
            print("\n📍 외국인 5일 연속 매집:")
            # 누적 순매수로 정렬 (내림차순)
            foreign_5day_stocks.sort(key=lambda x: x[2], reverse=True)
            for stock_name, code, accumulated in foreign_5day_stocks:
                print(f"   🔴 {stock_name}({code}) - 5일 누적 순매수: {accumulated:,.0f}주")
        
        if inst_5day_stocks:
            print("\n📍 기관 5일 연속 매집:")
            # 누적 순매수로 정렬 (내림차순)
            inst_5day_stocks.sort(key=lambda x: x[2], reverse=True)
            for stock_name, code, accumulated in inst_5day_stocks:
                print(f"   🔵 {stock_name}({code}) - 5일 누적 순매수: {accumulated:,.0f}주")
        
        print("="*60)
    
    # 수급 특이사항 종합 출력
    if all_supply_anomalies:
        print("\n" + "="*60)
        print("📊 [수급 특이사항 종합]")
        print("="*60)
        for anomaly in all_supply_anomalies:
            print(f"  • {anomaly}")
        print("="*60)
    
    # ------------------------------------------------
    # 💾 파일 저장 (관심 종목 분석 완료 후)
    # ------------------------------------------------
    if stock_data_list:
        try:
            # 날짜 문자열 생성
            date_str = datetime.now().strftime("%Y%m%d")
            
            # 폴더 생성
            reports_dir = create_daily_reports_folder()
            
            # 엑셀 데이터프레임 생성
            excel_df = pd.DataFrame(stock_data_list)
            
            # 텍스트 내용 생성 (거시경제 지표 + 모든 프롬프트 + 5일 연속 매수 + 수급 특이사항)
            text_content = market_indices_text + "\n"  # 거시경제 지표를 맨 위에 추가
            text_content += "\n".join(all_reports_text)
            
            # 5일 연속 매수 종목 추가
            if foreign_5day_stocks or inst_5day_stocks:
                text_content += "\n" + "="*60 + "\n"
                text_content += "🌟 [외국인/기관 5일 연속 매집 종목 - 강력 매집 신호]\n"
                text_content += "="*60 + "\n"
                
                if foreign_5day_stocks:
                    text_content += "\n📍 외국인 5일 연속 매집:\n"
                    for stock_name, code, accumulated in sorted(foreign_5day_stocks, key=lambda x: x[2], reverse=True):
                        text_content += f"   🔴 {stock_name}({code}) - 5일 누적 순매수: {accumulated:,.0f}주\n"
                
                if inst_5day_stocks:
                    text_content += "\n📍 기관 5일 연속 매집:\n"
                    for stock_name, code, accumulated in sorted(inst_5day_stocks, key=lambda x: x[2], reverse=True):
                        text_content += f"   🔵 {stock_name}({code}) - 5일 누적 순매수: {accumulated:,.0f}주\n"
                
                text_content += "="*60 + "\n"
            
            if all_supply_anomalies:
                text_content += "\n" + "="*60 + "\n"
                text_content += "📊 [수급 특이사항 종합]\n"
                text_content += "="*60 + "\n"
                for anomaly in all_supply_anomalies:
                    text_content += f"  • {anomaly}\n"
                text_content += "="*60 + "\n"
            
            # 파일 저장
            if save_analysis_results(excel_df, text_content, date_str, reports_dir):
                print(f"\n📂 결과 파일이 'daily_reports' 폴더에 저장되었습니다.")
                print(f"   - 엑셀 파일: kr_stock_data_{date_str}.xlsx")
                print(f"   - 텍스트 파일: kr_stock_summary_{date_str}.txt")
                print(f"   - 마크다운 파일: Gemini_Insight_{date_str}.md")
        except Exception as e:
            print(f"\n⚠️ 파일 저장 중 오류 발생: {e}")

    # ------------------------------------------------
    # 2. 시장 스캐닝 (현재 비활성화 - 안정성 개선 중)
    # ------------------------------------------------
    print(f"\n[2] 시장 주도주 매매 시그널 스캐닝")
    print("   ⚠️ 시장 전체 스캔 기능은 일시적으로 비활성화 중입니다.")
    print("   📌 위의 관심 종목 분석 결과를 참고해주세요.")

    # ------------------------------------------------
    # ✅ 분석 완료
    # ------------------------------------------------
    print("\n" + "="*60)
    print("✅ 모든 분석이 완료되었습니다!")
    print("👋 프로그램을 종료합니다. 성투하세요!")
    print("="*60)