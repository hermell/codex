# Daily News Telegram Bot (Python)

매일 아침 지정한 시간에 RSS 기반 주요 뉴스를 수집하고, 요약한 뒤 텔레그램으로 전송하는 자동화 프로그램입니다.

## 개선된 설계 포인트

1. **수집 안정성 강화**
   - RSS 다중 수집 + 기사 본문 스크래핑
   - 본문 길이가 짧으면 RSS summary 자동 fallback
   - 제목 기준 중복 제거
2. **중복 전송 방지(state 관리)**
   - `STATE_FILE`에 이미 보낸 링크를 저장
   - 재시작 후에도 동일 기사 재전송 방지
3. **전송 안정성 강화**
   - 텔레그램 메시지 길이 제한 대응(자동 분할 전송)
4. **스케줄 안전성 강화**
   - 같은 날짜에 중복 실행되지 않도록 last-run 체크
5. **테스트 추가**
   - 요약/메시지 분할/설정 로딩 단위 테스트 포함

## 파일 구성

- `news_bot.py`: 봇 실행 코드
- `.env.example`: 환경변수 템플릿
- `requirements.txt`: 의존성
- `tests/test_news_bot.py`: 단위 테스트

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
- `SEND_HOUR`, `SEND_MINUTE`: 전송 시각
- `TOP_N`: 전송 기사 수
- `SUMMARY_SENTENCES`: 요약 문장 수
- `MIN_CONTENT_LENGTH`: 본문 최소 길이(짧으면 summary fallback)
- `STATE_FILE`: 중복 전송 방지 상태 파일 위치

## 실행

### 1) 테스트용 1회 실행

```bash
python news_bot.py --once
```

### 2) 데몬 실행

```bash
python news_bot.py
```

## 테스트

```bash
python -m unittest tests/test_news_bot.py
```

## 운영 권장사항

- 실제 운영은 systemd 또는 Docker restart 정책 사용 권장
- RSS 소스는 2~5개로 시작 후 점진 확장 권장
- 추후 OpenAI API 연결 시 요약 품질을 크게 개선할 수 있습니다
