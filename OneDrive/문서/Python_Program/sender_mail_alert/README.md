# sender_mail_alert

Daum(등) 메일함을 IMAP으로 조회해서 지정한 발신자로부터 온 새 메일을 감지하면
텔레그램으로 알려주고, 필요하면 마크다운(.md) 파일로도 저장하는 파이썬 스크립트입니다.

- 외부 AI API(Claude, OpenAI 등) 호출 없음. 순수 `imaplib`(메일 조회) + `requests`(텔레그램 전송)만 사용합니다.
- 윈도우 작업 스케줄러에 등록해서 매주 월/수/금요일 등 원하는 주기로 자동 실행하는 것을 전제로 만들었습니다.
  실제로는 `SenderMailAlert`라는 이름으로 매주 월/수/금 10:40에 등록되어 있고, PC가 꺼져 있어
  실행을 놓치면 켜졌을 때 자동으로 캐치업 실행됩니다 (`StartWhenAvailable` + `WakeToRun`, 8번 항목 참고).

## 1. 사전 준비

1. 파이썬 3.9 이상 설치
2. 이 폴더에서 의존성 설치
   ```
   pip install -r requirements.txt
   ```

## 2. Daum 메일 IMAP 활성화

1. Daum 메일 웹사이트 로그인 → **환경설정** → **POP3/IMAP** 메뉴로 이동
2. **IMAP/SMTP 사용함**으로 설정 저장
3. Daum은 2단계 인증(또는 IMAP 접근용) **앱 비밀번호** 발급이 필요합니다. 일반 로그인 비밀번호로는
   IMAP 로그인이 거부될 수 있습니다.
   - 카카오계정 → 보안 설정에서 2단계 인증을 켠 뒤, "앱 비밀번호" 발급 메뉴에서 메일용 비밀번호를
     새로 생성하세요.
   - `config.ini`의 `password`에는 이 **앱 비밀번호**를 입력합니다 (평소 로그인 비밀번호 아님).

> Gmail, Naver 등 다른 메일 서비스도 `imap_server`/`imap_port`만 바꾸면 동일하게 동작합니다.
> (예: Gmail은 `imap.gmail.com`, 993 — 단, 이 경우도 앱 비밀번호가 필요합니다.)

## 3. 텔레그램 봇 설정 (.env)

이 저장소의 다른 앱(`dart_analysis_app`, `youtube_summary`, `cycle_investment`)과 **같은 텔레그램
봇을 공유**합니다. 새 봇을 만들 필요 없이, `.env.example`을 복사해서 `.env`로 만든 뒤 다른 앱의
`.env`에 있는 값을 그대로 옮겨 적으면 됩니다.

```
copy .env.example .env
```

```
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ
TELEGRAM_CHAT_ID=123456789
```

- `sender_mail_alert.py`는 실행 시 이 폴더의 `.env` 파일을 직접 파싱해 환경변수로 로드합니다
  (다른 앱과 동일한 방식이며, `python-dotenv` 등 추가 의존성은 필요 없습니다).
- 새 봇을 처음부터 만들고 싶다면 텔레그램에서 **@BotFather**에게 `/newbot`으로 발급받은
  `bot_token`과, 알림 받을 대화에 봇을 추가한 뒤
  `https://api.telegram.org/bot<bot_token>/getUpdates`에서 확인한 `chat_id`를 넣으면 됩니다.

## 4. config.ini 작성

`config.ini.example`을 복사해서 `config.ini`로 만든 뒤 값을 채웁니다.

```
copy config.ini.example config.ini
```

```ini
[mail]
imap_server = imap.daum.net
imap_port = 993
user = your_id@daum.net
password = your_app_password_here
target_senders = alert@example.com, news@example.com
mailbox = INBOX
default_days_back = 4

[markdown]
enabled = true
output_dir = mail_logs
mode = daily
```

- `target_senders`: 알림 받을 발신자 이메일 주소, 콤마로 여러 개 등록 가능
- `default_days_back`: `state.json`이 없는 최초 실행 시 며칠 전 메일까지 조회할지 (기본 4일)
- `markdown.mode`: `daily`(하루 한 파일에 이어쓰기, 기본값) 또는 `per_mail`(메일마다 파일 하나)
- 텔레그램 `bot_token`/`chat_id`는 `config.ini`가 아니라 `.env`에서 읽습니다 (3번 항목 참고).

