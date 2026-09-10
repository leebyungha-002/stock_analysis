# -*- coding: utf-8 -*-
"""
네이버 금융 리포트 PDF 다운로드.
1) 보유 종목 리포트 (company_list)  2) 산업분석 리포트 (industry_list)
라이브러리: requests, BeautifulSoup, os, re
"""

import os
import re
import datetime
import requests
from bs4 import BeautifulSoup

# 이보다 오래된 리포트는 다운로드하지 않음
MAX_REPORT_AGE_DAYS = 90


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def _sanitize_filename(s):
    """윈도우 파일명에 쓸 수 없는 특수문자 제거: < > : " / \\ | ? *"""
    if not s or not isinstance(s, str):
        return ""
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:200]


def _ensure_dir(path):
    if not path:
        return
    os.makedirs(path, exist_ok=True)


def _default_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": "https://finance.naver.com/",
    }


def _get_pdf_url_from_row(cols):
    """행의 td 중 'file' 클래스가 있는 셀에서 .pdf로 끝나는 href 추출."""
    for td in cols:
        if not td.get("class") or "file" not in " ".join(td.get("class", [])):
            continue
        for a in td.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if href.lower().endswith(".pdf"):
                if href.startswith("//"):
                    return "https:" + href
                if href.startswith("/"):
                    return "https://finance.naver.com" + href
                if href.startswith("http"):
                    return href
                return "https://finance.naver.com/" + href.lstrip("/")
    return None


def _normalize_date(date_str):
    """날짜 문자열을 8자리 숫자로 정규화 (예: 2024.01.15 -> 20240115)."""
    cleaned = re.sub(r"[.\s\-/]", "", date_str)[:8]
    return cleaned if cleaned and re.match(r"^\d{6,8}$", cleaned) else "00000000"


def _parse_report_date(date_str):
    """'26.09.10'(YY.MM.DD) 형식의 날짜 문자열을 date 객체로 변환. 실패 시 None."""
    cleaned = re.sub(r"[.\s\-/]", "", date_str or "")
    try:
        if re.match(r"^\d{6}$", cleaned):
            yy, mm, dd = int(cleaned[:2]), int(cleaned[2:4]), int(cleaned[4:6])
            return datetime.date(2000 + yy, mm, dd)
        if re.match(r"^\d{8}$", cleaned):
            return datetime.date(int(cleaned[:4]), int(cleaned[4:6]), int(cleaned[6:8]))
    except ValueError:
        return None
    return None


def _is_too_old(date_str):
    """날짜를 확실히 파싱할 수 있고 MAX_REPORT_AGE_DAYS보다 오래됐으면 True.
    파싱 실패 시에는 걸러내지 않음(False) — 컬럼 오탐지로 전체가 스킵되는 것을 방지."""
    report_date = _parse_report_date(date_str)
    if report_date is None:
        return False
    return (datetime.date.today() - report_date).days > MAX_REPORT_AGE_DAYS


# ---------------------------------------------------------------------------
# 1. 보유 종목 리포트 (download_stock_reports)
# ---------------------------------------------------------------------------

