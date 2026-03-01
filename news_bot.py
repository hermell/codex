import argparse
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MAX_TELEGRAM_LEN = 3900
DEFAULT_KST = timezone(timedelta(hours=9))

STOPWORDS = {
    "그리고",
    "하지만",
    "그러나",
    "또한",
    "대한",
    "관련",
    "있다",
    "한다",
    "있는",
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "have",
    "will",
    "are",
    "was",
}


@dataclass
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    rss_feeds: List[str]
    send_hour: int
    send_minute: int
    top_n: int
    summary_sentences: int
    request_timeout: int
    timezone_name: str
    min_content_length: int
    state_file: str


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: datetime
    content: str


class RunState:
    def __init__(self, state_file: str):
        self.path = Path(state_file)
        self.seen_links = set()
        self.last_run_date = ""

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.seen_links = set(data.get("seen_links", []))
            self.last_run_date = data.get("last_run_date", "")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("state 파일 로드 실패, 신규 state로 시작합니다: %s", exc)

    def save(self) -> None:
        payload = {
            "seen_links": sorted(self.seen_links)[-1000:],
            "last_run_date": self.last_run_date,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class NewsCollector:
    def __init__(self, request_timeout: int, min_content_length: int):
        self.request_timeout = request_timeout
        self.min_content_length = min_content_length

    def collect_from_feeds(self, feeds: Iterable[str], top_n: int, seen_links: set) -> List[NewsItem]:
        all_items: List[NewsItem] = []

        for feed_url in feeds:
            logger.info("RSS 수집 시작: %s", feed_url)
            parsed = feedparser.parse(feed_url)
            feed_entries = getattr(parsed, "entries", [])

            for entry in feed_entries[: top_n * 5]:
                item = self._parse_entry(parsed, entry)
                if not item:
                    continue
                if item.link in seen_links:
                    continue
                all_items.append(item)

        unique_items = self._deduplicate_by_title(all_items)
        unique_items.sort(key=lambda item: item.published, reverse=True)
        return unique_items[:top_n]

    def _parse_entry(self, parsed_feed, entry) -> Optional[NewsItem]:
        title = self._safe(entry.get("title", "제목 없음"))
        link = entry.get("link", "").strip()
        if not link:
            return None

        source = self._safe(self._extract_source(parsed_feed, entry))
        published = self._extract_datetime(entry)
        summary = self._safe(entry.get("summary", ""))
        body = self._fetch_article_text(link)

        if len(body) < self.min_content_length:
            body = summary or body

        return NewsItem(
            title=title,
            link=link,
            source=source,
            published=published,
            content=body,
        )

    @staticmethod
    def _safe(raw: str) -> str:
        clean = BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
        return html.unescape(clean)

    @staticmethod
    def _extract_source(parsed_feed, entry) -> str:
        if "source" in entry and entry.source:
            return entry.source.get("title", "Unknown")
        if parsed_feed.feed and parsed_feed.feed.get("title"):
            return parsed_feed.feed.get("title")
        return "Unknown"

    @staticmethod
    def _extract_datetime(entry) -> datetime:
        for key in ["published", "updated", "created"]:
            value = entry.get(key)
            if value:
                try:
                    dt = parsedate_to_datetime(value)
                    if dt.tzinfo is None:
                        return dt.replace(tzinfo=DEFAULT_KST)
                    return dt
                except (TypeError, ValueError):
                    continue
        return datetime.now(DEFAULT_KST)

    def _fetch_article_text(self, url: str) -> str:
        try:
            resp = requests.get(
                url,
                timeout=self.request_timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DailyNewsBot/1.0)"},
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("기사 본문 수집 실패: %s (%s)", url, exc)
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        article_tag = soup.find("article")
        if article_tag:
            text = article_tag.get_text(" ", strip=True)
        else:
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            text = " ".join(p for p in paragraphs if len(p) > 30)

        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000]

    @staticmethod
    def _deduplicate_by_title(items: List[NewsItem]) -> List[NewsItem]:
        seen = set()
        result = []
        for item in items:
            normalized = re.sub(r"\s+", " ", item.title.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(item)
        return result


class NewsSummarizer:
    def __init__(self, sentence_count: int):
        self.sentence_count = sentence_count

    def summarize(self, text: str) -> str:
        if not text:
            return "요약할 본문이 없어 제목/원문 확인이 필요합니다."

        sentences = self._split_sentences(text)
        if not sentences:
            trimmed = text[:200]
            return f"본문 길이가 짧아 원문 확인이 필요합니다: {trimmed}..."

        if len(sentences) <= self.sentence_count:
            return " ".join(sentences)

        word_scores = self._word_frequency(text)
        ranked = sorted(
            ((self._sentence_score(sentence, word_scores), sentence) for sentence in sentences),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = {sentence for _, sentence in ranked[: self.sentence_count]}
        ordered = [sentence for sentence in sentences if sentence in selected]
        return " ".join(ordered)

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        chunks = re.split(r"(?<=[.!?다])\s+", text)
        return [chunk.strip() for chunk in chunks if len(chunk.strip()) > 25]

    @staticmethod
    def _word_frequency(text: str) -> Dict[str, int]:
        words = re.findall(r"[가-힣A-Za-z]{2,}", text.lower())
        freq: Dict[str, int] = {}
        for word in words:
            if word in STOPWORDS:
                continue
            freq[word] = freq.get(word, 0) + 1
        return freq

    @staticmethod
    def _sentence_score(sentence: str, freq_map: Dict[str, int]) -> float:
        words = re.findall(r"[가-힣A-Za-z]{2,}", sentence.lower())
        if not words:
            return 0.0
        score = sum(freq_map.get(word, 0) for word in words)
        return score / len(words)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: int):
        self.chat_id = chat_id
        self.timeout = timeout
        self.endpoint = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, message: str) -> None:
        for chunk in self._chunk_message(message):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            resp = requests.post(self.endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()

    @staticmethod
    def _chunk_message(message: str, max_len: int = MAX_TELEGRAM_LEN) -> List[str]:
        if len(message) <= max_len:
            return [message]

        chunks: List[str] = []
        buffer = []
        size = 0
        for line in message.split("\n"):
            line_size = len(line) + 1
            if size + line_size > max_len and buffer:
                chunks.append("\n".join(buffer))
                buffer = [line]
                size = line_size
            else:
                buffer.append(line)
                size += line_size

        if buffer:
            chunks.append("\n".join(buffer))
        return chunks


class DailyNewsBot:
    def __init__(self, config: Config):
        self.config = config
        self.state = RunState(config.state_file)
        self.collector = NewsCollector(config.request_timeout, config.min_content_length)
        self.summarizer = NewsSummarizer(config.summary_sentences)
        self.notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id, config.request_timeout)

    def run_once(self) -> None:
        self.state.load()
        logger.info("뉴스 수집/요약 작업 시작")

        items = self.collector.collect_from_feeds(
            feeds=self.config.rss_feeds,
            top_n=self.config.top_n,
            seen_links=self.state.seen_links,
        )

        if not items:
            logger.warning("신규 뉴스가 없어 알림을 전송하지 않습니다.")
            return

        message = self._build_message(items)
        self.notifier.send(message)

        for item in items:
            self.state.seen_links.add(item.link)
        self.state.last_run_date = self._now().strftime("%Y-%m-%d")
        self.state.save()
        logger.info("텔레그램 전송 완료 (%d건)", len(items))

    def run_daemon(self) -> None:
        logger.info("데몬 모드 시작: 매일 %02d:%02d", self.config.send_hour, self.config.send_minute)

        while True:
            now = self._now()
            today = now.strftime("%Y-%m-%d")
            if self._is_send_time(now) and self.state.last_run_date != today:
                try:
                    self.run_once()
                except Exception:
                    logger.exception("실행 중 오류 발생")
                time.sleep(60)
            else:
                time.sleep(20)

    def _now(self) -> datetime:
        return datetime.now(DEFAULT_KST)

    def _is_send_time(self, now: datetime) -> bool:
        return now.hour == self.config.send_hour and now.minute == self.config.send_minute

    def _build_message(self, items: Sequence[NewsItem]) -> str:
        date_label = self._now().strftime("%Y-%m-%d")
        parts = [f"<b>🗞️ {date_label} 아침 핵심 뉴스 브리핑</b>"]

        for idx, item in enumerate(items, start=1):
            summary = self.summarizer.summarize(item.content)
            published = item.published.astimezone(DEFAULT_KST).strftime("%H:%M")
            source = html.escape(item.source)
            title = html.escape(item.title)
            link = html.escape(item.link, quote=True)

            parts.append(
                f"\n<b>{idx}. [{source}]</b> <a href=\"{link}\">{title}</a>\n"
                f"- 시각: {published}\n"
                f"- 요약: {html.escape(summary)}"
            )

        parts.append("\n#자동브리핑 #뉴스요약")
        return "\n".join(parts)


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    feed_str = os.getenv("RSS_FEEDS", "").strip()

    if not token or not chat_id or not feed_str:
        raise ValueError("필수 환경변수(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RSS_FEEDS)를 설정하세요.")

    feeds = [feed.strip() for feed in feed_str.split(",") if feed.strip()]
    send_hour = int(os.getenv("SEND_HOUR", "7"))
    send_minute = int(os.getenv("SEND_MINUTE", "30"))

    if not (0 <= send_hour <= 23 and 0 <= send_minute <= 59):
        raise ValueError("SEND_HOUR/SEND_MINUTE 값이 올바르지 않습니다.")

    return Config(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        rss_feeds=feeds,
        send_hour=send_hour,
        send_minute=send_minute,
        top_n=int(os.getenv("TOP_N", "8")),
        summary_sentences=int(os.getenv("SUMMARY_SENTENCES", "2")),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "12")),
        timezone_name=os.getenv("TIMEZONE", "Asia/Seoul"),
        min_content_length=int(os.getenv("MIN_CONTENT_LENGTH", "120")),
        state_file=os.getenv("STATE_FILE", ".data/news_state.json"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="아침 뉴스 스크래핑 + 요약 + 텔레그램 전송 봇")
    parser.add_argument("--once", action="store_true", help="1회 실행 후 종료")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    bot = DailyNewsBot(config)

    if args.once:
        bot.run_once()
    else:
        bot.run_daemon()


if __name__ == "__main__":
    main()