`config.ini`, `.env`, `state.json`, `run.log`, `mail_logs/`는 `.gitignore`에 등록되어 있어
git 저장소로 관리하더라도 개인정보/민감정보가 커밋되지 않습니다.

## 5. 수동 테스트

```
python sender_mail_alert.py
```

- 처음 실행하면 `default_days_back`일 전 메일부터 조회해서 텔레그램으로 보내고 `state.json`을 생성합니다.
- 다시 실행했을 때 새 메일이 없으면 아무 메시지도 보내지 않고 조용히 종료합니다 (정상 동작).
- 실행 로그는 `run.log`에 계속 쌓입니다 (타임스탬프, 발견 건수, 전송/저장 성공 여부 등).

## 6. 마크다운 저장 옵션

- `markdown.enabled = false`로 두면 텔레그램 전송만 하고 파일 저장은 하지 않습니다.
- `mode = daily`: `mail_logs/2026-08-20.md` 처럼 실행일 기준 파일 하나에 그날 발견된 메일을
  `##` 제목으로 이어서 추가합니다.
- `mode = per_mail`: `mail_logs/20260820_143205_제목.md` 처럼 메일 1건당 파일을 따로 만듭니다.
  파일명에 못 쓰는 특수문자(`\ / : * ? " < > |`)는 `_`로 바뀌고, 파일명은 60자 이내로 잘립니다.
- 텔레그램 메시지는 본문을 앞 200자만 보여주지만, 마크다운 파일에는 본문 **전체**가 저장됩니다.

## 7. 윈도우 작업 스케줄러 등록

### GUI로 등록
1. **작업 스케줄러** 실행 → **작업 만들기**
2. 트리거: **매주**, 월요일/수요일/금요일 체크, 원하는 시각(예: 10:40) 지정
3. 동작: **프로그램 시작**, 프로그램/스크립트에 이 폴더의 `run.bat` 전체 경로 지정
4. 설정 탭에서 반드시 "사용할 수 없는 경우 최대한 빨리 작업 실행"(StartWhenAvailable, 놓친 작업
   캐치업)과 "절전 모드를 해제하여 작업 실행"(WakeToRun)을 함께 켜두세요 — PC가 꺼져 있거나
   절전 상태여서 예약 시각에 실행되지 못했을 경우, 켜지는 즉시 자동으로 놓친 실행을 따라잡습니다
   (아래 8번 참고 항목 참조).

### 명령어로 등록
`schtasks`는 StartWhenAvailable을 직접 지정할 수 없으므로, PowerShell로 등록하는 것을 권장합니다.

```powershell
$action   = New-ScheduledTaskAction -Execute "C:\경로\run.bat"
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Wednesday,Friday -At 10:40am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "SenderMailAlert" -Action $action -Trigger $trigger -Settings $settings
```

간단히 `schtasks`만 쓰고 싶다면 아래처럼 만든 뒤, 작업 스케줄러 GUI의 설정 탭에서
StartWhenAvailable/WakeToRun을 수동으로 체크해도 됩니다.
```
schtasks /create /sc weekly /d MON,WED,FRI /st 10:40 /tn "SenderMailAlert" /tr "C:\경로\run.bat"
```

### 등록 확인
```
schtasks /query /tn "SenderMailAlert" /v /fo LIST
```

### 삭제
```
schtasks /delete /tn "SenderMailAlert" /f
```

## 8. 참고사항

- **PC 절전 모드**: 예약 시각에 PC가 절전 상태이면 작업이 실행되지 않을 수 있습니다.
  작업 속성의 "절전 모드를 해제하여 이 작업 실행"(Wake the computer to run this task)을 켜두세요.
  그래도 완전히 꺼져 있는 상태(종료)에서는 깨울 수 없으므로, "사용할 수 없는 경우 최대한 빨리
  작업 실행"(Start the task as soon as possible after a scheduled start is missed)도 함께 켜두면
  PC를 켰을 때 놓친 실행을 자동으로 따라잡습니다.
- **회사 메일(Exchange 등)**: 회사/기관 메일 시스템은 보안 정책상 IMAP 접근 자체를 막아두는
  경우가 많습니다. 이 경우 관리자에게 IMAP 허용 여부를 문의해야 하며, 막혀 있다면 이 스크립트를
  그대로 쓸 수 없습니다.
- 첨부파일은 감지/저장 대상에서 제외됩니다 (본문 텍스트만 처리).
