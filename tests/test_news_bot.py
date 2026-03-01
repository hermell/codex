import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from news_bot import NewsItem, NewsSummarizer, TelegramNotifier, load_config


class TestNewsSummarizer(unittest.TestCase):
    @patch("news_bot.genai.Client")
    def test_summarize_uses_gemini_with_context_prompt(self, mock_client_cls):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = "핵심 요약 문장 1. 핵심 요약 문장 2."
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        summarizer = NewsSummarizer(
            sentence_count=2,
            api_key="gemini-key",
            model="gemini-1.5-flash",
            request_timeout=5,
        )
        summary = summarizer.summarize("테스트 기사 본문입니다. 중요한 정보가 있습니다.")

        self.assertIn("핵심 요약", summary)
        _, kwargs = mock_client.models.generate_content.call_args
        prompt = kwargs["contents"]
        self.assertIn("[Context]", prompt)
        self.assertIn("2~3문장", prompt)
        self.assertEqual(kwargs["model"], "gemini-1.5-flash")


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
        os.environ["GEMINI_API_KEY"] = "gemini-key"
        os.environ["SEND_HOUR"] = "8"
        os.environ["SEND_MINUTE"] = "10"
        config = load_config()
        self.assertEqual(config.send_hour, 8)
        self.assertEqual(len(config.rss_feeds), 2)
        self.assertEqual(config.gemini_api_key, "gemini-key")


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

    def test_build_message_uses_anchor_title_without_raw_url(self):
        from news_bot import Config, DailyNewsBot

        config = Config(
            telegram_bot_token="token",
            telegram_chat_id="chat",
            rss_feeds=["https://example.com/rss"],
            send_hour=7,
            send_minute=30,
            top_n=1,
            summary_sentences=2,
            request_timeout=5,
            timezone_name="Asia/Seoul",
            min_content_length=120,
            state_file=".data/test_state.json",
            gemini_api_key="gemini-key",
            gemini_model="gemini-1.5-flash",
        )
        bot = DailyNewsBot(config)
        bot.summarizer.summarize = lambda _content: "요약 문장"

        item = NewsItem(
            title="링크 테스트",
            link="https://example.com/a?b=1&c=2",
            source="테스트소스",
            published=datetime.now(timezone.utc),
            content="본문" * 80,
        )

        message = bot._build_message([item])

        self.assertIn('<a href="https://example.com/a?b=1&amp;c=2">링크 테스트</a>', message)
        self.assertNotIn('- 링크:', message)


if __name__ == "__main__":
    unittest.main()
