# 증권사 리포트 크롤링 단독 테스트 (requests만 사용)
# 사용: python test_stock_reports.py
# 또는: python test_stock_reports.py 005930

import sys
import re

def main():
    try:
        import requests
    except ImportError:
        print("오류: requests가 없습니다. 설치: pip install requests")
        sys.exit(1)

    raw = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not raw or len(raw) != 6 or not raw.isdigit():
        code = "005930"
        if raw and raw != "005930":
            print("종목코드 6자리 아님, 기본값 005930 사용")
    else:
        code = raw
    url = f"https://finance.naver.com/item/coinfo.naver?code={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    print(f"요청 중: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.encoding = "euc-kr"
        text = r.text
    except Exception as e:
        print(f"요청 실패: {e}")
        sys.exit(1)

    # 목표주가/목표가 근처에서 숫자 추출
    reports = []
    for keyword in ("목표주가", "목표가", "매수"):
        idx = text.find(keyword)
        if idx == -1:
            continue
        segment = text[idx : idx + 300]
        for m in re.finditer(r"[\*<]?\s*(\d{1,3}(?:,\d{3})+)\s*[\*>]?", segment):
            cand = m.group(1).strip()
            if len(cand.replace(",", "")) >= 4:
                reports.append({"제목": "종합 컨센서스", "증권사": "-", "목표가": cand})
                break
        if reports:
            break

    if reports:
        print("성공:", reports)
    else:
        print("리포트 없음 (목표가를 찾지 못함). 한글 확인:", "목표주가" in text or "목표가" in text)

if __name__ == "__main__":
    main()
