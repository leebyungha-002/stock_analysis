# -*- coding: utf-8 -*-
"""
키움증권 REST API 클라이언트
- OAuth2 접근토큰 발급/자동 갱신 (au10001, /oauth2/token)
- TR 요청 공통 처리 (헤더 구성, 연속조회 cont-yn/next-key 페이지네이션)
- Rate Limit 대응: 요청 간 최소 간격 + 429/5xx/네트워크 오류 재시도(backoff)

TR ID·URL·요청/응답 필드는 키움 공식 REST API 개발자 포털(https://openapi.kiwoom.com)과
공식 예제 저장소(GitHub: Kiwoom-Securities/Kiwoom-REST-API)를 기준으로 작성했습니다.
계좌 승인 후 실제 발급받은 문서와 TR ID 목록이 다르면 이 파일 상단의 TR_* 상수만 대조/수정하면 됩니다.
"""
import os
import time
import logging
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    """dart_analysis_app/.env 파일에서 환경변수 로드 (python-dotenv 불필요)"""
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

# 'mock'(모의투자) 또는 'real'(실전투자)
KIWOOM_MODE = os.environ.get('KIWOOM_MODE', 'mock').strip().lower()
APP_KEY = os.environ.get('KIWOOM_APP_KEY', '').strip()
APP_SECRET = os.environ.get('KIWOOM_APP_SECRET', '').strip()
ACCOUNT_NO = os.environ.get('ACCOUNT_NO', '').strip()

_BASE_URLS = {
    'real': 'https://api.kiwoom.com',
    'mock': 'https://mockapi.kiwoom.com',
}
BASE_URL = _BASE_URLS.get(KIWOOM_MODE, _BASE_URLS['mock'])

MIN_REQUEST_INTERVAL_SEC = 0.25   # 연속 요청 사이 최소 간격 (Rate Limit 대응)
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2
DEFAULT_TIMEOUT_SEC = 30
TOKEN_REFRESH_MARGIN_MIN = 10     # 만료 이 시간 전에 미리 재발급
AUTH_FAILURE_COOLDOWN_SEC = 60    # 확정적 인증 실패(자격증명 오류 등) 후 재발급 재시도를 쉬는 시간

# ---- TR ID 상수: (api_id, path) — 공식 문서 대조용으로 이름을 명확히 분리 ----
TR_SECTOR_CODE_LIST = ('ka10101', '/api/dostk/stkinfo')   # 업종코드 리스트
TR_ALL_SECTOR_INDEX = ('ka20003', '/api/dostk/sect')       # 전업종지수요청 (당일 업종별 등락률/거래대금/비중)
TR_SECTOR_DAILY_CHART = ('ka20006', '/api/dostk/chart')    # 업종일봉조회요청 (업종 일별 시세/거래대금)
TR_SECTOR_STOCK_PRICE = ('ka20002', '/api/dostk/sect')     # 업종별주가요청 (업종 내 종목 시세)
TR_STOCK_LIST = ('ka10099', '/api/dostk/stkinfo')          # 종목정보 리스트 (전체 종목 + 업종명)
TR_STOCK_DAILY_CHART = ('ka10081', '/api/dostk/chart')     # 주식일봉차트조회요청 (이평선/거래량/거래대금)
TR_STOCK_FOREIGN_TREND = ('ka10008', '/api/dostk/frgnistt')   # 주식외국인종목별매매동향 (보유비중/변동수량 일별)
TR_FOREIGN_INST_STREAK = ('ka10131', '/api/dostk/frgnistt')   # 기관외국인연속매매현황요청 (시장 전체 랭킹)
TR_STOCK_INVESTOR_INSTITUTION = ('ka10059', '/api/dostk/stkinfo')  # 종목별투자자기관별요청 (기관 순매수)


class KiwoomAPIError(Exception):
    """키움 API 요청/인증 실패"""


