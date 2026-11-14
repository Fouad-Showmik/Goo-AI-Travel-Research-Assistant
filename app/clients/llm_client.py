import logging
from typing import Any

import requests

from app.core.config import settings

# talk to the provider over HTTP and return raw JSON.

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    pass


class LLMClient:
    def __init__(self):
        self.url = f"{settings.llm_base_url}/responses"
        self.headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def complete(
        self,
        input_items: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool = False,
    ):
        payload = {
            "model": settings.model_name,
            "input": input_items,
        }

        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
            payload["parallel_tool_calls"] = parallel_tool_calls

        try:
            response = requests.post(
                self.url, headers=self.headers, json=payload, timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.HTTPError as exc:
            response = exc.response

            status_code = response.status_code if response is not None else "unknown"

            try:
                error_details = response.json().get("error", {})
            except (ValueError, AttributeError):
                error_details = (
                    response.text[:1500] if response is not None else "No response body"
                )

            logger.error(
                "OpenAI API returned HTTP %s: %s",
                status_code,
                error_details,
            )

            raise LLMClientError(f"OpenAI API request failed: {error_details}") from exc

        except requests.RequestException as exc:
            logger.exception("LLM request failed")
            raise LLMClientError(str(exc)) from exc

        except ValueError as exc:
            logger.exception("LLM returned an invalid JSON response")
            raise LLMClientError("LLM returned an invalid response.") from exc
