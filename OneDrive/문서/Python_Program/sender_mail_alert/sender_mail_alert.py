"""Daum(등) 메일함을 IMAP으로 조회해 지정 발신자의 새 메일을 텔레그램으로 알리고,
설정에 따라 마크다운(.md) 파일로도 저장하는 스크립트.

- LLM/AI API 호출 없음 (순수 imaplib + requests 조합)
- 윈도우 작업 스케줄러에서 run.bat을 통해 주기 실행하는 것을 전제로 함
"""

from __future__ import annotations

import configparser
import email
import html
import imaplib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

# 윈도우 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지는 것을 방지
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.ini"
ENV_PATH = BASE_DIR / ".env"
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "run.log"

TELEGRAM_CHUNK_LIMIT = 3800  # 텔레그램 4096자 제한에 여유를 둔 분할 기준
BODY_PREVIEW_LEN = 200  # 텔레그램 요약에 넣을 본문 미리보기 길이
FILENAME_MAX_LEN = 60  # per_mail 모드 파일명(확장자 제외) 최대 길이

logger = logging.getLogger("sender_mail_alert")


def _load_env() -> None:
    """.env 파일에서 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID를 읽어 환경변수로 로드한다.

    dart_analysis_app/youtube_summary 등 이 저장소의 다른 앱들과 동일한 봇(.env 파일 하나 공유)을
    쓰기 위한 것으로, python-dotenv 의존성 없이 직접 파싱한다 (다른 앱과 동일한 방식).
    """
    if not ENV_PATH.exists():
        return
    with ENV_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_env()


@dataclass
class MailItem:
    """새로 감지된 메일 한 건을 표현하는 자료구조."""

    subject: str
    sender: str
    date: datetime
    body: str


def setup_logging() -> None:
    """콘솔 + run.log 파일에 동시에 기록하는 로거를 구성한다."""
    logger.handlers.clear()  # main()이 같은 프로세스에서 재호출돼도 핸들러가 중복 누적되지 않도록
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)


def load_config() -> configparser.ConfigParser:
    """config.ini를 읽는다. 파일이 없으면 안내 메시지를 출력하고 종료한다."""
    if not CONFIG_PATH.exists():
        message = (
            f"config.ini 파일을 찾을 수 없습니다: {CONFIG_PATH}\n"
            "config.ini.example 파일을 복사해서 config.ini로 만든 뒤, "
            "메일/텔레그램 정보를 채워주세요.\n"
            "  예) copy config.ini.example config.ini"
        )
        print(message)
        sys.exit(1)

    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding="utf-8")
    return config


