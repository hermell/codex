# Daily News Telegram Bot (Python)

매일 아침 지정한 시간에 RSS 기반으로 주요 뉴스를 수집하고, 간단 요약을 만든 뒤 텔레그램으로 전송하는 자동화 프로그램입니다.

## 아키텍처 설계

1. **수집(Collector)**
   - 여러 RSS 피드를 순회
   - 뉴스 링크를 따라 본문(가능한 경우)까지 추가 수집
   - 제목 중복 제거
2. **요약(Summarizer)**
   - 문장 분리 후 단어 빈도 기반 점수화
   - 상위 문장을 선택해 요약문 생성
3. **전송(Notifier)**
   - 텔레그램 Bot API `sendMessage`로 브리핑 전송
4. **스케줄러(Bot Runner)**
   - 데몬 모드: 매일 지정 시각 실행
   - 단발 모드: `--once`로 즉시 1회 실행 (테스트/cron)

## 파일 구성

- `news_bot.py`: 전체 실행 코드
- `.env.example`: 환경변수 템플릿
- `requirements.txt`: 의존성 목록

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

`.env`를 수정하세요.

- `TELEGRAM_BOT_TOKEN`: BotFather에서 발급
- `TELEGRAM_CHAT_ID`: 받는 채팅 ID
- `RSS_FEEDS`: 콤마로 구분한 RSS URL 목록
- `SEND_HOUR`, `SEND_MINUTE`: 매일 실행 시각
- `TOP_N`: 전송할 기사 개수
- `SUMMARY_SENTENCES`: 기사당 요약 문장 개수

## 실행

### 1) 테스트용 단발 실행

```bash
python news_bot.py --once
```

### 2) 데몬 실행

```bash
python news_bot.py
```

> 프로덕션에서는 systemd 또는 Docker + restart 정책으로 상시 실행을 권장합니다.

## 운영 팁

- RSS 피드를 너무 많이 넣으면 지연/차단 가능성이 증가합니다.
- 기사 본문 수집이 막히는 사이트가 있으므로 RSS `summary`를 fallback으로 사용합니다.
- 텔레그램 메시지는 4096자 제한이 있어 프로그램 내부에서 길이를 제한합니다.

## 향후 고도화 아이디어

- OpenAI API 연동으로 더 자연스러운 요약 생성
- 키워드 기반(경제/AI/정책 등) 섹션 분류
- DB 저장(중복 방지/이력 관리)
- 장애 알림(실패 시 별도 텔레그램 채널 전송)
