"""텔레그램 메시지/파일 전송 모듈. .env의 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 사용."""
from __future__ import annotations

import os
import tempfile

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
_MAX_LEN = 4096


def send_message(text: str, token: str = "", chat_id: str = "") -> bool:
    """텔레그램으로 메시지 전송. 4096자 초과 시 자동 분할하여 순서대로 전송."""
    token = token or BOT_TOKEN
    chat_id = chat_id or CHAT_ID

    if not token or not chat_id:
        print("⚠️  .env 파일에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 설정하세요.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i : i + _MAX_LEN] for i in range(0, len(text), _MAX_LEN)]

    for chunk in chunks:
        try:
            resp = requests.post(
                url, json={"chat_id": chat_id, "text": chunk}, timeout=15
            )
            if not resp.ok:
                print(f"⚠️  텔레그램 전송 실패 ({resp.status_code}): {resp.text[:300]}")
                return False
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  텔레그램 전송 오류: {e}")
            return False
    return True


def send_document(
    text: str, filename: str = "", caption: str = "", token: str = "", chat_id: str = ""
) -> bool:
    """텍스트를 파일로 저장한 뒤 텔레그램 파일로 전송."""
    token = token or BOT_TOKEN
    chat_id = chat_id or CHAT_ID

    if not token or not chat_id:
        print("⚠️  .env 파일에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 설정하세요.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(text)
            tmp_path = tmp.name

        fname = filename or os.path.basename(tmp_path)

        with open(tmp_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (fname, f, "text/plain")},
                timeout=30,
            )

        if not resp.ok:
            print(f"⚠️  파일 전송 실패 ({resp.status_code}): {resp.text[:300]}")
            return False
        return True

    except Exception as e:  # noqa: BLE001
        print(f"⚠️  파일 전송 오류: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
