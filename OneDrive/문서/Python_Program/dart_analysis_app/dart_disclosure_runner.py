# -*- coding: utf-8 -*-
"""
DART 전자공시 주간 수집 스크립트
  python dart_disclosure_runner.py        → 지난 7일치 공시 수집 + 텔레그램 전송
  python dart_disclosure_runner.py --test → 텔레그램 연결만 확인
매주 월요일 오전 9시 자동 실행 (Windows 작업 스케줄러)
"""
import sys
import os
import time
from datetime import datetime, timedelta

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_STOCK_DIR = os.path.join(_THIS_DIR, 'stock_analysis')
if _STOCK_DIR not in sys.path:
    sys.path.insert(0, _STOCK_DIR)

import OpenDartReader
from telegram_notifier import send_message, send_document
from kr_stock_api import MY_FAVORITES


def _load_env():
    env_path = os.path.join(_THIS_DIR, '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

_load_env()

# MY_FAVORITES 종목명과 DART 등록명이 다른 경우 매핑
DART_NAME_MAP = {
    '비에치아이': '비에이치아이',
}


def build_disclosure_report(days: int = 7) -> str:
    dart_api_key = os.environ.get('DART_API_KEY', '')
    if not dart_api_key or dart_api_key == '여기에_DART_API키_입력':
        return "⚠️ .env 파일에 DART_API_KEY를 설정하세요.\nhttps://opendart.fss.or.kr 에서 발급 가능합니다."

    dart = OpenDartReader(dart_api_key)

    end_dt    = datetime.now()
    start_dt  = end_dt - timedelta(days=days)
    start_str = start_dt.strftime('%Y%m%d')
    end_str   = end_dt.strftime('%Y%m%d')

    lines = [
        "📋 전자공시 주간 리포트",
        f"기간: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}",
        f"대상: {len(MY_FAVORITES)}개 관심종목",
        "=" * 50,
    ]

    total_count  = 0
    no_disc_list = []

    for name in MY_FAVORITES:
        dart_name = DART_NAME_MAP.get(name, name)
        for attempt in range(2):
            try:
                corp_code = dart.find_corp_code(dart_name)
                if not corp_code:
                    lines.append(f"\n▪ {name}: DART 코드 없음 (종목명 확인 필요)")
                    break

                df = dart.list(corp_code, start=start_str, end=end_str, final=True)
                if df is None or df.empty:
                    no_disc_list.append(name)
                    break

                lines.append(f"\n▪ {name}  ({len(df)}건)")
                for _, row in df.iterrows():
                    rcept_dt  = str(row.get('rcept_dt', ''))
                    if len(rcept_dt) == 8:
                        rcept_dt = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"
                    report_nm = str(row.get('report_nm', '')).strip()
                    flr_nm    = str(row.get('flr_nm', ''))
                    lines.append(f"  [{rcept_dt}] {report_nm}  (제출: {flr_nm})")
                    total_count += 1
                break

            except Exception as e:
                if attempt == 0:
                    time.sleep(2)
                    continue
                lines.append(f"\n▪ {name}: 조회 오류 ({str(e)[:60]})")

    if no_disc_list:
        lines.append(f"\n[ 공시 없음 ] {', '.join(no_disc_list)}")

    lines.append(f"\n{'='*50}")
    lines.append(f"총 {total_count}건 공시 수집 완료")
    return "\n".join(lines)


def main():
    test_mode = '--test' in sys.argv
    now_str   = datetime.now().strftime('%Y-%m-%d %H:%M')

    print(f"\n{'='*60}")
    print(f"📋 전자공시 주간 수집 - {now_str}")
    print(f"{'='*60}")

    if test_mode:
        print("\n[테스트 모드] 텔레그램 연결만 확인합니다.")
        ok = send_message(f"✅ DART 공시 수집기 연결 테스트 성공!\n{now_str}")
        print("✅ 연결 성공!" if ok else "❌ 연결 실패 - .env 파일을 확인하세요.")
        return

    print("\n공시 수집 중... (잠시 소요)")
    report = build_disclosure_report(days=7)
    print(report)

    filename = f"dart_disclosure_{datetime.now().strftime('%Y%m%d')}.txt"
    caption  = f"📋 전자공시 주간 리포트 ({now_str})"

    print("\n📨 텔레그램 파일 전송 중...")
    ok = send_document(report, filename=filename, caption=caption)
    print("✅ 전송 완료!" if ok else "⚠️  전송 실패.")

    print(f"\n{'='*60}")
    print("✅ 완료!")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
