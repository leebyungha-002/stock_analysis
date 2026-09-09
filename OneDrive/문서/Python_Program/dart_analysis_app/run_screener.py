# -*- coding: utf-8 -*-
"""
키움 주간 스크리닝 리포트 실행 & 텔레그램 전송
  python run_screener.py

매주 금요일 장 마감 후(16:30) 작업 스케줄러에서 실행되도록 설계됨.
(등록: setup_scheduler.bat)
"""
import sys
import os
import logging
from datetime import datetime

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_STOCK_DIR = os.path.join(_THIS_DIR, 'stock_analysis')
_LOG_DIR = os.path.join(_THIS_DIR, 'logs')
if _STOCK_DIR not in sys.path:
    sys.path.insert(0, _STOCK_DIR)
os.makedirs(_LOG_DIR, exist_ok=True)


def _setup_logging():
    log_path = os.path.join(_LOG_DIR, 'kiwoom_screener.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger('run_screener')


logger = _setup_logging()


def _fmt_price(value) -> str:
    try:
        return f'{value:,.0f}원'
    except (TypeError, ValueError):
        return '-'


def _strategy1_condition_text() -> str:
    import analyzer as a
    return (
        f" (거래대금 {a.SECTOR_VALUE_SURGE_RATIO}배↑, 상승일 {a.SURGE_MIN_CHANGE_PCT}%↑,"
        f" 거래량 {a.PULLBACK_VOLUME_DROP_RATIO*100:.0f}%↓, 이평선 근접 ±{a.PULLBACK_MA_TOLERANCE*100:.0f}%)"
    )


def _strategy2_condition_text() -> str:
    import analyzer as a
    return (
        f" (정배열 20>60>120일선, 이격도 ≤{a.ALIGNMENT_DISPARITY_MAX_PCT:.0f}%,"
        f" 외인매수 {a.ALIGNMENT_MIN_FOREIGN_BUY_DAYS}/10일↑, 20일선 이탈 ≤{a.ALIGNMENT_MAX_MA20_BREACH_DAYS}일)"
    )


def build_report(pullback_results: list, alignment_results: list, date_str: str) -> str:
    lines = [f'[📊 키움 주간 스크리닝 리포트 - {date_str}]']

    lines.append('\n[1. 주도 섹터 & 대장주 눌림목 발굴]' + _strategy1_condition_text())
    if pullback_results:
        for r in pullback_results:
            supply_text = '순매수 우위 유지' if r['supply_ok'] else '순매수 약화'
            lines.append(
                f" · {r['sector_name']}({r['market_name']}) | {r['stk_nm']}({r['stk_cd']})\n"
                f"   현재가 {_fmt_price(r['cur_prc'])} · 조정구간 거래량 {r['volume_drop_pct']:.1f}%↓"
                f" · 외인/기관 수급 {supply_text} · 지지선 {r['support_line']}"
            )
    else:
        lines.append(' · 조건을 만족하는 종목이 없습니다.')

    lines.append('\n[2. 정배열 초기 & 외인 집중 매집주]' + _strategy2_condition_text())
    if alignment_results:
        for r in alignment_results:
            wght_sign = '+' if r['wght_change'] >= 0 else ''
            lines.append(
                f" · {r['stk_nm']}({r['stk_cd']})\n"
                f"   현재가 {_fmt_price(r['cur_prc'])} · 20일선 이격도 {r['disparity_pct']:.1f}%"
                f" · 최근10일 외인매수 {r['foreign_buy_days']}일"
                f" · 외인지분율 변화 {wght_sign}{r['wght_change']:.2f}%p"
            )
    else:
        lines.append(' · 조건을 만족하는 종목이 없습니다.')

    return '\n'.join(lines)


def main():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    logger.info('=' * 60)
    logger.info('키움 주간 스크리닝 시작 - %s', now_str)
    logger.info('=' * 60)

    from telegram_notifier import send_message
    import kiwoom_api as kw

    if not kw.APP_KEY or not kw.APP_SECRET:
        msg = '⚠️ 키움 스크리너 실행 실패: .env에 KIWOOM_APP_KEY/KIWOOM_APP_SECRET이 설정되어 있지 않습니다.'
        logger.error(msg)
        send_message(msg)
        sys.exit(1)

    import analyzer

    pullback_results, alignment_results = [], []
    had_error = False

    try:
        logger.info('전략1(주도 섹터 & 눌림목) 실행 중...')
        pullback_results = analyzer.run_strategy_leading_sector_pullback()
        logger.info('전략1 완료: %d종목 발굴', len(pullback_results))
    except Exception:
        had_error = True
        logger.exception('전략1 실행 중 오류 발생')

    try:
        logger.info('전략2(정배열 & 외국인 매집) 실행 중...')
        alignment_results = analyzer.run_strategy_alignment_foreign_buy()
        logger.info('전략2 완료: %d종목 발굴', len(alignment_results))
    except Exception:
        had_error = True
        logger.exception('전략2 실행 중 오류 발생')

    report = build_report(pullback_results, alignment_results, datetime.now().strftime('%Y-%m-%d'))
    if had_error:
        report += '\n\n⚠️ 일부 전략 실행 중 오류가 발생했습니다. 로그(logs/kiwoom_screener.log)를 확인하세요.'

    logger.info('텔레그램 전송 중...')
    ok = send_message(report)
    if ok:
        logger.info('텔레그램 전송 완료')
    else:
        logger.error('텔레그램 전송 실패')

    logger.info('=' * 60)
    logger.info('키움 주간 스크리닝 완료')
    logger.info('=' * 60)

    if had_error or not ok:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logger.exception('키움 스크리너 실행 중 예상치 못한 오류로 중단됨')
        try:
            sys.path.insert(0, os.path.join(_THIS_DIR, 'stock_analysis'))
            from telegram_notifier import send_message
            send_message(f'🚨 키움 주간 스크리너 실행 실패\n{datetime.now().strftime("%Y-%m-%d %H:%M")}\n오류: {exc}')
        except Exception:
            logger.exception('오류 알림 텔레그램 전송마저 실패')
        sys.exit(1)
