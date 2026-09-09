# -*- coding: utf-8 -*-
"""
키움 주간 스크리너 분석 로직

[전략 1] 주도 섹터 순환매 및 대장주 눌림목 공략
[전략 2] 이평선 정배열 초기 + 외국인 연속 순매수 (중기 추세 추종)
"""
import logging
from datetime import datetime

import pandas as pd

import kiwoom_api as kw
from kiwoom_api import to_float, KiwoomAPIError

logger = logging.getLogger(__name__)

# ---- 전략 1 설정값 ----
TOP_N_SECTORS = 3                  # 시장별 주도 섹터 선정 개수
SECTOR_VALUE_SURGE_RATIO = 1.5     # 거래대금 급증 기준 (20일 평균 대비)
SECTOR_MA_WINDOW = 20
LEADER_CANDIDATES_PER_SECTOR = 5   # 섹터 내 대장주 후보 검토 개수 (거래대금 상위)
SURGE_MIN_CHANGE_PCT = 2.0         # "강한 상승일" 최소 등락률
PULLBACK_VOLUME_DROP_RATIO = 0.65  # 조정구간 거래량 <= 직전 상승일 대비 65%
PULLBACK_MA_TOLERANCE = 0.03       # 지지선 근접 허용 오차 (±3%)

# ---- 전략 2 설정값 ----
ALIGNMENT_STREAK_LOOKBACK = '10'       # ka10131 조회 기간 (최근 10일)
ALIGNMENT_MIN_FOREIGN_BUY_DAYS = 5     # 최근 10영업일 중 외국인 순매수 최소 일수
ALIGNMENT_MAX_CANDIDATES = 40          # 1차 후보 중 상세 검증할 최대 종목 수
ALIGNMENT_DISPARITY_MAX_PCT = 105.0    # 20일선 대비 이격도 상한
ALIGNMENT_MAX_MA20_BREACH_DAYS = 1     # 최근5일 중 20일선 이탈 허용 일수

MARKETS = [
    {'market_name': '코스피', 'inds_all_cd': '001', 'stock_mrkt_tp': '0', 'streak_mrkt_tp': '001'},
    {'market_name': '코스닥', 'inds_all_cd': '101', 'stock_mrkt_tp': '10', 'streak_mrkt_tp': '101'},
]


def _today_str() -> str:
    return datetime.now().strftime('%Y%m%d')


