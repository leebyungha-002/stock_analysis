# YouTube 채널 주간 Top3 요약 앱

등록된 유튜브 채널들의 최근 7일 업로드 영상 중 채널별 조회수 상위 3개를 선정하고,
자막(또는 음성 인식)을 추출해 Gemini API로 요약한 뒤 마크다운 리포트로 저장합니다.

## 파이프라인

1. `channels.json`에 등록된 채널 목록을 순회
2. YouTube Data API v3로 최근 7일 업로드 영상 조회 → 조회수 기준 상위 3개 선정
3. 각 영상의 자막 추출
   - 1순위: `youtube-transcript-api` (자막이 있는 경우, 빠르고 무료)
   - 2순위(폴백): 자막이 없으면 `yt-dlp`로 오디오 다운로드 → `faster-whisper`로 음성 인식
4. Gemini API(Google)로 요약 생성 (긴 트랜스크립트는 map-reduce 방식으로 청크 요약 후 종합)
5. `reports/YYYY-MM-DD_weekly_report.md` 형식으로 마크다운 리포트 저장

## 폴더 구조

```
youtube_summary/
├── main.py              # CLI 진입점 (오케스트레이션)
├── youtube_client.py    # YouTube Data API v3 호출
├── transcript.py        # 자막 추출 (API 우선, faster-whisper 폴백)
├── summarizer.py         # Gemini API 요약 (map-reduce)
├── report.py            # 마크다운 리포트 생성
├── channels.json        # 채널 목록 (직접 입력)
├── .env                 # API 키 (직접 입력, git에 커밋되지 않음)
├── requirements.txt
├── run_weekly.bat        # Windows 작업 스케줄러용 실행 스크립트
├── logs/                # 실행 로그
└── reports/              # 생성된 리포트
```

## 설치

