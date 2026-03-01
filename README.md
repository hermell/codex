# Daily News Telegram Bot (Python + FastAPI)

매일 아침/정시 기준으로 RSS 주요 뉴스를 수집하고 요약한 뒤 텔레그램으로 전송하는 자동화 프로그램입니다.

## 변경 사항 (FastAPI + 스케줄러)

- 기존 핵심 로직(`news_bot.py`)은 유지
- `fastapi_app.py` 추가
  - 서버 기동 시 백그라운드 스케줄러 시작
  - **매 1시간 단위**로 `run_once()` 실행
  - 라우터 요청으로 수동 실행 가능 (`POST /news/run`)

## 아키텍처

1. **핵심 도메인 로직 (`news_bot.py`)**
   - RSS 수집, 본문 스크래핑, 요약, 텔레그램 전송
   - 상태 파일 기반 중복 전송 방지
2. **API 레이어 (`fastapi_app.py`)**
   - FastAPI 라우팅
   - 백그라운드 스케줄러(시간 단위)
   - 외부 트리거 엔드포인트

## 파일 구성

- `news_bot.py`: 핵심 뉴스 처리 로직
- `fastapi_app.py`: FastAPI 앱 + 시간 단위 스케줄러 + 라우터
- `.env.example`: 환경변수 템플릿
- `requirements.txt`: 의존성
- `tests/test_news_bot.py`: 기존 단위 테스트

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 설정

```bash
cp .env.example .env
```

`.env` 주요 항목:

- `TELEGRAM_BOT_TOKEN`: BotFather에서 발급
- `TELEGRAM_CHAT_ID`: 수신 채팅 ID
- `RSS_FEEDS`: 콤마로 구분된 RSS 목록
- `TOP_N`: 전송 기사 수
- `SUMMARY_SENTENCES`: fallback 요약 문장 수(Gemini 실패 시 사용)
- `GEMINI_API_KEY`: Google Gemini API 키 (필수)
- `GEMINI_MODEL`: Gemini 모델명 (기본값: `gemini-1.5-flash`)
- `MIN_CONTENT_LENGTH`: 본문 최소 길이(짧으면 summary fallback)
- `STATE_FILE`: 중복 전송 방지 상태 파일 위치

## 실행

### 1) FastAPI 서버 실행 (권장)

```bash
uvicorn fastapi_app:app --host 0.0.0.0 --port 8000
```

### 2) 수동 실행 엔드포인트

```bash
curl -X POST http://localhost:8000/news/run
```

### 3) 헬스체크

```bash
curl http://localhost:8000/news/health
```

### 4) Swagger에서 API 테스트

- 브라우저에서 `http://localhost:8000/docs` 접속
- `POST /news/run` 또는 `GET /news/health`를 펼친 뒤 `Try it out` → `Execute`

### 5) 간단한 index 테스트 페이지

- 브라우저에서 `http://localhost:8000/` 접속
- 화면 버튼으로 헬스체크/수동 실행 테스트
- 같은 화면에서 Swagger 링크(`/docs`)로 이동 가능

## 참고

- 서버가 켜져 있는 동안 백그라운드에서 1시간마다 자동 실행됩니다.
- 기존 `python news_bot.py --once` 방식도 그대로 사용 가능합니다.