def download_stock_reports(code_list, max_pages=1):
    """
    리스트에 있는 특정 종목(보유 종목)의 리포트 다운로드.

    - code_list: {종목코드: 종목명} 딕셔너리 (예: {'010140': '삼성중공업', '017960': '한국카본'})
    - max_pages: 종목당 수집할 최대 페이지 수 (기본 1)

    반환: (총 다운로드 수, 건너뜀/실패 수, 새로 저장된 파일 경로 리스트)
    """
    if not code_list:
        print("  대상 종목이 없습니다.")
        return 0, 0, []

    root = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(root, "reports", "My_Portfolio")
    _ensure_dir(base_dir)

    headers = _default_headers()
    total_downloaded = 0
    total_skipped = 0
    saved_paths = []

    for code, stock_name in code_list.items():
        code = str(code).strip().zfill(6)
        stock_name_safe = _sanitize_filename(stock_name) or "unknown"
        save_dir = os.path.join(base_dir, stock_name_safe)
        _ensure_dir(save_dir)

        print(f"  [{stock_name} ({code})]")
        stock_downloaded = 0
        stock_skipped = 0

        for page in range(1, max_pages + 1):
            url = f"https://finance.naver.com/research/company_list.naver?keyword={code}&searchType=itemCode"
            if page > 1:
                url += f"&page={page}"

            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.encoding = "euc-kr"
            except Exception as e:
                print(f"    페이지 {page} 요청 실패: {e}")
                continue

            if resp.status_code != 200:
                print(f"    페이지 {page} HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", class_=re.compile(r"type_?1"))
            if not table:
                if page == 1:
                    print(f"    테이블을 찾을 수 없습니다.")
                continue

            # thead: 제목, 증권사, 작성일
            thead = table.find("thead")
            ths = thead.find_all("th") if thead else []
            col_title = col_broker = col_date = None
            for i, th in enumerate(ths):
                t = th.get_text(strip=True)
                if "제목" in t:
                    col_title = i
                elif "증권" in t or "기관" in t:
                    col_broker = i
                elif "날짜" in t or "일자" in t or "작성일" in t:
                    col_date = i

            col_title = col_title if col_title is not None else 0
            col_broker = col_broker if col_broker is not None else 1
            col_date = col_date if col_date is not None else 2

            tbody = table.find("tbody") or table
            for row in tbody.find_all("tr"):
                cols = row.find_all("td")
                if not cols or (len(cols) == 1 and cols[0].get("colspan")):
                    continue

                pdf_url = _get_pdf_url_from_row(cols)
                if not pdf_url:
                    total_skipped += 1
                    stock_skipped += 1
                    continue

                title = cols[col_title].get_text(strip=True) if col_title < len(cols) else ""
                broker = cols[col_broker].get_text(strip=True) if col_broker < len(cols) else ""
                date_str = cols[col_date].get_text(strip=True) if col_date < len(cols) else ""
                date_clean = _normalize_date(date_str)

                if _is_too_old(date_str):
                    total_skipped += 1
                    stock_skipped += 1
                    continue

                base_name = f"{date_clean}_{stock_name_safe}_{_sanitize_filename(broker)}_{_sanitize_filename(title)}".strip("_")
                if not base_name.endswith(".pdf"):
                    base_name += ".pdf"
                filepath = os.path.join(save_dir, base_name)

                # 이미 다운로드된 파일은 건너뜀 (중복 방지) — requests.get 수행 안 함
                if os.path.exists(filepath):
                    print(f"    [패스] 이미 존재함: {os.path.basename(filepath)}")
                    total_skipped += 1
                    stock_skipped += 1
                    continue

                # 동일 실행 내 중복 파일명 방지
                stem, ext = os.path.splitext(base_name)
                n = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(save_dir, f"{stem}_{n}{ext}")
                    n += 1

                try:
                    r_pdf = requests.get(pdf_url, headers=headers, timeout=15)
                    if r_pdf.status_code != 200:
                        total_skipped += 1
                        stock_skipped += 1
                        continue
                    with open(filepath, "wb") as f:
                        f.write(r_pdf.content)
                    total_downloaded += 1
                    stock_downloaded += 1
                    saved_paths.append(filepath)
                    print(f"    저장: {os.path.basename(filepath)}")
                except Exception as e:
                    print(f"    다운로드 실패 ({title[:20]}...): {e}")
                    total_skipped += 1
                    stock_skipped += 1

        if stock_downloaded or stock_skipped:
            print(f"    완료 (다운로드: {stock_downloaded}, 건너뜀/실패: {stock_skipped})")

    return total_downloaded, total_skipped, saved_paths


# ---------------------------------------------------------------------------
# 2. 산업/업종 리포트 (download_industry_reports)
# ---------------------------------------------------------------------------

