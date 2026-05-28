# -*- coding: utf-8 -*-
"""
텔레그램 메시지 전송 모듈
.env 파일에서 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 자동 로드
"""
import os
import requests

def _load_env():
    """dart_analysis_app/.env 파일에서 환경변수 로드 (python-dotenv 불필요)"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

_load_env()

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '')
_MAX_LEN  = 4096


def send_message(text: str, token: str = '', chat_id: str = '') -> bool:
    """
    텔레그램으로 메시지 전송.
    4096자 초과 시 자동 분할하여 순서대로 전송.
    parse_mode=HTML 사용: <b>, <i>, <code> 태그 지원.
    """
    token   = token   or BOT_TOKEN
    chat_id = chat_id or CHAT_ID

    if not token or not chat_id:
        print("⚠️  .env 파일에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 설정하세요.")
        return False

    url    = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i:i+_MAX_LEN] for i in range(0, len(text), _MAX_LEN)]

    for chunk in chunks:
        try:
            resp = requests.post(
                url,
                json={'chat_id': chat_id, 'text': chunk, 'parse_mode': 'HTML'},
                timeout=15
            )
            if not resp.ok:
                print(f"⚠️  텔레그램 전송 실패 ({resp.status_code}): {resp.text[:300]}")
                return False
        except Exception as e:
            print(f"⚠️  텔레그램 전송 오류: {e}")
            return False
    return True
