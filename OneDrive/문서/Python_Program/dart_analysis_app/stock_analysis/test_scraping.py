# -*- coding: utf-8 -*-
"""웹 스크래핑 테스트"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime

code = '010140'  # 삼성중공업

url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page=1"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

print(f"URL: {url}")
print("=" * 60)

try:
    res = requests.get(url, headers=headers, timeout=5)
    res.encoding = 'euc-kr'
    
    print(f"상태 코드: {res.status_code}")
    print(f"응답 크기: {len(res.text)} bytes")
    print()
    
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # type2 테이블 찾기
        table = soup.find('table', {'class': 'type2'})
        
        if table:
            rows = table.find_all('tr')
            print(f"총 행 개수: {len(rows)}")
            print()
            
            # 헤더행 확인
            print("헤더행:")
            header_row = rows[0]  
            headers_cols = header_row.find_all('th')
            for i, col in enumerate(headers_cols):
                print(f"  [{i}] {col.get_text(strip=True)}")
            print()
            
            # 데이터행 확인 (3행만)
            for row_idx in range(2, min(5, len(rows))):
                row = rows[row_idx]
                cols = row.find_all('td')
                date_val = cols[0].get_text(strip=True) if cols else "No data"
                print(f"행 {row_idx} ({date_val}): {len(cols)}개 컬럼")
                for j, col in enumerate(cols[:14]):
                    text = col.get_text(strip=True)[:20]
                    print(f"  [{j}] {text}")
                print()
        else:
            print("type2 테이블을 찾을 수 없음")

except Exception as e:
    print(f"오류: {e}")
    import traceback
    traceback.print_exc()
