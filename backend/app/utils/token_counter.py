"""Token counting utilities using tiktoken.

Uses cl100k_base encoding which is compatible with GPT-4 and qwen3.6-plus.
"""

import tiktoken
from typing import Optional

# Default encoding for GPT-4 and qwen3.6-plus
_ENCODING = "cl100k_base"

# Default context window limit
DEFAULT_TOKEN_LIMIT = 8000

# Warning threshold (80% of limit)
WARNING_THRESHOLD = 0.8


def _get_encoder() -> tiktoken.Encoding:
    """Get the tiktoken encoder (cached)."""
    return tiktoken.get_encoding(_ENCODING)


def count_tokens(messages: list[dict]) -> int:
    """Count total tokens in a list of messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
                  Example: [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]

    Returns:
        Total token count for all messages combined.
    """
    if not messages:
        return 0

    encoder = _get_encoder()
    total_tokens = 0

    for message in messages:
        content = message.get("content", "")
        role = message.get("role", "")

        # Count tokens for content
        total_tokens += len(encoder.encode(content, allowed_special="all"))

        # Add overhead for message formatting (approximately 4 tokens per message)
        # This accounts for role tags and message structure
        total_tokens += 4

    # Add overhead for chat template (approximately 3 tokens)
    total_tokens += 3

    return total_tokens


def is_within_limit(messages: list[dict], limit: int = DEFAULT_TOKEN_LIMIT) -> bool:
    """Check if messages are within the token limit.

    Args:
        messages: List of message dicts.
        limit: Maximum token limit (default: 8000).

    Returns:
        True if token count is within limit, False otherwise.
    """
    return count_tokens(messages) <= limit


def get_warning_threshold(
    messages: list[dict], limit: int = DEFAULT_TOKEN_LIMIT
) -> float:
    """Get the current capacity as a ratio (0.0 to 1.0).

    Args:
        messages: List of message dicts.
        limit: Maximum token limit (default: 8000).

    Returns:
        Token count as a ratio of the limit (0.0 to 1.0+).
        Returns 1.0+ if over limit.
    """
    token_count = count_tokens(messages)
    return token_count / limit


def is_approaching_limit(
    messages: list[dict], limit: int = DEFAULT_TOKEN_LIMIT
) -> bool:
    """Check if messages are approaching the limit (above 80% threshold).

    Args:
        messages: List of message dicts.
        limit: Maximum token limit (default: 8000).

    Returns:
        True if token count exceeds 80% of limit, False otherwise.
    """
    return get_warning_threshold(messages, limit) >= WARNING_THRESHOLD
