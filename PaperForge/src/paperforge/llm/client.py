"""DeepSeek API client with retry and error handling."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from paperforge.config import LLMConfig

logger = logging.getLogger(__name__)

# Default base URL if env var not set
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


class LLMClient:
    """OpenAI-compatible API client for DeepSeek."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key
        self.base_url = config.base_url or DEFAULT_BASE_URL
        self.model = config.model
        self.timeout = config.timeout_seconds
        self.max_retries = config.max_retries

        if not self.api_key:
            raise ValueError(
                f"API key not found. Set the {config.api_key_env} environment variable."
            )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Call the chat completion API with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name (defaults to config.model).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            response_format: Response format, e.g. {"type": "json_object"}.

        Returns:
            API response dict.

        Raises:
            RuntimeError: After all retries exhausted.
        """
        import urllib.request
        import urllib.error

        model = model or self.model
        url = f"{self.base_url}/chat/completions"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)

            except urllib.error.HTTPError as e:
                body_text = ""
                try:
                    body_text = e.read().decode("utf-8")
                except Exception:
                    pass
                last_error = f"HTTP {e.code}: {body_text}"
                logger.warning(
                    "LLM API error (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, last_error,
                )
                # Don't retry on client errors (4xx except 429)
                if e.code == 429 or e.code >= 500:
                    wait = 2 ** attempt
                    time.sleep(wait)
                elif e.code < 500:
                    raise RuntimeError(f"LLM API client error: {last_error}")

            except urllib.error.URLError as e:
                last_error = f"URL error: {e.reason}"
                logger.warning(
                    "LLM API error (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, last_error,
                )
                wait = 2 ** attempt
                time.sleep(wait)

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "LLM API error (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, last_error,
                )
                wait = 2 ** attempt
                time.sleep(wait)

        raise RuntimeError(f"LLM API failed after {self.max_retries} retries: {last_error}")
