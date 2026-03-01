import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from news_bot import DailyNewsBot, load_config

logger = logging.getLogger(__name__)


class BotRuntime:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._bot: Optional[DailyNewsBot] = None

    def start(self) -> None:
        config = load_config()
        self._bot = DailyNewsBot(config)
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        logger.info("FastAPI scheduler started (hourly)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("FastAPI scheduler stopped")

    def run_once(self) -> None:
        if self._bot is None:
            raise RuntimeError("Bot is not initialized")
        with self._lock:
            self._bot.run_once()

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            wait_seconds = self._seconds_until_next_hour(datetime.now())
            if self._stop_event.wait(timeout=wait_seconds):
                break

            try:
                logger.info("Hourly scheduler triggered")
                self.run_once()
            except Exception:
                logger.exception("Scheduled run failed")

    @staticmethod
    def _seconds_until_next_hour(now: datetime) -> int:
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        return max(1, int((next_hour - now).total_seconds()))


app = FastAPI(title="Daily News Bot API", version="1.0.0")
router = APIRouter(prefix="/news", tags=["news"])
runtime = BotRuntime()


INDEX_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Daily News Bot 테스트</title>
  <style>
    body { font-family: sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
    .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    button, a { font-size: 0.95rem; padding: 0.5rem 0.8rem; border-radius: 8px; border: 1px solid #d1d5db; background: #fff; cursor: pointer; }
    a { text-decoration: none; color: inherit; display: inline-block; }
    pre { background: #111827; color: #e5e7eb; padding: 1rem; border-radius: 10px; overflow: auto; }
    .hint { color: #4b5563; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Daily News Bot API 테스트</h1>
  <p class="hint">Swagger UI와 간단한 버튼 테스트를 함께 사용할 수 있습니다.</p>

  <div class="actions">
    <a href="/docs" target="_blank" rel="noopener noreferrer">Swagger 열기 (/docs)</a>
    <button onclick="callApi('/news/health', 'GET')">헬스체크</button>
    <button onclick="callApi('/news/run', 'POST')">뉴스 수동 실행</button>
  </div>

  <h2>응답</h2>
  <pre id="output">아직 호출되지 않았습니다.</pre>

  <script>
    async function callApi(path, method) {
      const output = document.getElementById('output');
      output.textContent = '요청 중...';
      try {
        const response = await fetch(path, { method });
        const text = await response.text();
        output.textContent = `${method} ${path}\nstatus: ${response.status}\n\n${text}`;
      } catch (err) {
        output.textContent = `요청 실패: ${err}`;
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, tags=["ui"])
def index_page():
    return INDEX_HTML


@router.post("/run")
def run_news_now():
    try:
        runtime.run_once()
        return {"status": "ok", "message": "뉴스 수집/요약/전송 작업이 실행되었습니다."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"실행 실패: {exc}") from exc


@router.get("/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():
    runtime.start()


@app.on_event("shutdown")
def on_shutdown():
    runtime.stop()


app.include_router(router)
