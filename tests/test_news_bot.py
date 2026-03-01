import os
import unittest
from datetime import datetime, timezone

from news_bot import NewsItem, NewsSummarizer, TelegramNotifier, load_config


class TestNewsSummarizer(unittest.TestCase):
    def test_summarize_returns_top_sentences(self):
        text = (
            "AI 시장이 빠르게 성장하고 있다. "
            "기업들은 AI 인프라 투자 경쟁을 이어가고 있다. "
            "주식 시장은 오늘 보합세를 보였다. "
            "AI 기술 인력 확보가 핵심 과제로 떠올랐다."
        )
        summarizer = NewsSummarizer(sentence_count=2)
        summary = summarizer.summarize(text)
        self.assertIn("AI", summary)
        self.assertGreater(len(summary), 20)


class TestTelegramChunk(unittest.TestCase):
    def test_chunk_message_splits_long_text(self):
        line = "a" * 100
        message = "\n".join([line] * 80)
        chunks = TelegramNotifier._chunk_message(message, max_len=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))


class TestConfigLoad(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_load_config(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "token"
        os.environ["TELEGRAM_CHAT_ID"] = "chat"
        os.environ["RSS_FEEDS"] = "https://a.com/rss,https://b.com/rss"
        os.environ["SEND_HOUR"] = "8"
        os.environ["SEND_MINUTE"] = "10"
        config = load_config()
        self.assertEqual(config.send_hour, 8)
        self.assertEqual(len(config.rss_feeds), 2)


class TestMessageBuild(unittest.TestCase):
    def test_newsitem_dataclass_usage(self):
        item = NewsItem(
            title="제목",
            link="https://example.com",
            source="테스트",
            published=datetime.now(timezone.utc),
            content="긴 기사 본문입니다. " * 30,
        )
        self.assertEqual(item.source, "테스트")


if __name__ == "__main__":
    unittest.main()
