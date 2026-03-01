import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException

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
