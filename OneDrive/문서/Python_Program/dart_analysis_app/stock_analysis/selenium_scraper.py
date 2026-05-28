# -*- coding: utf-8 -*-
"""Selenium을 이용한 네이버 금융 투자자별 수급 데이터 추출"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from datetime import datetime
import time

def scrape_investor_data_with_selenium(code, start_date, end_date):
    """
    Selenium을 이용해 네이버 금융에서 투자자별 수급 데이터를 추출합니다.
    
    Args:
        code (str): 종목코드 (6자리)
        start_date (str): 시작일자 (YYYYMMDD)
        end_date (str): 종료일자 (YYYYMMDD)
    
    Returns:
        list: [{'날짜': '20260401', '외국인_매입': 100, ...}, ...]
    """
    
    code = str(code).strip().zfill(6)
    investor_data = []
    
    # Chrome 옵션 설정
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36')
    
    driver = None
    try:
        # ChromeDriver 설정
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # 네이버 금융 페이지 로드
        url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page=1"
        print(f"📲 페이지 로드: {url}")
        driver.get(url)
        
        # 페이지 로드 대기
        time.sleep(2)
        
        # JavaScript 실행하여 추가 데이터 로드
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        # 테이블 찾기 및 파싱
        try:
            # type2 테이블 찾기
            table = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.type2"))
            )
            
            print("✅ 테이블 발견! 데이터 추출 중...")
            
            # 모든 행 추출
            rows = table.find_elements(By.TAG_NAME, "tr")
            print(f"   총 {len(rows)}개 행 발견")
            
            # 데이터 행 처리 (헤더 제외)
            for row_idx, row in enumerate(rows[2:], start=2):
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cols) < 7:
                        continue
                    
                    # 날짜 추출
                    date_text = cols[0].text.strip()
                    if not date_text or '.' not in date_text:
                        continue
                    
                    # 날짜 형식 변환
                    date_obj = datetime.strptime(date_text, '%Y.%m.%d')
                    date_str_yyyymmdd = date_obj.strftime('%Y%m%d')
                    
                    # 외국인/기관 데이터 추출
                    # 네이버 금융 테이블 구조 확인 필요
                    try:
                        # 컬럼 인덱스는 실제 HTML 구조에 따라 조정 필요
                        foreign_text = cols[5].text.strip().replace(',', '').replace('-', '0')
                        inst_text = cols[6].text.strip().replace(',', '').replace('-', '0')
                        
                        foreign_val = int(float(foreign_text)) if foreign_text else 0
                        inst_val = int(float(inst_text)) if inst_text else 0
                        
                        investor_data.append({
                            '날짜': date_str_yyyymmdd,
                            '외국인_순매수': foreign_val,
                            '기관_순매수': inst_val,
                        })
                        
                        if len(investor_data) % 5 == 0:
                            print(f"   {len(investor_data)}개 행 처리 완료...")
                    
                    except (ValueError, IndexError) as e:
                        continue
                
                except Exception as row_err:
                    continue
            
            print(f"✅ {len(investor_data)}개 데이터 추출 완료")
            
        except Exception as table_err:
            print(f"⚠️ 테이블 파싱 오류: {table_err}")
    
    except Exception as e:
        print(f"❌ Selenium 오류: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            driver.quit()
            print("🔌 Selenium 종료")
    
    return investor_data


if __name__ == "__main__":
    from datetime import timedelta
    
    code = '010140'
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    
    print("=" * 70)
    print("Selenium 테스트: 네이버 금융 투자자별 수급 데이터 추출")
    print("=" * 70)
    
    data = scrape_investor_data_with_selenium(code, start_date, end_date)
    
    print("\n추출된 데이터:")
    for item in data[:5]:
        print(f"  {item}")
    
    if len(data) > 5:
        print(f"  ... 외 {len(data) - 5}개")
