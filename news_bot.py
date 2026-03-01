import argparse
import html
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


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


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: Optional[datetime]
    content: str


class NewsCollector:
    def __init__(self, request_timeout: int):
        self.request_timeout = request_timeout

    def collect_from_feeds(self, feeds: Iterable[str], top_n: int) -> List[NewsItem]:
        all_items: List[NewsItem] = []

        for feed_url in feeds:
            logger.info("RSS 수집 시작: %s", feed_url)
            parsed = feedparser.parse(feed_url)

            for entry in parsed.entries[: top_n * 2]:
                title = self._safe(entry.get("title", "제목 없음"))
                link = entry.get("link", "")
                source = self._safe(self._extract_source(parsed, entry))
                published = self._extract_datetime(entry)
                summary = self._safe(entry.get("summary", ""))

                if not link:
                    continue

                body = self._fetch_article_text(link) or summary
                item = NewsItem(
                    title=title,
                    link=link,
                    source=source,
                    published=published,
                    content=body,
                )
                all_items.append(item)

        unique_items = self._deduplicate_by_title(all_items)
        unique_items.sort(
            key=lambda item: item.published or datetime.min,
            reverse=True,
        )

        return unique_items[:top_n]

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
    def _extract_datetime(entry) -> Optional[datetime]:
        for key in ["published", "updated", "created"]:
            value = entry.get(key)
            if value:
                try:
                    return parsedate_to_datetime(value)
                except Exception:
                    continue
        return None

    def _fetch_article_text(self, url: str) -> str:
        try:
            resp = requests.get(url, timeout=self.request_timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("기사 본문 수집 실패: %s (%s)", url, exc)
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        article_tag = soup.find("article")
        if article_tag:
            text = article_tag.get_text(" ", strip=True)
        else:
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            text = " ".join(p for p in paragraphs if len(p) > 20)

        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]

    @staticmethod
    def _deduplicate_by_title(items: List[NewsItem]) -> List[NewsItem]:
        seen = set()
        result = []
        for item in items:
            norm = re.sub(r"\s+", " ", item.title.lower()).strip()
            if norm in seen:
                continue
            seen.add(norm)
            result.append(item)
        return result


class NewsSummarizer:
    def __init__(self, sentence_count: int):
        self.sentence_count = sentence_count

    def summarize(self, text: str) -> str:
        if not text:
            return "요약할 본문이 없어 제목 중심으로 확인이 필요합니다."

        sentences = self._split_sentences(text)
        if len(sentences) <= self.sentence_count:
            return " ".join(sentences)

        word_scores = self._word_frequency(text)
        ranked = sorted(
            sentences,
            key=lambda sent: self._sentence_score(sent, word_scores),
            reverse=True,
        )
        selected = ranked[: self.sentence_count]

        ordered = [s for s in sentences if s in selected]
        return " ".join(ordered)

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        chunks = re.split(r"(?<=[.!?다])\s+", text)
        return [c.strip() for c in chunks if len(c.strip()) > 20]

    @staticmethod
    def _word_frequency(text: str):
        words = re.findall(r"[가-힣A-Za-z]{2,}", text.lower())
        freq = {}
        for word in words:
            if word in STOPWORDS:
                continue
            freq[word] = freq.get(word, 0) + 1
        return freq

    @staticmethod
    def _sentence_score(sentence: str, freq_map: dict) -> float:
        words = re.findall(r"[가-힣A-Za-z]{2,}", sentence.lower())
        if not words:
            return 0.0
        score = sum(freq_map.get(w, 0) for w in words)
        return score / len(words)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: int):
        self.chat_id = chat_id
        self.timeout = timeout
        self.endpoint = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, message: str):
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(self.endpoint, json=payload, timeout=self.timeout)
        resp.raise_for_status()


class DailyNewsBot:
    def __init__(self, config: Config):
        self.config = config
        self.collector = NewsCollector(config.request_timeout)
        self.summarizer = NewsSummarizer(config.summary_sentences)
        self.notifier = TelegramNotifier(
            config.telegram_bot_token,
            config.telegram_chat_id,
            config.request_timeout,
        )

    def run_once(self):
        logger.info("뉴스 수집/요약 작업 시작")
        news_items = self.collector.collect_from_feeds(self.config.rss_feeds, self.config.top_n)

        if not news_items:
            logger.warning("수집된 뉴스가 없어 알림을 전송하지 않습니다.")
            return

        message = self._build_message(news_items)
        self.notifier.send(message)
        logger.info("텔레그램 전송 완료 (%d건)", len(news_items))

    def run_daemon(self):
        logger.info(
            "데몬 모드 시작: 매일 %02d:%02d 실행",
            self.config.send_hour,
            self.config.send_minute,
        )

        while True:
            now = datetime.now()
            if now.hour == self.config.send_hour and now.minute == self.config.send_minute:
                try:
                    self.run_once()
                except Exception:
                    logger.exception("실행 중 오류 발생")
                time.sleep(61)
            else:
                time.sleep(20)

    def _build_message(self, items: List[NewsItem]) -> str:
        date_label = datetime.now().strftime("%Y-%m-%d")
        parts = [f"<b>🗞️ {date_label} 아침 핵심 뉴스 브리핑</b>"]

        for idx, item in enumerate(items, start=1):
            summary = self.summarizer.summarize(item.content)
            source = html.escape(item.source)
            title = html.escape(item.title)
            link = html.escape(item.link)
            parts.append(
                f"\n<b>{idx}. [{source}] {title}</b>\n"
                f"- 요약: {html.escape(summary)}\n"
                f"- 링크: {link}"
            )

        parts.append("\n#자동브리핑 #뉴스요약")
        return "\n".join(parts)[:3900]


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    feed_str = os.getenv("RSS_FEEDS", "").strip()

    if not token or not chat_id or not feed_str:
        raise ValueError("필수 환경변수(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RSS_FEEDS)를 설정하세요.")

    feeds = [f.strip() for f in feed_str.split(",") if f.strip()]

    return Config(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        rss_feeds=feeds,
        send_hour=int(os.getenv("SEND_HOUR", "7")),
        send_minute=int(os.getenv("SEND_MINUTE", "30")),
        top_n=int(os.getenv("TOP_N", "8")),
        summary_sentences=int(os.getenv("SUMMARY_SENTENCES", "2")),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "12")),
    )


def parse_args():
    parser = argparse.ArgumentParser(description="아침 뉴스 스크래핑 + 요약 + 텔레그램 전송 봇")
    parser.add_argument(
        "--once",
        action="store_true",
        help="1회 실행 후 종료 (테스트/cron 용도)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()
    bot = DailyNewsBot(config)

    if args.once:
        bot.run_once()
    else:
        bot.run_daemon()


if __name__ == "__main__":
    main()
