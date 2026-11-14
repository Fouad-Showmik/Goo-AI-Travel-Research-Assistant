# Business Logic
import json
import logging
from time import perf_counter

from app.agent.tool_definitions import TOOL_DEFINITIONS
from app.agent.tool_registry import execute_tool
from app.clients.llm_client import LLMClient, LLMClientError
from app.core.config import settings
from app.schemas.chat import ChatResponse
from app.services.session_store import SessionStore

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, client: LLMClient, store: SessionStore):  # Dependency Injection
        self.client = client
        self.store = store

    def ask(self, session_id: str, user_message: str):
        messages = [
            {"role": "system", "content": settings.system_prompt},
            *self.store.get(session_id),
            {"role": "user", "content": user_message},
        ]

        #Send the user message and avaiable tools to the LLM
         
        data = self.client.complete(
            messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            parallel_tool_calls=False,
            )
        total_tokens = self._get_total_tokens(data)
        

        # Check whether the LLM requested a tool.

        output_items = data.get("output", [])

        tool_calls = [
            item
            for item in output_items
            if item.get("type") == "function_call"
        ]

        if len(tool_calls) > 1:
            raise LLMClientError(
                "Multiple tool calls are not supported yet."
            )

        # Execute the selected tool if requested

        if tool_calls:
            tool_call = tool_calls[0]
            tool_name = tool_call.get("name")
            call_id = tool_call.get("call_id")
            raw_arguments = tool_call.get("arguments")

            if not tool_name or not call_id or not raw_arguments: 
                raise LLMClientError(
                    "LLM returned an incomplete function call."
                )
            try:
                arguments = json.loads(raw_arguments)

            except(json.JSONDecodeError, TypeError) as exc:
                raise LLMClientError(
                     "LLM returned invalid tool arguments."
                ) from exc

            if not isinstance(arguments, dict):
                raise LLMClientError(
                    "Tool arguments must be a JSON object."
                )

            # Execute the registered Python function
            tool_start = perf_counter()

            logger.info(
                "Tool execution started | Tool: %s | Call ID: %s",
                tool_name,
                call_id,
            )

            try:
                tool_result = execute_tool(tool_name, arguments)

                execution_time = perf_counter() - tool_start

                logger.info(
                    "Tool execution completed | Tool: %s | Time: %.2fs",
                    tool_name,
                    execution_time,
                )

            except Exception:
                execution_time = perf_counter() - tool_start

                logger.exception(
                    "Tool execution failed | Tool: %s | Time: %.2fs",
                    tool_name,
                    execution_time,
                )

                tool_result = {
                    "error": (
                        "The requested tool could not retrieve "
                        "the information. Inform the user that "
                        "the operation is temporarily unavailable."
                    )
                }

            # Step 4: Preserve the model's function-call output.
            follow_up_input = [
                *messages,
                *output_items,
                {
                   "type": "function_call_output",
                   "call_id": call_id,
                   "output": json.dumps(
                       tool_result,
                       ensure_ascii=False,
                   ), 
                },
            ]


            # Send the tool result back to the LLM.
            # No tools are supplied here, so another tool call
            # cannot be requested during this user turn.

            final_data = self.client.complete(follow_up_input)

            total_tokens += self._get_total_tokens(final_data)

            # Extract the final natural-language response.

            reply = self._extract_text(final_data)

        else:
            # The LLM answered directly without requesting a tool.
            logger.info("LLM responded without calling a tool.")
            reply = self._extract_text(data)

        if not reply:
            raise LLMClientError("LLM returned no text.")

        self.store.save_exchange(session_id, user_message, reply)

        return ChatResponse(reply=reply, total_tokens=total_tokens)
        
    def reset(self, session_id: str):
        self.store.clear(session_id)

    @staticmethod
    def _extract_text(data: dict):
        parts = []
        for item in data["output"]:
            if item["type"] == "message":
                for block in item["content"]:
                    if block["type"] == "output_text":
                        parts.append(block["text"])
        return "".join(parts)

    @staticmethod
    def _get_total_tokens(data: dict):
        usage = data.get("usage") or {}
        return usage.get("total_tokens", 0)