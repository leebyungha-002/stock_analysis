# -*- coding: utf-8 -*-
"""KRX 공식 API를 통한 투자자별 수급 데이터 조회 테스트"""
import requests
import json
from datetime import datetime, timedelta
import pandas as pd

code = '010140'
end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

print("=" * 70)
print("KRX 공식 API 테스트")
print("=" * 70)

# 1. KRX 정보데이터시스템 (IMD) API - 투자자별 거래량
print("\n[1] KRX IMD API - 투자자별 거래량")
print("-" * 70)

# IMD API URL
imd_url = "https://data.krx.co.kr/comm/functional/CmmEasySearchInfoSrch.Read"

# 파라미터 설정
params = {
    'bld': 'dbms/MDC_PUB_TR',
    'dataSrch': '1',
    'searchType': '1',
    'mktId': 'STK',
    'trdDd': end_date,
    'isuCd': code.zfill(6),
    'isuCd2': '',
    'cboAttr': '',
    'pagePath': '/contents/MKD/04/0402/04020100/mkd04020100.jsp',
    'name': 'form',
    '_': str(int(datetime.now().timestamp() * 1000))
}

try:
    response = requests.get(imd_url, params=params, timeout=5)
    print(f"상태 코드: {response.status_code}")
    print(f"응답 크기: {len(response.text)} bytes")
    
    if response.status_code == 200 and response.text:
        print("응답 데이터 (처음 500자):")
        print(response.text[:500])
except Exception as e:
    print(f"오류: {e}")

# 2. KRX Open Market Data (OMD) API - 거래량 데이터
print("\n\n[2] KRX OMD API - 거래량 데이터")
print("-" * 70)

omd_url = "https://open.krx.co.kr/contents/OPT10004?code={code}&bdate={start}&edate={end}&json".format(
    code=code,
    start=start_date,
    end=end_date
)

try:
    response = requests.get(omd_url, timeout=5)
    print(f"상태 코드: {response.status_code}")
    print(f"응답 크기: {len(response.text)} bytes")
    
    if response.status_code == 200:
        print("응답 데이터 (처음 500자):")
        print(response.text[:500])
except Exception as e:
    print(f"오류: {e}")

# 3. KRX 주식시장 투자자별 거래량 (대시보드)
print("\n\n[3] KRX 투자자별 거래량 페이지")
print("-" * 70)

investor_url = "https://data.krx.co.kr/comm/functionalSearch/search.cmd"

params = {
    'bld': 'dbms/MDC_PUB_TR',
    'dataSrch': '1',
    'searchType': '1',
    'mktId': 'STK',
    'trdDd': end_date,
}

try:
    response = requests.get(investor_url, params=params, timeout=5)
    print(f"상태 코드: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ URL에 접근 가능합니다")
        print(f"응답 크기: {len(response.text)} bytes")
except Exception as e:
    print(f"오류: {e}")

# 4. 네이버 금융 JSON API 확인
print("\n\n[4] 네이버 금융 JSON API")
print("-" * 70)

naver_api_url = "https://finance.naver.com/item/sise_day.naver"
params = {
    'code': code,
    'page': 1
}

try:
    response = requests.get(naver_api_url, params=params, timeout=5)
    print(f"상태 코드: {response.status_code}")
    
    if response.status_code == 200:
        # 숨겨진 데이터 확인
        if 'investorBuy' in response.text or 'investorSell' in response.text:
            print("✅ JSON 데이터에 투자자 정보가 있습니다")
        else:
            print("❌ 현재 페이지에는 투자자 정보가 없습니다")
except Exception as e:
    print(f"오류: {e}")

print("\n" + "=" * 70)
print("참고: 공식 KRX API는 주로 XML/JSON 형식으로 데이터를 반환합니다.")
print("=" * 70)
