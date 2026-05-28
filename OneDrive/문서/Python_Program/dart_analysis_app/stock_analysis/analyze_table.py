# -*- coding: utf-8 -*-
"""네이버 금융 테이블 구조 분석"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

code = '010140'

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--start-maximized')
chrome_options.add_argument('--disable-blink-features=AutomationControlled')
chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

try:
    url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page=1"
    print(f"페이지 로드: {url}")
    driver.get(url)
    
    time.sleep(2)
    
    # 테이블 찾기
    table = driver.find_element(By.CSS_SELECTOR, "table.type2")
    
    print("\n=" * 70)
    print("헤더 행:")
    print("=" * 70)
    
    # 헤더 행 출력
    header_row = table.find_element(By.TAG_NAME, "tr")
    headers = header_row.find_elements(By.TAG_NAME, "th")
    for i, header in enumerate(headers):
        print(f"[{i}] {header.text}")
    
    print("\n" + "=" * 70)
    print("첫 번째 데이터 행 상세:")
    print("=" * 70)
    
    rows = table.find_elements(By.TAG_NAME, "tr")
    # 헤더 제외 (rows[0], rows[1])
    first_data_row = rows[2]
    cols = first_data_row.find_elements(By.TAG_NAME, "td")
    
    for i, col in enumerate(cols):
        print(f"[{i}] {col.text}")
    
finally:
    driver.quit()