def download_industry_reports(pages=3):
    """
    네이버 금융 '산업분석' 게시판의 최신 리포트 다운로드 (새 투자처 발굴용).

    - pages: 크롤링할 페이지 수 (기본 3)
    반환: (다운로드 수, 건너뜀/실패 수, 새로 저장된 파일 경로 리스트 — 분류 이동 전 경로)
    """
    root = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(root, "reports", "Industry_Analysis")
    _ensure_dir(save_dir)

    headers = _default_headers()
    downloaded = 0
    skipped = 0
    saved_paths = []

    for page in range(1, pages + 1):
        url = "https://finance.naver.com/research/industry_list.naver"
        if page > 1:
            url += f"?page={page}"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "euc-kr"
        except Exception as e:
            print(f"  산업분석 페이지 {page} 요청 실패: {e}")
            continue

        if resp.status_code != 200:
            print(f"  산업분석 페이지 {page} HTTP {resp.status_code}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_=re.compile(r"type_?1"))
        if not table:
            if page == 1:
                print("  산업분석 테이블을 찾을 수 없습니다.")
            continue

        # thead: 분류, 제목, 증권사, 작성일 등
        thead = table.find("thead")
        ths = thead.find_all("th") if thead else []
        col_category = col_title = col_broker = col_date = None
        for i, th in enumerate(ths):
            t = th.get_text(strip=True)
            if "분류" in t:
                col_category = i
            elif "제목" in t:
                col_title = i
            elif "증권" in t or "기관" in t:
                col_broker = i
            elif "날짜" in t or "일자" in t or "작성일" in t:
                col_date = i

        col_category = col_category if col_category is not None else 0
        col_title = col_title if col_title is not None else 1
        col_broker = col_broker if col_broker is not None else 2
        # 네이버 산업분석 표에는 <thead>가 없어 위 헤더 자동감지가 항상 실패함 -> 폴백 인덱스 사용.
        # 실제 열 순서: 분류(0) 제목(1) 증권사(2) 파일링크(3, 텍스트 없음) 날짜(4) 조회수(5)
        col_date = col_date if col_date is not None else 4

        tbody = table.find("tbody") or table
        for row in tbody.find_all("tr"):
            cols = row.find_all("td")
            if not cols or (len(cols) == 1 and cols[0].get("colspan")):
                continue

            pdf_url = _get_pdf_url_from_row(cols)
            if not pdf_url:
                skipped += 1
                continue

            category = cols[col_category].get_text(strip=True) if col_category < len(cols) else ""
            title = cols[col_title].get_text(strip=True) if col_title < len(cols) else ""
            date_str = cols[col_date].get_text(strip=True) if col_date < len(cols) else ""
            date_clean = _normalize_date(date_str)

            if _is_too_old(date_str):
                skipped += 1
                continue

            # 파일명: [날짜]_[분류]_[제목].pdf
            base_name = f"{date_clean}_{_sanitize_filename(category)}_{_sanitize_filename(title)}".strip("_")
            if not base_name.endswith(".pdf"):
                base_name += ".pdf"
            filepath = os.path.join(save_dir, base_name)

            # 이미 다운로드된 파일은 건너뜀 — requests.get 수행 안 함
            if os.path.exists(filepath):
                print(f"  [패스] 이미 존재함: {os.path.basename(filepath)}")
                skipped += 1
                continue

            stem, ext = os.path.splitext(base_name)
            n = 1
            while os.path.exists(filepath):
                filepath = os.path.join(save_dir, f"{stem}_{n}{ext}")
                n += 1

            try:
                r_pdf = requests.get(pdf_url, headers=headers, timeout=15)
                if r_pdf.status_code != 200:
                    skipped += 1
                    continue
                with open(filepath, "wb") as f:
                    f.write(r_pdf.content)
                downloaded += 1
                saved_paths.append(filepath)
                print(f"  저장: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"  다운로드 실패 ({title[:30]}...): {e}")
                skipped += 1

    return downloaded, skipped, saved_paths


# ---------------------------------------------------------------------------
# 3. 다운로드 파일 분류 정리 (organize_downloaded_files)
# ---------------------------------------------------------------------------

# 분류 키워드 맵: [지주회사], [화학], [바이오] 등 섹터별 상세 관리
KEYWORD_MAP = {
    "반도체_IT": ["반도체", "IT", "전기전자", "디스플레이", "AI", "하드웨어", "가전"],
    "2차전지": ["2차전지", "배터리", "양극재", "음극재"],  # 화학에서 분리
    "화학_에너지": ["화학", "정유", "에너지", "석유", "태양광", "풍력"],  # 화학 독립
    "바이오_헬스": ["바이오", "헬스케어", "제약", "의료기기", "신약"],  # 바이오 강화
    "금융_지주": ["지주", "홀딩스", "금융", "은행", "증권", "보험"],  # 지주회사 명시
    "자동차_운송": ["자동차", "운송", "모빌리티", "타이어", "항공"],
    "조선_기계_건설": ["조선", "기계", "건설", "방산", "우주", "로봇", "플랜트"],
    "소비재_플랫폼": ["유통", "화장품", "의류", "음식료", "엔터", "게임", "인터넷", "미디어"],
}


def _classify_filename(fname):
    """
    파일명(분류/제목 포함)을 KEYWORD_MAP 기준으로 폴더명 반환.
    - '지주' or '홀딩스' -> 무조건 금융_지주
    - '배터리' 등 -> 2차전지 (화학보다 우선)
    - '화학' -> 화학_에너지
    - 나머지 키워드 매칭 후 없으면 기타.
    """
    if not fname:
        return "기타"
    # 확장자 제거 후 검사 (공백/언더스코어로 이어져 있어도 매칭되도록)
    base = os.path.splitext(fname)[0].replace("_", " ").replace(".", " ")

    # 1) 지주/홀딩스 -> 무조건 금융_지주
    if "지주" in base or "홀딩스" in base:
        return "금융_지주"

    # 2) 2차전지 관련 (화학보다 우선 구분: 배터리 등)
    for kw in KEYWORD_MAP["2차전지"]:
        if kw in base:
            return "2차전지"

    # 3) 화학/에너지 -> 화학_에너지 (정유, 에너지, 석유, 태양광, 풍력 포함)
    for kw in KEYWORD_MAP["화학_에너지"]:
        if kw in base:
            return "화학_에너지"

    # 4) 나머지 키워드 맵 순서대로 매칭 (금융_지주는 이미 1에서 처리)
    for folder_name, keywords in KEYWORD_MAP.items():
        if folder_name in ("금융_지주", "2차전지", "화학_에너지"):
            continue
        for kw in keywords:
            if kw in base:
                return folder_name

    return "기타"


def organize_downloaded_files(target_dir=None, only_filenames=None):
    """
    Industry_Analysis 등에 쌓인 PDF를 섹터별 폴더로 분류 이동.
    - target_dir: 정리할 폴더 (기본: reports/Industry_Analysis)
    - only_filenames: 지정하면 이 파일명들만 처리 (None이면 폴더 내 전체 PDF 대상)
    - 반환: (이동한 파일 수, 폴더별 건수 딕셔너리, 이동된 최종 경로 리스트)
    """
    root = os.path.dirname(os.path.abspath(__file__))
    if target_dir is None:
        target_dir = os.path.join(root, "reports", "Industry_Analysis")

    if not os.path.isdir(target_dir):
        print(f"  대상 폴더가 없습니다: {target_dir}")
        return 0, {}, []

    moved = 0
    by_folder = {}
    moved_paths = []

    for fname in os.listdir(target_dir):
        if not fname.lower().endswith(".pdf"):
            continue
        if only_filenames is not None and fname not in only_filenames:
            continue
        src = os.path.join(target_dir, fname)
        if not os.path.isfile(src):
            continue

        folder_name = _classify_filename(fname)
        dest_dir = os.path.join(target_dir, folder_name)
        _ensure_dir(dest_dir)
        dest_path = os.path.join(dest_dir, fname)

        if os.path.abspath(src) == os.path.abspath(dest_path):
            moved_paths.append(dest_path)
            continue
        try:
            # 이미 해당 폴더에 동일 파일명이 있으면 덮어쓰기 (os.replace는 Windows에서도 기존 파일을 대체함)
            os.replace(src, dest_path)
            moved += 1
            by_folder[folder_name] = by_folder.get(folder_name, 0) + 1
            moved_paths.append(dest_path)
            print(f"  이동: {folder_name}/ {fname}")
        except OSError as e:
            print(f"  이동 실패 ({fname}): {e}")

    if by_folder:
        print(f"  분류 결과: {dict(sorted(by_folder.items()))}")
    return moved, by_folder, moved_paths


# ---------------------------------------------------------------------------
# 실행부
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== 1. 보유 종목 리포트 업데이트 ===")
    my_stocks = {"010140": "삼성중공업", "017960": "한국카본", "352820": "하이브"}
    d1, s1, portfolio_paths = download_stock_reports(my_stocks)
    print(f"  총 다운로드: {d1}건, 건너뜀/실패: {s1}건\n")

    print("=== 2. 유망 산업 리포트 탐색 (최신 5페이지) ===")
    d2, s2, industry_root_paths = download_industry_reports(pages=5)
    print(f"  총 다운로드: {d2}건, 건너뜀/실패: {s2}건\n")

    print("=== 3. 산업 리포트 분류 정리 (섹터별 폴더) ===")
    industry_fnames = {os.path.basename(p) for p in industry_root_paths}
    moved, by_folder, industry_moved_paths = organize_downloaded_files(only_filenames=industry_fnames)
    print(f"  이동: {moved}건\n")

    new_files = portfolio_paths + industry_moved_paths
    if new_files:
        try:
            import summarize_reports
            summarize_reports.summarize_and_notify(new_files)
        except Exception as e:
            print(f"  [요약/텔레그램 전송 실패] {e}")
    else:
        print("=== 4. 리포트 요약: 신규 다운로드 없음, 건너뜀 ===")