```powershell
cd "C:\Users\USer\OneDrive\문서\Python_Program\youtube_summary"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

`faster-whisper`와 `yt-dlp`가 오디오를 처리하려면 **ffmpeg**가 필요합니다.
[ffmpeg 공식 사이트](https://ffmpeg.org/download.html)에서 다운로드 후 PATH에 추가하세요.
(자막이 있는 영상만 처리한다면 ffmpeg 없이도 대부분 동작하지만, 폴백 경로를 위해 설치를 권장합니다.)

## 설정

### 1. `.env` — API 키 입력

`.env` 파일을 열어 아래 두 값을 채워주세요.

```
YOUTUBE_API_KEY=발급받은_유튜브_API_키
GEMINI_API_KEY=발급받은_Gemini_API_키
```

- YouTube API 키: [Google Cloud Console](https://console.cloud.google.com/) → API 및 서비스 → 사용자 인증 정보에서
  "YouTube Data API v3"를 활성화한 프로젝트의 API 키를 발급받으세요.
- Gemini API 키: [Google AI Studio](https://aistudio.google.com/apikey) → "Create API key"에서 무료로 발급받으세요.

### 2. `channels.json` — 채널 목록 입력

```json
{
  "channels": [
    { "name": "채널 표시 이름", "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx" }
  ]
}
```

채널 ID(`UC`로 시작하는 24자 문자열)를 찾는 방법:
- 채널 홈 → 정보 더보기(About) → "채널 ID 공유" 또는
- 채널 페이지 URL이 `youtube.com/channel/UCxxxx...` 형태면 그 부분이 채널 ID
- URL이 `@handle` 형태라면, 페이지 소스에서 `"channelId":"UC..."` 검색하거나
  YouTube Data API의 `channels.list?forHandle=@handle` 로 조회

## 실행

```powershell
.venv\Scripts\python main.py
```

옵션:
- `--days N` : 최근 N일간의 영상을 대상으로 함 (기본값 7)
- `--top-n N` : 채널별 상위 N개 영상 (기본값 3)
- `--whisper-model SIZE` : faster-whisper 모델 크기 (`tiny`/`base`/`small`/`medium`/`large-v3`, 기본값 `medium`)

## Windows 작업 스케줄러 등록 (주간 자동 실행)

1. `run_weekly.bat`의 `PROJECT_DIR` 경로가 실제 설치 경로와 일치하는지 확인 (이미 절대경로로 설정되어 있음)
2. 작업 스케줄러(Task Scheduler) 실행 → "작업 만들기" (기본 작업 아님, "작업 만들기"로 세부 옵션 설정)
3. **일반** 탭
   - 이름: `YoutubeWeeklySummary`
   - "사용자가 로그온했는지 여부에 관계없이 실행" 선택 (선택 시 암호 입력 필요)
4. **트리거** 탭 → 새로 만들기
   - 매주, 원하는 요일/시간 지정 (예: 매주 월요일 오전 9시)
5. **동작** 탭 → 새로 만들기
   - 프로그램/스크립트: `C:\Users\USer\OneDrive\문서\Python_Program\youtube_summary\run_weekly.bat`
   - (시작 위치는 비워도 무방 — `run_weekly.bat` 내부에서 절대경로만 사용)
6. **조건** 탭
   - 절전 중 PC를 깨워 작업 실행: 체크 (dart_analysis_app 프로젝트에서 절전 미실행 이슈가 있었으므로 권장)
7. **설정** 탭
   - "요청된 실행이 이미 실행 중이면 새 인스턴스 시작 안 함" 선택
   - 작업 실패 시 다시 시작 옵션 등 필요에 따라 설정
8. 저장 후 우클릭 → "실행"으로 1회 테스트, `logs\run_weekly.log`에 `SUCCESS`가 기록되는지 확인

> `run_weekly.bat`은 종료 코드를 그대로 반환하므로, 작업 스케줄러의 "마지막 실행 결과" 항목으로
> 성공/실패를 바로 확인할 수 있습니다. 로그 마커는 한글 인코딩 깨짐을 피하기 위해 영문(`START`/`SUCCESS`/`FAILURE`)을 사용합니다.

## YouTube Data API 쿼터 사용량 추정

기본 일일 쿼터는 **10,000 units**이며, 이 앱이 사용하는 호출은 모두 저비용(각 1 unit)입니다
(`search.list`처럼 100 units가 드는 호출은 사용하지 않음).

채널 1개당 실행 1회 기준:
| 호출 | 비용 | 비고 |
|---|---|---|
| `channels.list` | 1 unit | 업로드 재생목록 ID 조회 |
| `playlistItems.list` | 1 unit (페이지당) | 보통 주간 업로드가 50개 미만이면 1페이지 |
| `videos.list` | 1 unit (50개 배치당) | 조회수 등 통계 조회 |

→ **채널당 약 3 units**, 채널 20개 등록 시 **주간 실행당 약 60 units** (10,000 units의 0.6% 수준).
채널 수가 100개로 늘어나도 약 300 units로, 일일 한도에 전혀 무리가 없습니다.

## Gemini API 비용 추정

`summarizer.py`는 `gemini-flash-latest` 모델(항상 최신 안정 Flash 모델을 가리키는 별칭)을 사용합니다.
Google AI Studio에서 발급한 키는
기본적으로 **무료 티어(Free tier)**로 시작하며, 분당/일일 요청 수 제한 내에서는 과금되지 않습니다
([Gemini API 가격 정책](https://ai.google.dev/gemini-api/docs/pricing) 확인 권장 — 무료 티어 한도를
초과하거나 유료 티어로 전환하면 입력/출력 토큰당 과금이 발생합니다).

채널 수가 많아 무료 티어의 분당 요청 한도(RPM)를 초과할 경우 요청이 일시적으로 실패할 수 있으니,
채널이 많다면 `--top-n`을 줄이거나 실행 간격을 늘리는 것을 고려하세요.

> faster-whisper 폴백 자체는 로컬 실행이므로 API 비용이 들지 않습니다 (CPU 시간만 소요).

## 참고

- 자막이 없는 영상은 자동으로 faster-whisper 폴백을 시도합니다. CPU 환경에서는 영상 길이에 따라
  전사(transcribe)에 수 분이 소요될 수 있습니다.
- `logs/youtube_summary.log`에 실행 상세 로그가 누적됩니다 (앱 내부 Python 로깅).
- `logs/run_weekly.log`에는 작업 스케줄러 실행 결과(START/SUCCESS/FAILURE)가 누적됩니다 (`run_weekly.bat`).