def _safe_json(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def to_float(value, default=0.0) -> float:
    """키움 API 응답의 숫자 필드(문자열, +/- 부호, 공백 포함 가능)를 안전하게 float으로 변환."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


class KiwoomClient:
    def __init__(self):
        if not APP_KEY or not APP_SECRET:
            raise KiwoomAPIError(
                '.env 파일에 KIWOOM_APP_KEY / KIWOOM_APP_SECRET을 설정하세요. '
                f'(현재 모드: {KIWOOM_MODE}, base_url: {BASE_URL})'
            )
        self.session = requests.Session()
        self._token = None
        self._token_expires_at = None
        self._last_request_at = 0.0
        self._auth_failure_msg = None
        self._auth_failure_until = 0.0

    # ---------------- 인증 ----------------
    def _issue_token(self):
        url = f'{BASE_URL}/oauth2/token'
        payload = {
            'grant_type': 'client_credentials',
            'appkey': APP_KEY,
            'secretkey': APP_SECRET,
        }

        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(
                    url, json=payload,
                    headers={'Content-Type': 'application/json;charset=UTF-8'},
                    timeout=DEFAULT_TIMEOUT_SEC,
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning('토큰 발급 네트워크 오류(%s) - %d/%d 재시도', exc, attempt, MAX_RETRIES)
                time.sleep(RETRY_BACKOFF_SEC * attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning('토큰 발급 HTTP %d 응답 - %d/%d 재시도 (%d초 대기)',
                                resp.status_code, attempt, MAX_RETRIES, RETRY_BACKOFF_SEC * attempt)
                time.sleep(RETRY_BACKOFF_SEC * attempt)
                continue

            data = _safe_json(resp)
            if resp.status_code >= 400 or data.get('return_code') not in (None, 0):
                # 인증정보 자체가 잘못된 확정적 실패(예: 실전/모의 키 불일치) - 재시도해도 소용없으므로
                # 짧은 쿨다운 동안 캐시된 오류를 즉시 재사용해 토큰 엔드포인트를 연타하지 않는다.
                msg = f"토큰 발급 실패 (HTTP {resp.status_code}): {data.get('return_msg', resp.text[:200])}"
                self._auth_failure_msg = msg
                self._auth_failure_until = time.time() + AUTH_FAILURE_COOLDOWN_SEC
                raise KiwoomAPIError(msg)

            token = data.get('token')
            expires_dt = data.get('expires_dt')  # 'YYYYMMDDHHMMSS'
            if not token or not expires_dt:
                raise KiwoomAPIError('토큰 응답에 token/expires_dt 필드가 없습니다.')

            self._token = token
            self._auth_failure_msg = None
            try:
                self._token_expires_at = datetime.strptime(expires_dt, '%Y%m%d%H%M%S')
            except ValueError:
                self._token_expires_at = datetime.now() + timedelta(hours=1)
            logger.info('키움 접근토큰 발급 완료 (mode=%s, 만료=%s)', KIWOOM_MODE, self._token_expires_at)
            return

        raise KiwoomAPIError(f'토큰 발급 {MAX_RETRIES}회 재시도 후에도 실패했습니다: {last_exc}')

    def _ensure_token(self):
        if (
            self._token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at - timedelta(minutes=TOKEN_REFRESH_MARGIN_MIN)
        ):
            return
        if self._auth_failure_msg and time.time() < self._auth_failure_until:
            raise KiwoomAPIError(f'{self._auth_failure_msg} (쿨다운 중 - 재발급 재시도 생략)')
        self._issue_token()

    # ---------------- 요청 ----------------
    def _throttle(self):
        elapsed = time.time() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SEC:
            time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)

    def request(self, api_id: str, path: str, body: dict | None = None,
                cont_yn: str | None = None, next_key: str | None = None) -> dict:
        """TR 단건 요청. 토큰 자동 발급/갱신 + 401/429/5xx/네트워크 오류 재시도."""
        self._ensure_token()

        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            headers = {
                'Content-Type': 'application/json;charset=UTF-8',
                'api-id': api_id,
                'authorization': f'Bearer {self._token}',
            }
            if cont_yn:
                headers['cont-yn'] = cont_yn
            if next_key:
                headers['next-key'] = next_key

            self._throttle()
            try:
                resp = self.session.post(f'{BASE_URL}{path}', json=body or {},
                                          headers=headers, timeout=DEFAULT_TIMEOUT_SEC)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning('[%s] 네트워크 오류(%s) - %d/%d 재시도', api_id, exc, attempt, MAX_RETRIES)
                time.sleep(RETRY_BACKOFF_SEC * attempt)
                continue
            finally:
                self._last_request_at = time.time()

            if resp.status_code == 401:
                logger.warning('[%s] 인증 만료 감지 → 토큰 재발급 후 재시도', api_id)
                self._issue_token()
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning('[%s] HTTP %d 응답 - %d/%d 재시도 (%d초 대기)',
                                api_id, resp.status_code, attempt, MAX_RETRIES, RETRY_BACKOFF_SEC * attempt)
                time.sleep(RETRY_BACKOFF_SEC * attempt)
                continue

            data = _safe_json(resp)
            return_code = data.get('return_code')
            if resp.status_code >= 400 or return_code not in (None, 0):
                raise KiwoomAPIError(
                    f"[{api_id}] 요청 실패 (HTTP {resp.status_code}, return_code={return_code}): "
                    f"{data.get('return_msg', resp.text[:200])}"
                )

            data['_cont_yn'] = resp.headers.get('cont-yn') or resp.headers.get('Cont-Yn')
            data['_next_key'] = resp.headers.get('next-key') or resp.headers.get('Next-Key')
            return data

        raise KiwoomAPIError(f'[{api_id}] {MAX_RETRIES}회 재시도 후에도 요청에 실패했습니다: {last_exc}')

    def request_all_pages(self, api_id: str, path: str, body: dict | None = None,
                           list_key: str | None = None, max_pages: int = 10,
                           page_delay_sec: float = 0.2) -> list:
        """연속조회(cont-yn=Y)를 max_pages까지 순회하며 list_key 리스트를 이어붙여 반환."""
        rows: list = []
        cont_yn, next_key = None, None
        for page in range(max_pages):
            data = self.request(api_id, path, body=body, cont_yn=cont_yn, next_key=next_key)
            if list_key:
                records = data.get(list_key, [])
                if isinstance(records, list):
                    rows.extend(records)
            cont_yn = data.get('_cont_yn')
            next_key = data.get('_next_key')
            if cont_yn != 'Y':
                break
            if page + 1 < max_pages:
                time.sleep(page_delay_sec)
        return rows


_client: KiwoomClient | None = None


def get_client() -> KiwoomClient:
    global _client
    if _client is None:
        _client = KiwoomClient()
    return _client


# ==================== 개별 TR 래퍼 함수 ====================

def get_sector_code_list(mrkt_tp: str) -> list:
    """업종코드 리스트[ka10101]. mrkt_tp: 0=코스피, 1=코스닥"""
    api_id, path = TR_SECTOR_CODE_LIST
    return get_client().request_all_pages(api_id, path, body={'mrkt_tp': mrkt_tp}, list_key='list')


def get_all_sector_index(inds_cd: str) -> list:
    """전업종지수요청[ka20003]. inds_cd: 001=코스피 종합, 101=코스닥 종합 → 시장 내 전체 업종 당일 스냅샷"""
    api_id, path = TR_ALL_SECTOR_INDEX
    return get_client().request_all_pages(api_id, path, body={'inds_cd': inds_cd}, list_key='all_inds_idex')


def get_sector_daily_chart(inds_cd: str, base_dt: str) -> list:
    """업종일봉조회요청[ka20006]. 업종 일별 현재가/거래량/거래대금 (이동평균/거래대금 급증 판단용)"""
    api_id, path = TR_SECTOR_DAILY_CHART
    body = {'inds_cd': inds_cd, 'base_dt': base_dt}
    return get_client().request_all_pages(api_id, path, body=body, list_key='inds_dt_pole_qry', max_pages=3)


def get_sector_stock_price(mrkt_tp: str, inds_cd: str, stex_tp: str = '1') -> list:
    """업종별주가요청[ka20002]. 업종 내 종목별 현재가/등락률/거래량 (대장주 후보 탐색용)"""
    api_id, path = TR_SECTOR_STOCK_PRICE
    body = {'mrkt_tp': mrkt_tp, 'inds_cd': inds_cd, 'stex_tp': stex_tp}
    return get_client().request_all_pages(api_id, path, body=body, list_key='inds_stkpc')


def get_stock_list(mrkt_tp: str) -> list:
    """종목정보 리스트[ka10099]. mrkt_tp: 0=코스피, 10=코스닥 → 전체 종목 + 업종명(upName)"""
    api_id, path = TR_STOCK_LIST
    return get_client().request_all_pages(api_id, path, body={'mrkt_tp': mrkt_tp}, list_key='list')


def get_stock_daily_chart(stk_cd: str, base_dt: str, upd_stkpc_tp: str = '1', max_pages: int = 3) -> list:
    """주식일봉차트조회요청[ka10081]. 종목 일별 OHLCV+거래대금 (이동평균/눌림목 판단용)"""
    api_id, path = TR_STOCK_DAILY_CHART
    body = {'stk_cd': stk_cd, 'base_dt': base_dt, 'upd_stkpc_tp': upd_stkpc_tp}
    return get_client().request_all_pages(api_id, path, body=body,
                                           list_key='stk_dt_pole_chart_qry', max_pages=max_pages)


def get_stock_foreign_trend(stk_cd: str, max_pages: int = 2) -> list:
    """주식외국인종목별매매동향[ka10008]. 일별 외국인 보유비중/변동수량 (순매수일수/지분율 추세 판단용)"""
    api_id, path = TR_STOCK_FOREIGN_TREND
    return get_client().request_all_pages(api_id, path, body={'stk_cd': stk_cd},
                                           list_key='stk_frgnr', max_pages=max_pages)


def get_foreign_inst_streak(mrkt_tp: str, dt: str = '10', stex_tp: str = '3') -> list:
    """기관외국인연속매매현황요청[ka10131]. 시장 전체 외국인/기관 연속순매수 랭킹 (1차 후보 스크리닝용)"""
    api_id, path = TR_FOREIGN_INST_STREAK
    body = {
        'dt': dt, 'mrkt_tp': mrkt_tp, 'netslmt_tp': '2',
        'stk_inds_tp': '0', 'amt_qty_tp': '0', 'stex_tp': stex_tp,
        'strt_dt': '', 'end_dt': '',
    }
    return get_client().request_all_pages(api_id, path, body=body,
                                           list_key='orgn_frgnr_cont_trde_prst', max_pages=3)


def get_stock_investor_institution(stk_cd: str, dt: str, amt_qty_tp: str = '1',
                                    trde_tp: str = '0', unit_tp: str = '1000') -> list:
    """종목별투자자기관별요청[ka10059]. 특정일 개인/외국인/기관 순매수 금액 (수급강도 스코어링용)"""
    api_id, path = TR_STOCK_INVESTOR_INSTITUTION
    body = {'dt': dt, 'stk_cd': stk_cd, 'amt_qty_tp': amt_qty_tp, 'trde_tp': trde_tp, 'unit_tp': unit_tp}
    return get_client().request_all_pages(api_id, path, body=body, list_key='stk_invsr_orgn', max_pages=1)
