import json
from typing import Any, AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
from app.config import settings
from app.logging import logger


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = base_url or settings.AI_BASE_URL
        self.api_key = api_key or settings.AI_API_KEY or "not-needed-for-mock"
        self.model = model or settings.AI_MODEL

        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams completion and normalizes token deltas and tool-call chunks.
        """
        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": True,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            stream = await self.client.chat.completions.create(**kwargs)

            current_tool_calls: Dict[int, Dict[str, Any]] = {}

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Stream text chunks
                if delta.content:
                    yield {"type": "text_delta", "content": delta.content}

                # Accumulate tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index if tc.index is not None else 0
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or f"call_{idx}",
                                "name": tc.function.name if tc.function and tc.function.name else "",
                                "arguments": "",
                                "extra_content": None,
                            }
                        if tc.id and not current_tool_calls[idx]["id"]:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            current_tool_calls[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            current_tool_calls[idx]["arguments"] += tc.function.arguments
                        if hasattr(tc, "extra_content") and tc.extra_content:
                            current_tool_calls[idx]["extra_content"] = tc.extra_content

            # Yield accumulated complete tool calls if any
            for idx, tc_data in current_tool_calls.items():
                parsed_args = {}
                try:
                    if tc_data["arguments"]:
                        parsed_args = json.loads(tc_data["arguments"])
                except Exception as e:
                    logger.warning(f"Could not parse tool call arguments '{tc_data['arguments']}': {e}")

                yield {
                    "type": "tool_call",
                    "id": tc_data["id"],
                    "name": tc_data["name"],
                    "arguments": parsed_args,
                    "extra_content": tc_data.get("extra_content"),
                }

            yield {"type": "finish"}

        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
            yield {"type": "error", "error": str(e)}
