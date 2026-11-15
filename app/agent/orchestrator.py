import json
import logging
from time import perf_counter
from typing import Any

from app.agent.tool_definitions import TOOL_DEFINITIONS
from app.agent.tool_registry import execute_tool
from app.clients.llm_client import LLMClient, LLMClientError

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    MAX_TOOL_CALLS = 5

    def __init__(self, client: LLMClient):  # Dependency Injection
        self.client = client

    # Run the agentic tool-calling loop.
    # Return the final LLM response and total token usage.

    def run(
        self,
        input_items: list[dict[str, Any]],
        tool_context: dict[str, Any] | None = None,
    ):
        conversation_input = list(input_items)
        total_tokens = 0
        tool_calls_executed = 0

        # Initial request: let the LLM select a tool or answer directly.
        response = self.client.complete(
            conversation_input,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            parallel_tool_calls=False,
        )

        total_tokens += self._get_total_tokens(response)

        while True:
            output_items = response.get("output", [])

            # Identify function calls in the model response.
            function_calls = [
                item for item in output_items if item.get("type") == "function_call"
            ]

            # No function call means the LLM has finished.
            if not function_calls:
                return response, total_tokens

            # Preserve the complete model output.
            conversation_input.extend(output_items)

            function_outputs = []
            tool_limit_reached = False

            for tool_call in function_calls:
                tool_name = tool_call.get("name")
                call_id = tool_call.get("call_id")
                raw_arguments = tool_call.get("arguments")

                if not tool_name or not call_id:
                    raise LLMClientError("LLM returned an incomplete function call.")

                # Check whether the execution limit has been reached.
                if tool_calls_executed >= self.MAX_TOOL_CALLS:
                    logger.warning(
                        "Maximum tool-call limit reached: %s",
                        self.MAX_TOOL_CALLS,
                    )

                    tool_result = {
                        "error": (
                            "The maximum number of tool executions "
                            "for this request has been reached. "
                            "Provide a final answer using the "
                            "information already retrieved."
                        )
                    }

                    tool_limit_reached = True

                else:
                    tool_calls_executed += 1

                    tool_result = self._execute_tool(
                        tool_name,
                        raw_arguments,
                        call_id,
                        tool_calls_executed,
                        tool_context,
                    )

                # Every function call must receive a matching output,
                # including calls rejected because of the execution limit.
                function_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(
                            tool_result,
                            ensure_ascii=False,
                        ),
                    }
                )

            # Append all function outputs to the conversation.
            conversation_input.extend(function_outputs)

            if tool_limit_reached:
                logger.warning("Requesting final response after reaching tool limit.")

                # Do not offer additional tools.
                response = self.client.complete(conversation_input)

            else:
                # Let the LLM evaluate the results and decide
                # whether another tool is needed.
                response = self.client.complete(
                    conversation_input,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    parallel_tool_calls=False,
                )

            total_tokens += self._get_total_tokens(response)

    @staticmethod
    def _execute_tool(
        tool_name: str,
        raw_arguments: Any,
        call_id: str,
        call_number: int,
        tool_context: dict[str, Any] | None = None,
    ) -> dict:
        """Execute one registered tool and log its execution."""

        tool_start = perf_counter()

        logger.info(
            "Tool execution started | Tool: %s | Call ID: %s | Step: %s",
            tool_name,
            call_id,
            call_number,
        )

        try:
            # Responses API normally provides function arguments
            # as a JSON string.
            if isinstance(raw_arguments, str):
                arguments = json.loads(raw_arguments)
            else:
                arguments = raw_arguments

            if not isinstance(arguments, dict):
                raise TypeError("Tool arguments must be a JSON object.")

            # Validate and execute through the tool registry.
            result = execute_tool(tool_name, arguments, context=tool_context)

            if not isinstance(result, dict):
                raise TypeError("Tool must return a dictionary.")

            execution_time = perf_counter() - tool_start

            logger.info(
                "Tool execution completed | Tool: %s | Time: %.2fs",
                tool_name,
                execution_time,
            )

            return result

        except Exception:
            execution_time = perf_counter() - tool_start

            logger.exception(
                "Tool execution failed | Tool: %s | Time: %.2fs",
                tool_name,
                execution_time,
            )

            return {
                "error": (
                    "The requested tool could not retrieve "
                    "the information. Explain the failure "
                    "without inventing missing data."
                )
            }

    @staticmethod
    def _get_total_tokens(response: dict[str, Any]) -> int:
        usage = response.get("usage") or {}
        return usage.get("total_tokens", 0)