def load_last_checked() -> Optional[datetime]:
    """state.json에서 마지막 확인 시각을 읽는다. 없으면 None."""
    if not STATE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["last_checked"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("state.json 파싱 실패, 처음 실행으로 간주합니다: %s", exc)
        return None


def save_last_checked(moment: datetime) -> None:
    """이번 실행 시각을 state.json에 저장해 다음 실행의 중복 알림을 방지한다."""
    STATE_PATH.write_text(
        json.dumps({"last_checked": moment.isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def decode_mime_words(raw: Optional[str]) -> str:
    """메일 제목/발신자 헤더(MIME 인코딩 가능)를 사람이 읽을 수 있는 문자열로 디코딩한다."""
    if not raw:
        return ""
    decoded_parts = decode_header(raw)
    result = []
    for text, charset in decoded_parts:
        if isinstance(text, bytes):
            try:
                result.append(text.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                result.append(text.decode("utf-8", errors="replace"))
        else:
            result.append(text)
    return "".join(result)


def ensure_aware(dt: datetime) -> datetime:
    """타임존 정보가 없는 datetime을 로컬 타임존 기준으로 보정한다."""
    if dt.tzinfo is None:
        return dt.astimezone()
    return dt


def strip_html_tags(raw_html: str) -> str:
    """본문이 text/html뿐일 때, 태그를 제거하고 순수 텍스트만 남긴다."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_body(msg: Message) -> str:
    """text/plain을 우선 사용하고, 없으면 text/html에서 태그를 제거해 사용한다. 첨부파일은 무시."""
    plain_body: Optional[str] = None
    html_body: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                continue
            if content_type == "text/plain" and plain_body is None:
                plain_body = _decode_part(part)
            elif content_type == "text/html" and html_body is None:
                html_body = _decode_part(part)
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            plain_body = _decode_part(msg)
        elif content_type == "text/html":
            html_body = _decode_part(msg)

    if plain_body is not None:
        return plain_body.strip()
    if html_body is not None:
        return strip_html_tags(html_body)
    return ""


def _decode_part(part: Message) -> str:
    """메일 파트의 payload를 해당 파트의 charset으로 디코딩한다."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def fetch_new_mails(config: configparser.ConfigParser, last_checked: Optional[datetime]) -> list[MailItem]:
    """IMAP 서버에 접속해 target_senders로부터 온 새 메일을 조회한다."""
    mail_cfg = config["mail"]
    imap_server = mail_cfg.get("imap_server")
    imap_port = mail_cfg.getint("imap_port", fallback=993)
    user = mail_cfg.get("user")
    password = mail_cfg.get("password")
    mailbox = mail_cfg.get("mailbox", fallback="INBOX")
    default_days_back = mail_cfg.getint("default_days_back", fallback=4)
    target_senders = [s.strip() for s in mail_cfg.get("target_senders", "").split(",") if s.strip()]

    if not target_senders:
        logger.warning("config.ini의 target_senders가 비어 있습니다. 조회할 발신자가 없습니다.")
        return []

    if last_checked is not None:
        search_since = last_checked
    else:
        search_since = datetime.now(timezone.utc) - timedelta(days=default_days_back)

    since_str = search_since.strftime("%d-%b-%Y")

    conn = imaplib.IMAP4_SSL(imap_server, imap_port)
    try:
        conn.login(user, password)
        conn.select(mailbox, readonly=True)

        uid_to_mail: dict[bytes, MailItem] = {}
        for sender in target_senders:
            criteria = f'(SINCE "{since_str}" FROM "{sender}")'
            status, data = conn.uid("search", None, criteria)
            if status != "OK":
                logger.warning("IMAP 검색 실패 (발신자: %s): %s", sender, status)
                continue

            uids = data[0].split()
            for uid in uids:
                if uid in uid_to_mail:
                    continue
                mail_item = _fetch_and_parse(conn, uid)
                if mail_item is None:
                    continue
                if last_checked is not None and mail_item.date <= last_checked:
                    continue
                uid_to_mail[uid] = mail_item

        mails = sorted(uid_to_mail.values(), key=lambda m: m.date)
        return mails
    finally:
        try:
            conn.close()
        except imaplib.IMAP4.error:
            pass
        conn.logout()


def _fetch_and_parse(conn: imaplib.IMAP4_SSL, uid: bytes) -> Optional[MailItem]:
    """UID로 메일 원문을 가져와 MailItem으로 변환한다.

    (RFC822) 매크로 대신 (BODY.PEEK[])를 쓴다: 일부 IMAP 서버(다음 메일 등)가 특정 메일에서
    RFC822 fetch에 OK를 반환하면서도 본문을 비워 보내는 경우가 있어, 실제 메일이 소리 없이
    누락되는 문제가 있었다. BODY.PEEK[]는 \\Seen 플래그도 건드리지 않아 더 안전하다.
    """
    status, data = conn.uid("fetch", uid, "(BODY.PEEK[])")
    if status != "OK" or not data or data[0] is None:
        logger.warning("메일 본문 조회 실패 (uid=%s)", uid)
        return None

    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)

    subject = decode_mime_words(msg.get("Subject"))
    sender = decode_mime_words(msg.get("From"))
    date_header = msg.get("Date")

    try:
        mail_date = ensure_aware(parsedate_to_datetime(date_header))
    except (TypeError, ValueError):
        logger.warning("Date 헤더 파싱 실패 (uid=%s, subject=%s), 현재 시각으로 대체", uid, subject)
        mail_date = datetime.now().astimezone()

    body = extract_body(msg)
    return MailItem(subject=subject, sender=sender, date=mail_date, body=body)


def build_telegram_text(mails: list[MailItem]) -> str:
    """텔레그램 전송용 요약 텍스트를 구성한다 (본문은 앞 200자만)."""
    lines = [f"📬 새 메일 {len(mails)}건 도착\n"]
    for idx, mail in enumerate(mails, start=1):
        preview = mail.body[:BODY_PREVIEW_LEN]
        if len(mail.body) > BODY_PREVIEW_LEN:
            preview += "..."
        date_str = mail.date.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{idx}. {date_str} | {mail.sender}\n"
            f"제목: {mail.subject}\n"
            f"{preview}\n"
        )
    return "\n".join(lines)


def split_into_chunks(text: str, limit: int = TELEGRAM_CHUNK_LIMIT) -> list[str]:
    """텔레그램 길이 제한을 고려해 텍스트를 여러 조각으로 분할한다 (줄 단위 우선)."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            if len(line) > limit:
                for i in range(0, len(line), limit):
                    chunks.append(line[i : i + limit])
                current = ""
            else:
                current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram(text: str) -> bool:
    """텔레그램 봇 API로 메시지를 전송한다. 길면 여러 번 나눠 보낸다.

    bot_token/chat_id는 .env의 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID에서 읽는다
    (dart_analysis_app, youtube_summary 등 다른 앱과 동일한 봇을 공유).
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        logger.error(".env 파일에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 설정하세요.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    all_ok = True
    for chunk in split_into_chunks(text):
        try:
            resp = requests.post(url, data={"chat_id": chat_id, "text": chunk}, timeout=15)
            if resp.status_code != 200:
                logger.error("텔레그램 전송 실패 (status=%s): %s", resp.status_code, resp.text)
                all_ok = False
        except requests.RequestException as exc:
            logger.error("텔레그램 전송 중 예외 발생: %s", exc)
            all_ok = False
    return all_ok


def sanitize_filename(name: str) -> str:
    """파일명에 쓸 수 없는 특수문자를 언더스코어로 치환한다."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def save_markdown(config: configparser.ConfigParser, mails: list[MailItem]) -> bool:
    """설정에 따라 메일을 마크다운 파일로 저장한다 (daily 또는 per_mail 모드)."""
    md_cfg = config["markdown"]
    if not md_cfg.getboolean("enabled", fallback=True):
        return True

    output_dir = BASE_DIR / md_cfg.get("output_dir", fallback="mail_logs")
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = md_cfg.get("mode", fallback="daily").strip().lower()

    all_ok = True
    if mode == "per_mail":
        for mail in mails:
            try:
                _save_per_mail(output_dir, mail)
            except OSError as exc:
                logger.error("마크다운 저장 실패 (제목=%s): %s", mail.subject, exc)
                all_ok = False
    else:
        try:
            _save_daily(output_dir, mails)
        except OSError as exc:
            logger.error("마크다운(daily) 저장 실패: %s", exc)
            all_ok = False
    return all_ok


def _save_daily(output_dir: Path, mails: list[MailItem]) -> None:
    """실행일 기준 mail_logs/YYYY-MM-DD.md 파일 하나에 이어서 저장한다."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    file_path = output_dir / f"{today_str}.md"

    is_new = not file_path.exists()
    with file_path.open("a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# 메일 로그 - {today_str}\n\n")
        for mail in mails:
            f.write(f"## {mail.subject}\n")
            f.write(f"- 발신자: {mail.sender}\n")
            f.write(f"- 수신일시: {mail.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"{mail.body}\n\n")
            f.write("---\n\n")


def _save_per_mail(output_dir: Path, mail: MailItem) -> None:
    """메일 1건당 mail_logs/YYYYMMDD_HHMMSS_제목.md 파일을 개별 생성한다."""
    timestamp = mail.date.strftime("%Y%m%d_%H%M%S")
    safe_subject = sanitize_filename(mail.subject) or "제목없음"

    prefix = f"{timestamp}_"
    max_subject_len = max(FILENAME_MAX_LEN - len(prefix), 1)
    safe_subject = safe_subject[:max_subject_len]

    file_path = output_dir / f"{prefix}{safe_subject}.md"

    with file_path.open("w", encoding="utf-8") as f:
        f.write(f"# {mail.subject}\n\n")
        f.write(f"- 발신자: {mail.sender}\n")
        f.write(f"- 수신일시: {mail.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"{mail.body}\n")


def main() -> None:
    setup_logging()
    config = load_config()

    last_checked = load_last_checked()
    run_started_at = datetime.now().astimezone()
    logger.info("실행 시작. 마지막 확인 시각: %s", last_checked if last_checked else "(없음, 최초 실행)")

    try:
        mails = fetch_new_mails(config, last_checked)
    except (imaplib.IMAP4.error, OSError) as exc:
        logger.error("IMAP 메일 조회 실패: %s", exc)
        sys.exit(1)

    logger.info("새 메일 %d건 발견", len(mails))

    if not mails:
        save_last_checked(run_started_at)
        logger.info("새 메일 없음. 조용히 종료합니다.")
        return

    telegram_text = build_telegram_text(mails)
    if send_telegram(telegram_text):
        logger.info("텔레그램 전송 성공")
    else:
        logger.warning("텔레그램 전송 중 일부 실패 발생 (위 로그 참고)")

    if save_markdown(config, mails):
        logger.info("마크다운 저장 성공")
    else:
        logger.warning("마크다운 저장 중 일부 실패 발생 (위 로그 참고)")

    save_last_checked(run_started_at)
    logger.info("실행 종료. 다음 확인 기준 시각: %s", run_started_at)


if __name__ == "__main__":
    main()