def _minmax(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if pd.isna(lo) or pd.isna(hi) or (hi - lo) < 1e-9:
        return series.map(lambda _: 0.5)
    return (series - lo) / (hi - lo)


def _ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _numeric_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    for col in ('cur_prc', 'trde_qty', 'trde_prica', 'open_pric', 'high_pric', 'low_pric'):
        if col in df.columns:
            df[col] = df[col].map(to_float).abs()
    return df


def _sector_daily_df(inds_cd: str, base_dt: str) -> pd.DataFrame:
    rows = kw.get_sector_daily_chart(inds_cd, base_dt)
    if not rows:
        return pd.DataFrame()
    df = _numeric_ohlcv(pd.DataFrame(rows))
    if 'dt' in df.columns:
        df = df.sort_values('dt').reset_index(drop=True)
    return df


def _stock_daily_df(stk_cd: str, base_dt: str) -> pd.DataFrame:
    rows = kw.get_stock_daily_chart(stk_cd, base_dt)
    if not rows:
        return pd.DataFrame()
    df = _numeric_ohlcv(pd.DataFrame(rows))
    if 'dt' in df.columns:
        df = df.sort_values('dt').reset_index(drop=True)
    return df


def _foreign_trend_df(stk_cd: str) -> pd.DataFrame:
    rows = kw.get_stock_foreign_trend(stk_cd)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ('close_pric', 'trde_qty', 'chg_qty', 'poss_stkcnt', 'wght'):
        if col in df.columns:
            df[col] = df[col].map(to_float)
    if 'dt' in df.columns:
        df = df.sort_values('dt').reset_index(drop=True)
    return df


def _return_pct(df: pd.DataFrame, n: int) -> float:
    if len(df) < n + 1 or 'cur_prc' not in df.columns:
        return 0.0
    start = df['cur_prc'].iloc[-(n + 1)]
    end = df['cur_prc'].iloc[-1]
    if start <= 0:
        return 0.0
    return (end / start - 1) * 100


# ==================== 전략 1: 주도 섹터 & 대장주 눌림목 ====================

def screen_leading_sectors(base_dt: str) -> list:
    """거래대금 20일 평균 대비 급증 + RS 우수 + 20일선 위 조건을 만족하는 주도 섹터 선별."""
    leading = []
    for mkt in MARKETS:
        try:
            sectors = kw.get_all_sector_index(mkt['inds_all_cd'])
        except KiwoomAPIError as exc:
            logger.error('[%s] 전업종지수 조회 실패: %s', mkt['market_name'], exc)
            continue
        if not sectors:
            continue

        try:
            market_df = _sector_daily_df(mkt['inds_all_cd'], base_dt)
        except KiwoomAPIError as exc:
            logger.error('[%s] 시장 종합지수 일봉 조회 실패: %s', mkt['market_name'], exc)
            continue
        market_return_5d = _return_pct(market_df, 5)

        market_leading = []
        for sector in sectors:
            sector_cd = sector.get('stk_cd')
            sector_name = sector.get('stk_nm')
            if not sector_cd or not sector_name:
                continue
            try:
                sdf = _sector_daily_df(sector_cd, base_dt)
            except KiwoomAPIError as exc:
                logger.warning('[%s] 업종 일봉 조회 실패: %s', sector_name, exc)
                continue
            if len(sdf) < SECTOR_MA_WINDOW + 1 or 'trde_prica' not in sdf.columns:
                continue

            sdf['ma20'] = _ma(sdf['cur_prc'], SECTOR_MA_WINDOW)
            latest = sdf.iloc[-1]
            avg_value_20 = sdf['trde_prica'].iloc[-(SECTOR_MA_WINDOW + 1):-1].mean()
            if not avg_value_20 or avg_value_20 <= 0:
                continue

            value_surge_ratio = latest['trde_prica'] / avg_value_20
            above_ma20 = bool(pd.notna(latest['ma20']) and latest['cur_prc'] > latest['ma20'])
            rs = _return_pct(sdf, 5) - market_return_5d

            if value_surge_ratio >= SECTOR_VALUE_SURGE_RATIO and above_ma20 and rs > 0:
                market_leading.append({
                    'market_name': mkt['market_name'],
                    'sector_cd': sector_cd,
                    'sector_name': sector_name,
                    'value_surge_ratio': value_surge_ratio,
                    'rs': rs,
                    'stock_mrkt_tp': mkt['stock_mrkt_tp'],
                })

        market_leading.sort(key=lambda x: x['value_surge_ratio'], reverse=True)
        leading.extend(market_leading[:TOP_N_SECTORS])

    return leading


def _supply_strength_score(stk_cd: str) -> float:
    """최근 5거래일 외국인 보유주식수 변동합으로 수급강도 근사."""
    try:
        fdf = _foreign_trend_df(stk_cd)
    except KiwoomAPIError:
        return 0.0
    if fdf.empty or 'chg_qty' not in fdf.columns:
        return 0.0
    return float(fdf['chg_qty'].tail(5).sum())


def find_sector_leader(sector: dict) -> dict | None:
    """대장주 점수 = 거래대금비중 40% + 등락률 30% + 외인/기관 수급강도 30% 최고 종목 선정."""
    try:
        stocks = kw.get_sector_stock_price(sector['stock_mrkt_tp'], sector['sector_cd'])
    except KiwoomAPIError as exc:
        logger.warning('[%s] 업종별 종목 시세 조회 실패: %s', sector['sector_name'], exc)
        return None
    if not stocks:
        return None

    df = pd.DataFrame(stocks)
    if 'stk_cd' not in df.columns:
        return None
    for col in ('cur_prc', 'flu_rt', 'now_trde_qty'):
        if col in df.columns:
            df[col] = df[col].map(to_float)
        else:
            df[col] = 0.0

    df['trde_value_est'] = (df['cur_prc'] * df['now_trde_qty']).abs()
    total_value = df['trde_value_est'].sum()
    if total_value <= 0:
        return None
    df['value_share'] = df['trde_value_est'] / total_value
    df = df.sort_values('trde_value_est', ascending=False).head(LEADER_CANDIDATES_PER_SECTOR).reset_index(drop=True)

    candidates = []
    for _, row in df.iterrows():
        stk_cd = row.get('stk_cd')
        if not stk_cd:
            continue
        candidates.append({
            'stk_cd': stk_cd,
            'stk_nm': row.get('stk_nm', ''),
            'cur_prc': row['cur_prc'],
            'flu_rt': row['flu_rt'],
            'value_share': row['value_share'],
            'supply_score': _supply_strength_score(stk_cd),
        })

    if not candidates:
        return None

    cdf = pd.DataFrame(candidates)
    cdf['flu_rt_norm'] = _minmax(cdf['flu_rt'])
    cdf['supply_norm'] = _minmax(cdf['supply_score'])
    cdf['leader_score'] = cdf['value_share'] * 0.4 + cdf['flu_rt_norm'] * 0.3 + cdf['supply_norm'] * 0.3

    best = cdf.sort_values('leader_score', ascending=False).iloc[0]
    return {
        'stk_cd': best['stk_cd'],
        'stk_nm': best['stk_nm'],
        'cur_prc': best['cur_prc'],
        'leader_score': best['leader_score'],
    }


def check_pullback(stk_cd: str, base_dt: str) -> dict | None:
    """대장주 눌림목 진입조건 판정: 지지 이평선 근접 + 거래량 마름 + 외인/기관 순매수 기조 유지."""
    try:
        pdf = _stock_daily_df(stk_cd, base_dt)
    except KiwoomAPIError:
        return None
    if len(pdf) < 25 or 'cur_prc' not in pdf.columns:
        return None

    pdf['ma5'] = _ma(pdf['cur_prc'], 5)
    pdf['ma10'] = _ma(pdf['cur_prc'], 10)
    pdf['ma20'] = _ma(pdf['cur_prc'], 20)
    latest = pdf.iloc[-1]

    recent = pdf.tail(20).reset_index(drop=True)
    recent['chg_pct'] = recent['cur_prc'].pct_change() * 100
    if recent['chg_pct'].isna().all():
        return None
    surge_idx = int(recent['chg_pct'].idxmax())
    if recent.loc[surge_idx, 'chg_pct'] < SURGE_MIN_CHANGE_PCT:
        return None  # 최근 구간에 강한 상승일이 없으면 눌림목 대상 아님

    surge_volume = recent.loc[surge_idx, 'trde_qty']
    pullback = recent.iloc[surge_idx + 1:]
    if pullback.empty or not surge_volume or surge_volume <= 0:
        return None

    pullback_avg_volume = pullback['trde_qty'].mean()
    volume_dry = pullback_avg_volume <= surge_volume * PULLBACK_VOLUME_DROP_RATIO

    support_line = None
    for label, ma_col in (('5일선', 'ma5'), ('10일선', 'ma10'), ('20일선', 'ma20')):
        ma_val = latest[ma_col]
        if pd.isna(ma_val) or ma_val <= 0:
            continue
        if abs(latest['cur_prc'] - ma_val) / ma_val <= PULLBACK_MA_TOLERANCE:
            support_line = label
            break
    if support_line is None:
        return None

    supply_ok = False
    try:
        fdf = _foreign_trend_df(stk_cd)
        if not fdf.empty and 'chg_qty' in fdf.columns:
            supply_ok = float(fdf['chg_qty'].tail(len(pullback)).sum()) >= 0
    except KiwoomAPIError:
        pass

    if not (volume_dry and supply_ok):
        return None

    return {
        'stk_cd': stk_cd,
        'cur_prc': latest['cur_prc'],
        'support_line': support_line,
        'volume_drop_pct': (1 - pullback_avg_volume / surge_volume) * 100,
        'supply_ok': supply_ok,
    }


def run_strategy_leading_sector_pullback() -> list:
    """전략 1 실행: 주도 섹터 선별 → 대장주 판별 → 눌림목 조건 검증."""
    base_dt = _today_str()
    sectors = screen_leading_sectors(base_dt)
    logger.info('[전략1] 주도 섹터 %d개 선정: %s', len(sectors), [s['sector_name'] for s in sectors])

    results = []
    for sector in sectors:
        try:
            leader = find_sector_leader(sector)
            if not leader:
                continue
            pullback = check_pullback(leader['stk_cd'], base_dt)
            if not pullback:
                continue
            results.append({
                'market_name': sector['market_name'],
                'sector_name': sector['sector_name'],
                'stk_cd': leader['stk_cd'],
                'stk_nm': leader['stk_nm'],
                'cur_prc': pullback['cur_prc'],
                'support_line': pullback['support_line'],
                'volume_drop_pct': pullback['volume_drop_pct'],
                'supply_ok': pullback['supply_ok'],
            })
        except Exception as exc:  # 종목 단위 오류가 전체 스크리닝을 중단시키지 않도록 격리
            logger.exception('[전략1] %s 처리 중 오류: %s', sector.get('sector_name'), exc)
    return results


# ==================== 전략 2: 정배열 초기 + 외국인 연속 순매수 ====================

def _collect_streak_candidates() -> dict:
    """ka10131로 시장 전체 외국인 연속순매수 상위 종목을 1차 수집 (종목코드 → 종목명)."""
    candidates = {}
    for mkt in MARKETS:
        try:
            rows = kw.get_foreign_inst_streak(mkt['streak_mrkt_tp'], dt=ALIGNMENT_STREAK_LOOKBACK)
        except KiwoomAPIError as exc:
            logger.error('[%s] 외국인/기관 연속매매 현황 조회 실패: %s', mkt['market_name'], exc)
            continue
        for row in rows:
            stk_cd = row.get('stk_cd')
            if stk_cd and stk_cd not in candidates:
                candidates[stk_cd] = row.get('stk_nm', '')
    return candidates


def _check_alignment_and_foreign_buy(stk_cd: str, stk_nm: str, base_dt: str) -> dict | None:
    try:
        pdf = _stock_daily_df(stk_cd, base_dt)
    except KiwoomAPIError:
        return None
    if len(pdf) < 121 or 'cur_prc' not in pdf.columns:
        return None

    pdf['ma20'] = _ma(pdf['cur_prc'], 20)
    pdf['ma60'] = _ma(pdf['cur_prc'], 60)
    pdf['ma120'] = _ma(pdf['cur_prc'], 120)
    latest = pdf.iloc[-1]

    if pd.isna(latest['ma20']) or pd.isna(latest['ma60']) or pd.isna(latest['ma120']):
        return None
    if not (latest['cur_prc'] > latest['ma20'] > latest['ma60'] > latest['ma120']):
        return None  # 정배열 미충족

    disparity = latest['cur_prc'] / latest['ma20'] * 100
    if disparity > ALIGNMENT_DISPARITY_MAX_PCT:
        return None  # 이미 과열 구간

    recent5 = pdf.tail(5)
    breach_days = int((recent5['cur_prc'] < recent5['ma20']).sum())
    if breach_days > ALIGNMENT_MAX_MA20_BREACH_DAYS:
        return None  # 20일선 이탈 일수 초과 → 추세 지지 미충족

    try:
        fdf = _foreign_trend_df(stk_cd)
    except KiwoomAPIError:
        return None
    if fdf.empty or 'chg_qty' not in fdf.columns or 'wght' not in fdf.columns:
        return None

    recent10 = fdf.tail(10)
    foreign_buy_days = int((recent10['chg_qty'] > 0).sum())
    if foreign_buy_days < ALIGNMENT_MIN_FOREIGN_BUY_DAYS:
        return None

    recent20 = fdf.tail(20)
    if len(recent20) < 2:
        return None
    wght_change = float(recent20['wght'].iloc[-1] - recent20['wght'].iloc[0])

    return {
        'stk_cd': stk_cd,
        'stk_nm': stk_nm,
        'cur_prc': latest['cur_prc'],
        'disparity_pct': disparity,
        'foreign_buy_days': foreign_buy_days,
        'wght_change': wght_change,
    }


def run_strategy_alignment_foreign_buy() -> list:
    """전략 2 실행: 외국인 연속순매수 1차 후보 → 정배열/이격도/지지 조건 정밀 검증."""
    base_dt = _today_str()
    candidates = _collect_streak_candidates()
    logger.info('[전략2] 1차 후보 %d종목 확보, 상위 %d종목 정밀 검증', len(candidates), ALIGNMENT_MAX_CANDIDATES)

    results = []
    for idx, (stk_cd, stk_nm) in enumerate(candidates.items()):
        if idx >= ALIGNMENT_MAX_CANDIDATES:
            break
        try:
            detail = _check_alignment_and_foreign_buy(stk_cd, stk_nm, base_dt)
            if detail:
                results.append(detail)
        except Exception as exc:  # 종목 단위 오류가 전체 스크리닝을 중단시키지 않도록 격리
            logger.exception('[전략2] %s(%s) 처리 중 오류: %s', stk_nm, stk_cd, exc)
    return results
