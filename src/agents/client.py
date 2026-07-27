"""
Bedrock Converse API client with tool-use loop and retry logic.
"""

import logging
import time

import boto3
from botocore.exceptions import ClientError

from src.config import get_settings
from src.tools.executor import ToolExecutor

log = logging.getLogger("memory-agent")

# Retryable Bedrock errors
RETRYABLE_ERRORS = ("ModelErrorException", "ThrottlingException", "ModelTimeoutException")
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry


class BedrockClient:
    """Wraps the Bedrock Converse API with automatic tool-use handling and retries."""

    def __init__(self, tool_executor: ToolExecutor):
        settings = get_settings()
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self._model_id = settings.bedrock_model_id
        self._max_tokens = settings.max_tokens
        self._max_rounds = settings.max_tool_rounds
        self._tool_executor = tool_executor

    def invoke(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
        content_blocks: list[dict] | None = None,
    ) -> str:
        """
        Invoke Bedrock Converse with a full tool-use loop.

        Automatically retries on transient errors (ModelErrorException,
        ThrottlingException) with exponential backoff.

        Args:
            system_prompt: The system prompt for this agent type.
            user_message: The user's text message.
            tools: Tool specs available to the model.
            content_blocks: Optional additional content (images, documents).

        Returns:
            The model's final text response.
        """
        # Build initial user content
        user_content = [{"text": user_message}]
        if content_blocks:
            user_content.extend(content_blocks)

        messages = [{"role": "user", "content": user_content}]

        for round_num in range(self._max_rounds):
            response = self._call_with_retry(system_prompt, messages, tools)

            if response is None:
                return "Error: Bedrock API call failed after retries."

            output = response["output"]["message"]
            messages.append(output)
            stop_reason = response["stopReason"]

            if stop_reason == "tool_use":
                tool_results = self._handle_tool_calls(output["content"])
                messages.append({"role": "user", "content": tool_results})
            else:
                # Model finished - extract text response
                text_parts = [b["text"] for b in output["content"] if "text" in b]
                return " ".join(text_parts) if text_parts else "Done."

        return "Max tool rounds exceeded."

    def _call_with_retry(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
    ) -> dict | None:
        """Call Bedrock Converse with retry on transient errors."""
        kwargs = {
            "modelId": self._model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "inferenceConfig": {"maxTokens": self._max_tokens},
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}

        for attempt in range(MAX_RETRIES):
            try:
                return self._client.converse(**kwargs)

            except ClientError as e:
                error_code = e.response["Error"]["Code"]

                if error_code in RETRYABLE_ERRORS:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    log.warning(
                        f"⚠️  {error_code} (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    # Non-retryable error
                    log.error(f"Bedrock API error: {e}")
                    return None

            except Exception as e:
                log.error(f"Unexpected error: {e}")
                return None

        log.error(f"Bedrock API failed after {MAX_RETRIES} retries")
        return None

    def _handle_tool_calls(self, content_blocks: list[dict]) -> list[dict]:
        """Process tool calls from the model response."""
        tool_results = []
        for block in content_blocks:
            if "toolUse" in block:
                tool_call = block["toolUse"]
                tool_name = tool_call["name"]
                tool_input = tool_call["input"]

                log.info(f"🔧 Tool call: {tool_name}")
                result = self._tool_executor.execute(tool_name, tool_input)

                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_call["toolUseId"],
                        "content": [{"json": result}],
                    }
                })
        return tool_results

    def invoke_stream(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict],
    ):
        """
        Invoke Bedrock ConverseStream for streaming token output.

        Handles tool use internally (tools executed between rounds,
        only final text is streamed).

        Yields:
            str: Text chunks as they are generated.
        """
        import json as json_mod

        user_content = [{"text": user_message}]
        messages = [{"role": "user", "content": user_content}]

        for round_num in range(self._max_rounds):
            kwargs = {
                "modelId": self._model_id,
                "system": [{"text": system_prompt}],
                "messages": messages,
                "inferenceConfig": {"maxTokens": self._max_tokens},
            }
            if tools:
                kwargs["toolConfig"] = {"tools": tools}

            try:
                response = self._client.converse_stream(**kwargs)
            except Exception as e:
                log.error(f"Stream error: {e}")
                yield f"Error: {e}"
                return

            # Process stream events
            tool_use_blocks = []
            current_tool_use = None
            tool_input_json = ""
            has_tool_use = False
            text_buffer = []

            for event in response["stream"]:
                if "contentBlockStart" in event:
                    start = event["contentBlockStart"].get("start", {})
                    if "toolUse" in start:
                        has_tool_use = True
                        current_tool_use = {
                            "toolUseId": start["toolUse"]["toolUseId"],
                            "name": start["toolUse"]["name"],
                        }
                        tool_input_json = ""

                elif "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"]["delta"]
                    if "text" in delta:
                        yield delta["text"]
                        text_buffer.append(delta["text"])
                    elif "toolUse" in delta:
                        tool_input_json += delta["toolUse"].get("input", "")

                elif "contentBlockStop" in event:
                    if current_tool_use:
                        try:
                            current_tool_use["input"] = json_mod.loads(tool_input_json) if tool_input_json else {}
                        except (json_mod.JSONDecodeError, ValueError):
                            current_tool_use["input"] = {}
                        tool_use_blocks.append(current_tool_use)
                        current_tool_use = None

            if has_tool_use and tool_use_blocks:
                # Build assistant message
                assistant_content = []
                if text_buffer:
                    assistant_content.append({"text": "".join(text_buffer)})
                for tu in tool_use_blocks:
                    assistant_content.append({"toolUse": tu})
                messages.append({"role": "assistant", "content": assistant_content})

                # Execute tools and continue
                log.info(f"🔧 Stream tool calls: {[t['name'] for t in tool_use_blocks]}")
                tool_results = []
                for tu in tool_use_blocks:
                    result = self._tool_executor.execute(tu["name"], tu["input"])
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tu["toolUseId"],
                            "content": [{"json": result}],
                        }
                    })
                messages.append({"role": "user", "content": tool_results})
            else:
                return
