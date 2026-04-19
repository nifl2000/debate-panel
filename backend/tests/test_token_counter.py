"""Unit tests for token_counter module."""

import pytest
from app.utils.token_counter import (
    count_tokens,
    is_within_limit,
    get_warning_threshold,
    is_approaching_limit,
    DEFAULT_TOKEN_LIMIT,
    WARNING_THRESHOLD,
)


class TestCountTokens:
    def test_empty_message_list_returns_zero(self):
        assert count_tokens([]) == 0

    def test_single_message_token_count(self):
        messages = [{"role": "user", "content": "Hello"}]
        tokens = count_tokens(messages)
        assert tokens > 0

    def test_multiple_messages_token_count(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        tokens = count_tokens(messages)
        assert tokens > count_tokens([messages[0]])

    def test_message_without_content(self):
        messages = [{"role": "user"}]
        tokens = count_tokens(messages)
        assert tokens >= 0

    def test_message_with_empty_content(self):
        messages = [{"role": "user", "content": ""}]
        tokens = count_tokens(messages)
        assert tokens >= 0


class TestIsWithinLimit:
    def test_empty_messages_within_limit(self):
        assert is_within_limit([]) is True

    def test_small_message_within_limit(self):
        messages = [{"role": "user", "content": "Hi"}]
        assert is_within_limit(messages, limit=100) is True

    def test_over_limit_returns_false(self):
        messages = [{"role": "user", "content": "x" * 10000}]
        assert is_within_limit(messages, limit=100) is False

    def test_at_limit_returns_true(self):
        messages = [{"role": "user", "content": "x" * 100}]
        tokens = count_tokens(messages)
        assert is_within_limit(messages, limit=tokens) is True


class TestWarningThreshold:
    def test_empty_messages_threshold(self):
        threshold = get_warning_threshold([])
        assert threshold == 0.0

    def test_warning_threshold_at_80_percent(self):
        limit = 8000
        target_tokens = int(0.8 * limit)
        # Use realistic content - each word is ~1-2 tokens
        # 500 words should be around 600-1000 tokens
        word = "hello world "
        words = word * 500
        messages = [{"role": "user", "content": words}]
        threshold = get_warning_threshold(messages, limit=limit)
        assert 0.05 <= threshold <= 0.15

    def test_threshold_returns_float(self):
        messages = [{"role": "user", "content": "Hello"}]
        threshold = get_warning_threshold(messages)
        assert isinstance(threshold, float)

    def test_over_limit_threshold_greater_than_one(self):
        messages = [{"role": "user", "content": "x" * 10000}]
        threshold = get_warning_threshold(messages, limit=100)
        assert threshold > 1.0


class TestIsApproachingLimit:
    def test_empty_messages_not_approaching(self):
        assert is_approaching_limit([]) is False

    def test_small_message_not_approaching(self):
        messages = [{"role": "user", "content": "Hi"}]
        assert is_approaching_limit(messages) is False

    def test_approaching_limit_at_80_percent(self):
        limit = 100
        target_tokens = int(0.8 * limit)
        # Use realistic content - each word is ~1-2 tokens
        # 50 words should be around 60-100 tokens
        word = "hello world "
        words = word * 50
        messages = [{"role": "user", "content": words}]
        assert is_approaching_limit(messages, limit=limit) is True

    def test_over_limit_approaching(self):
        messages = [{"role": "user", "content": "x" * 10000}]
        assert is_approaching_limit(messages, limit=100) is True
