"""Reusable MCP-enabled LLM client module."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import litellm
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field


class AnswerFormat(BaseModel):
    """Structured answer schema returned by the model."""

    full_answer: str = Field(
        description="The full answer to output, inclusive of reasoning for the user."
    )
    final_answer: str = Field(
        description="The final figure or fact that responds to the original question."
    )


class LLM_MCP_obj:
    """Client wrapper that combines LiteLLM generation with MCP tool-calling."""

    def __init__(
        self,
        exit_stack: Optional[AsyncExitStack] = None,
        max_compl_tokens: int = 2048,
        model: str = "mistral/mistral-small-2506",
        seed: int = 17,
        session: Optional[ClientSession] = None,
        stdio: Any = None,
        system_message: str = (
            "You are a helpful assistant. If you receive a question without any indication "
            "of time period, always assume it to refer to FY2023. Always limit tool "
            "executions to 5 fiscal periods prior to the reference one."
        ),
        temper: float = 0.01,
        top_p: float = 0.15,
        write: Any = None,
        project_root: Optional[Union[str, Path]] = None,
        history_file: Optional[Union[str, Path]] = None,
        history_db: Optional[Union[str, Path]] = None,
        deepseek_disable_thinking: bool = True,
        mcp_server_name: Optional[str] = None,
        enforce_tool_followup_policy: bool = True,
        max_edgar_identifier_only_followups: int = 1,
    ) -> None:
        """
        Constructor.

        Args:
            exit_stack: Async exit stack used by MCP client transports.
            max_compl_tokens: Max completion tokens.
            model: Model identifier in either provider/model or model-only format.
            seed: Seed for chat completions (provider support varies).
            session: Optional already-open MCP session.
            stdio: Optional read stream for the MCP client session.
            system_message: System prompt used for generation.
            temper: Temperature for completions.
            top_p: Top-p for completions.
            write: Optional write stream for the MCP client session.
            project_root: Optional base directory for server.py and data files.
            history_file: Legacy history path; if provided, `.db` sibling is used.
            history_db: Optional explicit SQLite path for tool-call history.
            deepseek_disable_thinking: Disable DeepSeek thinking mode when True.
            mcp_server_name: Optional MCP server identifier for history rows.
            enforce_tool_followup_policy: Enable MCP-specific tool-followup policies.
            max_edgar_identifier_only_followups: Maximum forced follow-up rounds when
                EDGAR requests only identifier-resolution tools.
        """

        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parent.parent
        )
        self.knowledge_base_dir = self.project_root / "knowledge_base" / "earnings_calls"
        if history_db is not None:
            self.history_db_path = Path(history_db).resolve()
        elif history_file is not None:
            self.history_db_path = Path(history_file).resolve().with_suffix(".db")
        else:
            # Keep history in runtime working directory as requests are processed.
            self.history_db_path = (Path.cwd() / "system_database.db").resolve()

        self.exit_stack = exit_stack or AsyncExitStack()
        self.max_compl_tokens = max_compl_tokens
        self.model = model
        self.seed = seed
        self.session = session
        self.stdio = stdio
        self.system_message = system_message
        self.temper = temper
        self.top_p = top_p
        self.write = write
        self.deepseek_disable_thinking = deepseek_disable_thinking
        self.enforce_tool_followup_policy = bool(enforce_tool_followup_policy)
        self.max_edgar_identifier_only_followups = max(
            0, int(max_edgar_identifier_only_followups)
        )
        self._mcp_server_name_explicit = (
            mcp_server_name is not None and str(mcp_server_name).strip() != ""
        )
        self.mcp_server_name = self._normalize_mcp_server_name(
            mcp_server_name or "lseg_mcp"
        )
        self._connected_sessions: List[ClientSession] = []
        self._connected_server_names: List[str] = []
        self._tool_name_to_session: Dict[str, ClientSession] = {}
        self._tool_name_to_server_name: Dict[str, str] = {}
        self._tool_name_casefold_lookup: Dict[str, str] = {}
        self._cached_tool_schemas: List[Dict[str, Any]] = []

        # Load project .env if present; fallback to default discovery.
        project_env = self.project_root / ".env"
        if project_env.exists():
            load_dotenv(dotenv_path=project_env, override=False)
        else:
            load_dotenv(override=False)

    @staticmethod
    def _empty_response_fallback_text() -> str:
        """Fallback text used when provider returns no textual answer."""

        return "Model returned an empty response."

    @staticmethod
    def _is_deepseek_model_name(model_name: str) -> bool:
        """Return whether model identifier appears to target a DeepSeek endpoint."""

        normalized_model_name = model_name.lower().strip()
        return normalized_model_name.startswith("deepseek/") or normalized_model_name.startswith(
            "deepseek"
        )

    @staticmethod
    def _normalize_mcp_server_name(server_name: str) -> str:
        """Normalize MCP server identifier used in persisted history."""

        normalized_raw = str(server_name).strip().lower()
        if normalized_raw in {
            "none",
            "no_mcp",
            "no mcp",
            "no-mcp",
            "off",
            "disable",
            "disabled",
        }:
            return "no_mcp"

        normalized = re.sub(r"[^a-z0-9_]+", "_", normalized_raw).strip(
            "_"
        )
        if normalized in {"none", "no_mcp", "nomcp", "off", "disable", "disabled"}:
            return "no_mcp"
        if not normalized:
            return "lseg_mcp"
        if not normalized.endswith("_mcp"):
            normalized = f"{normalized}_mcp"
        return normalized

    def _infer_mcp_server_name_from_script_path(self, server_script_path: Path) -> str:
        """Infer MCP server identifier from server script path."""

        script_stem = server_script_path.stem.lower().strip()
        if script_stem == "server":
            return "lseg_mcp"
        if script_stem.endswith("_server"):
            script_stem = script_stem[: -len("_server")]
        return self._normalize_mcp_server_name(script_stem or "lseg")

    def _reset_connected_server_state(self) -> None:
        """Reset in-memory mappings for active MCP sessions and registered tools."""

        self.session = None
        self._connected_sessions = []
        self._connected_server_names = []
        self._tool_name_to_session = {}
        self._tool_name_to_server_name = {}
        self._tool_name_casefold_lookup = {}
        self._cached_tool_schemas = []

    def _register_tool_schema(
        self,
        tool_schema: Dict[str, Any],
        *,
        session: ClientSession,
        server_name: str,
    ) -> None:
        """Register a tool schema and bind it to the owning MCP session."""

        function_payload = tool_schema.get("function", {})
        tool_name_raw = function_payload.get("name", "")
        tool_name = str(tool_name_raw).strip()
        if not tool_name:
            return

        casefold_tool_name = tool_name.casefold()
        existing_tool_name = self._tool_name_casefold_lookup.get(casefold_tool_name)
        if existing_tool_name is not None:
            existing_server = self._tool_name_to_server_name.get(existing_tool_name, "")
            if existing_server != server_name:
                raise RuntimeError(
                    "Tool name collision across MCP servers: "
                    f"'{existing_tool_name}' from '{existing_server}' "
                    f"and '{tool_name}' from '{server_name}'."
                )
            return

        self._tool_name_casefold_lookup[casefold_tool_name] = tool_name
        self._tool_name_to_session[tool_name] = session
        self._tool_name_to_server_name[tool_name] = server_name
        self._cached_tool_schemas.append(tool_schema)

    async def _register_session_tools(self, *, session: ClientSession, server_name: str) -> None:
        """Fetch and register tools exposed by one MCP session."""

        tools_result = await session.list_tools()
        for tool in tools_result.tools:
            tool_schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            self._register_tool_schema(
                tool_schema=tool_schema,
                session=session,
                server_name=server_name,
            )

    def _resolve_tool_session(self, tool_name: str) -> tuple[ClientSession, str]:
        """Resolve MCP session and server name for a tool call."""

        direct_session = self._tool_name_to_session.get(tool_name)
        if direct_session is not None:
            return direct_session, self._tool_name_to_server_name.get(
                tool_name,
                self.mcp_server_name,
            )

        canonical_tool_name = self._tool_name_casefold_lookup.get(str(tool_name).casefold())
        if canonical_tool_name is not None:
            resolved_session = self._tool_name_to_session.get(canonical_tool_name)
            if resolved_session is not None:
                return resolved_session, self._tool_name_to_server_name.get(
                    canonical_tool_name,
                    self.mcp_server_name,
                )

        if self.session is not None:
            return self.session, self.mcp_server_name

        raise RuntimeError(
            f"Tool '{tool_name}' is unavailable for current MCP server scope."
        )

    def _apply_model_specific_completion_overrides(self, **kwargs: Any) -> Dict[str, Any]:
        """Apply provider-specific completion kwargs before dispatching to LiteLLM."""

        if not self.deepseek_disable_thinking:
            return kwargs

        model_name = str(kwargs.get("model") or self.model)
        if not self._is_deepseek_model_name(model_name):
            return kwargs

        overridden_kwargs = dict(kwargs)
        extra_body_raw = kwargs.get("extra_body")
        extra_body = dict(extra_body_raw) if isinstance(extra_body_raw, dict) else {}
        thinking_raw = extra_body.get("thinking")
        thinking = dict(thinking_raw) if isinstance(thinking_raw, dict) else {}
        thinking["type"] = "disabled"
        extra_body["thinking"] = thinking
        overridden_kwargs["extra_body"] = extra_body
        return overridden_kwargs

    async def _acompletion_with_retry(self, **kwargs: Any) -> Any:
        """
        Execute litellm.acompletion() with exponential backoff retry logic.
        Retries up to 3 times for 503-like failures.
        """

        max_attempts = 3
        attempt = 0
        completion_kwargs = self._apply_model_specific_completion_overrides(**kwargs)

        while attempt < max_attempts:
            try:
                attempt += 1
                return await litellm.acompletion(**completion_kwargs)
            except Exception as exc:
                error_message = str(exc)
                if attempt >= max_attempts:
                    raise
                if "503" in error_message or "Service Unavailable" in error_message:
                    wait_time = 2**attempt
                    print(
                        f"Attempt {attempt} failed with 503 error. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

    def _resolve_server_script_path(
        self, server_script_path: Optional[Union[str, Path]]
    ) -> Path:
        """Resolve server script path in a way that is safe for import-from-anywhere usage."""

        if server_script_path is None:
            return (self.project_root / "server.py").resolve()

        candidate = Path(server_script_path)
        if candidate.is_absolute():
            return candidate

        project_candidate = (self.project_root / candidate).resolve()
        if project_candidate.exists():
            return project_candidate

        cwd_candidate = (Path.cwd() / candidate).resolve()
        if cwd_candidate.exists():
            return cwd_candidate

        # Default to project-root-relative path even if it does not exist yet.
        return project_candidate

    def _model_name_for_history(self) -> str:
        """Return provider-qualified model identifier for history records."""

        return self.model

    @staticmethod
    def _safe_int_token(value: Any) -> Optional[int]:
        """Coerce token value to non-negative integer when possible."""

        if value is None:
            return None
        try:
            token_value = int(value)
        except (TypeError, ValueError):
            return None
        if token_value < 0:
            return None
        return token_value

    @staticmethod
    def _obj_to_dict(value: Any) -> Dict[str, Any]:
        """Convert response-like objects to dictionaries when possible."""

        if value is None:
            return {}
        if isinstance(value, dict):
            return value

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass

        to_dict = getattr(value, "dict", None)
        if callable(to_dict):
            try:
                dumped = to_dict()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass

        try:
            return dict(vars(value))
        except Exception:
            return {}

    def _lookup_token_value(
        self, containers: List[Dict[str, Any]], keys: List[str]
    ) -> Optional[int]:
        """Find first valid token value across dict containers and candidate keys."""

        for container in containers:
            for key in keys:
                if key not in container:
                    continue
                parsed_value = self._safe_int_token(container.get(key))
                if parsed_value is not None:
                    return parsed_value
        return None

    def _normalize_messages_for_count(self, messages: List[Any]) -> List[Dict[str, str]]:
        """Normalize mixed message objects/dicts into text-only chat messages."""

        normalized_messages: List[Dict[str, str]] = []

        for message in messages:
            if isinstance(message, dict):
                role = str(message.get("role", "user"))
                content = message.get("content")
                if isinstance(content, str):
                    text_content = content
                else:
                    text_content = json.dumps(content, default=str)
                normalized_messages.append({"role": role, "content": text_content})
                continue

            role = str(getattr(message, "role", "assistant"))
            content = getattr(message, "content", "")
            tool_calls = getattr(message, "tool_calls", None)
            chunks: List[str] = []

            if isinstance(content, str):
                if content:
                    chunks.append(content)
            elif content is not None:
                chunks.append(json.dumps(content, default=str))

            if tool_calls:
                chunks.append(str(tool_calls))

            if not chunks:
                chunks.append(str(message))

            normalized_messages.append({"role": role, "content": "\n".join(chunks)})

        return normalized_messages

    def _estimate_tokens_from_messages(self, messages: List[Any]) -> int:
        """Estimate tokens from messages when provider usage is missing."""

        normalized_messages = self._normalize_messages_for_count(messages)
        if not normalized_messages:
            return 0

        try:
            return int(litellm.token_counter(model=self.model, messages=normalized_messages))
        except Exception:
            joined_text = " ".join(
                message.get("content", "") for message in normalized_messages
            )
            if not joined_text:
                return 0
            # Character-length fallback used only if provider tokenizer is unavailable.
            return max(1, len(joined_text) // 4)

    def _assistant_message_text_for_count(self, assistant_message: Any) -> str:
        """Build assistant/tool-call textual form for token estimation fallback."""

        content = getattr(assistant_message, "content", "")
        if content is None:
            content_text = ""
        elif isinstance(content, str):
            content_text = content
        else:
            content_text = json.dumps(content, default=str)

        tool_calls = getattr(assistant_message, "tool_calls", None)
        if not tool_calls:
            return content_text

        tool_chunks: List[str] = []
        for tool_call in tool_calls:
            function_obj = getattr(tool_call, "function", None)
            tool_name = getattr(function_obj, "name", "")
            tool_args = getattr(function_obj, "arguments", "")
            tool_chunks.append(f"{tool_name}:{tool_args}")

        serialized_tools = "\n".join(tool_chunks)
        if content_text:
            return f"{content_text}\n{serialized_tools}"
        return serialized_tools

    @staticmethod
    def _json_schema_response_format() -> Dict[str, Any]:
        """Return response_format payload for strict AnswerFormat JSON schema."""

        return {
            "type": "json_schema",
            "json_schema": {
                "name": "AnswerFormat",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "full_answer": {
                            "type": "string",
                            "description": (
                                "The full answer to output, inclusive of descriptions "
                                "for the user to understand how the final answer was reached."
                            ),
                        },
                        "final_answer": {
                            "type": "string",
                            "description": (
                                "The final figure or fact that ultimately responds "
                                "to the original user question."
                            ),
                        },
                    },
                    "required": ["full_answer", "final_answer"],
                    "additionalProperties": False,
                },
            },
        }

    def _supports_json_schema_response_format(self) -> bool:
        """Best-effort provider capability gate for response_format json_schema."""

        model_name = self.model.lower().strip()
        # DeepSeek chat endpoints currently reject json_schema response_format.
        if model_name.startswith("deepseek/") or model_name.startswith("deepseek"):
            return False
        return True

    def _is_deepseek_model(self) -> bool:
        """Return whether the active model appears to be a DeepSeek endpoint."""

        return self._is_deepseek_model_name(self.model)

    @staticmethod
    def _is_response_format_unsupported_error(exc: Exception) -> bool:
        """Return True when provider rejects response_format/json_schema features."""

        error_text = str(exc).lower()
        mentions_response_format = (
            "response_format" in error_text or "json_schema" in error_text
        )
        unsupported_markers = [
            "unavailable",
            "unsupported",
            "not support",
            "not available",
            "invalid_request_error",
        ]
        return mentions_response_format and any(
            marker in error_text for marker in unsupported_markers
        )

    def _build_json_only_fallback_messages(self, messages: List[Any]) -> List[Any]:
        """Append instruction that enforces JSON-only output without response_format."""

        return [
            *messages,
            {
                "role": "user",
                "content": (
                    "Return ONLY a valid JSON object with exactly two string keys: "
                    "full_answer and final_answer. Do not include markdown, code fences, "
                    "or any other keys."
                ),
            },
        ]

    @staticmethod
    def _extract_tool_names_from_schemas(tool_schemas: List[Dict[str, Any]]) -> List[str]:
        """Extract normalized function names from OpenAI-style tool schema payloads."""

        tool_names: List[str] = []
        for tool_schema in tool_schemas:
            function_payload = tool_schema.get("function", {})
            raw_name = function_payload.get("name")
            if raw_name is None:
                continue
            normalized_name = str(raw_name).strip()
            if normalized_name:
                tool_names.append(normalized_name)
        return tool_names

    @staticmethod
    def _zero_usage() -> Dict[str, int]:
        """Return zeroed token-usage payload."""

        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @staticmethod
    def _accumulate_usage(total_usage: Dict[str, int], delta_usage: Dict[str, int]) -> None:
        """Accumulate token usage in-place."""

        total_usage["prompt_tokens"] += int(delta_usage.get("prompt_tokens", 0) or 0)
        total_usage["completion_tokens"] += int(delta_usage.get("completion_tokens", 0) or 0)
        total_usage["total_tokens"] += int(delta_usage.get("total_tokens", 0) or 0)

    @staticmethod
    def _query_explicitly_requests_identifier_resolution(query: str) -> bool:
        """Return whether question appears to explicitly ask for ticker/CIK mapping."""

        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return False

        identifier_markers = (
            r"\bcik\b",
            r"central\s+index\s+key",
            r"ticker\s+to\s+cik",
            r"cik\s+from\s+ticker",
            r"what\s+is\s+the\s+cik",
        )
        return any(
            re.search(pattern, normalized_query, flags=re.IGNORECASE)
            for pattern in identifier_markers
        )

    @staticmethod
    def _tool_response_contains_identifier_error(tool_response_text: str) -> bool:
        """Best-effort check for identifier lookup failures in tool responses."""

        normalized_response = str(tool_response_text or "").strip().lower()
        if not normalized_response:
            return False

        error_markers = (
            "error calling tool",
            "not found in sec ticker reference",
            "invalid cik",
            "cannot be empty",
            "failed",
            "exception",
        )
        return any(marker in normalized_response for marker in error_markers)

    def should_request_additional_tool_round(
        self,
        *,
        query: str,
        executed_tool_names: List[str],
        executed_tool_responses: Optional[List[str]] = None,
        available_tool_names: Optional[List[str]] = None,
        followup_rounds_already_requested: int = 0,
    ) -> bool:
        """
        Decide whether model should be pushed into another tool-calling round.

        Current policy:
        - Applies to EDGAR MCP only.
        - Triggers when model only called `get_cik_from_ticker` (identifier resolution)
          even though question appears to need factual retrieval.
        """

        if not self.enforce_tool_followup_policy:
            return False
        if self.mcp_server_name != "edgar_mcp":
            return False
        if followup_rounds_already_requested >= self.max_edgar_identifier_only_followups:
            return False

        normalized_executed_names = {
            str(tool_name).strip().lower()
            for tool_name in executed_tool_names
            if str(tool_name).strip()
        }
        if not normalized_executed_names:
            return False

        identifier_only_tool_names = {"get_cik_from_ticker"}
        if not normalized_executed_names.issubset(identifier_only_tool_names):
            return False
        if self._query_explicitly_requests_identifier_resolution(query):
            return False

        if executed_tool_responses:
            if any(
                self._tool_response_contains_identifier_error(tool_response_text)
                for tool_response_text in executed_tool_responses
            ):
                return False

        normalized_available_names = {
            str(tool_name).strip().lower()
            for tool_name in (available_tool_names or [])
            if str(tool_name).strip()
        }
        data_retrieval_tool_names = {
            "get_company_concept",
            "get_company_facts",
            "get_recent_filings",
            "get_xbrl_frame",
            "get_submissions",
        }

        # If no availability map is provided, optimistically allow follow-up.
        if normalized_available_names and not (
            normalized_available_names & data_retrieval_tool_names
        ):
            return False

        return True

    def build_additional_tool_round_prompt(
        self, *, query: str, executed_tool_names: Optional[List[str]] = None
    ) -> str:
        """Build a focused follow-up instruction for the next tool-planning round."""

        executed_names = ", ".join(
            sorted({str(name).strip() for name in (executed_tool_names or []) if str(name).strip()})
        )
        executed_names_suffix = f" ({executed_names})" if executed_names else ""
        return (
            "You just resolved an identifier using tool(s)"
            f"{executed_names_suffix}. Do not provide the final answer yet. "
            "Call at least one SEC data-retrieval tool now (prefer `get_company_concept`; "
            "otherwise use `get_company_facts`, `get_recent_filings`, or `get_xbrl_frame`) "
            "to fetch the financial facts needed for the original question, then continue."
        )

    def _content_to_text(self, content: Any) -> str:
        """Normalize model response content (str/list/object) into plain text."""

        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: List[str] = []
            for chunk in content:
                if isinstance(chunk, str):
                    chunks.append(chunk)
                    continue
                if isinstance(chunk, dict):
                    chunk_text = chunk.get("text")
                    if isinstance(chunk_text, str):
                        chunks.append(chunk_text)
                        continue
                chunk_text_attr = getattr(chunk, "text", None)
                if isinstance(chunk_text_attr, str):
                    chunks.append(chunk_text_attr)
                    continue
                try:
                    chunks.append(json.dumps(chunk, default=str))
                except Exception:
                    chunks.append(str(chunk))
            return "\n".join(chunk for chunk in chunks if chunk)
        try:
            return json.dumps(content, default=str)
        except Exception:
            return str(content)

    def _first_non_empty_text(self, values: List[Any]) -> str:
        """Return first non-empty normalized text across candidate values."""

        for value in values:
            text = self._content_to_text(value).strip()
            if text:
                return text
        return ""

    def _response_message_text(
        self, message: Any, include_reasoning_fallback: bool = False
    ) -> str:
        """Extract best-effort text from a single chat message object."""

        message_dict = self._obj_to_dict(message)

        primary_text = self._first_non_empty_text(
            [
                getattr(message, "content", None),
                message_dict.get("content"),
                getattr(message, "text", None),
                message_dict.get("text"),
                getattr(message, "output_text", None),
                message_dict.get("output_text"),
                message_dict.get("final_answer"),
                message_dict.get("answer"),
            ]
        )
        if primary_text:
            return primary_text

        if include_reasoning_fallback:
            reasoning_text = self._first_non_empty_text(
                [
                    getattr(message, "reasoning_content", None),
                    message_dict.get("reasoning_content"),
                    getattr(message, "reasoning", None),
                    message_dict.get("reasoning"),
                ]
            )
            if reasoning_text:
                return reasoning_text

        return ""

    def _response_text(
        self, response: Any, include_reasoning_fallback: bool = False
    ) -> str:
        """Extract best-effort text from a completion response object."""

        response_dict = self._obj_to_dict(response)
        choices = getattr(response, "choices", None)
        if choices is None:
            choices = response_dict.get("choices", [])

        for choice in choices or []:
            choice_dict = self._obj_to_dict(choice)
            message = getattr(choice, "message", None)
            if message is None:
                message = choice_dict.get("message")

            message_text = self._response_message_text(
                message=message,
                include_reasoning_fallback=include_reasoning_fallback,
            )
            if message_text:
                return message_text

            choice_text = self._first_non_empty_text(
                [
                    getattr(choice, "text", None),
                    choice_dict.get("text"),
                    choice_dict.get("output_text"),
                    choice_dict.get("content"),
                ]
            )
            if choice_text:
                return choice_text

        response_text = self._first_non_empty_text(
            [
                response_dict.get("output_text"),
                response_dict.get("text"),
                response_dict.get("content"),
                response_dict.get("final_answer"),
                response_dict.get("answer"),
            ]
        )
        if response_text:
            return response_text

        if include_reasoning_fallback:
            reasoning_response_text = self._first_non_empty_text(
                [
                    response_dict.get("reasoning_content"),
                    response_dict.get("reasoning"),
                ]
            )
            if reasoning_response_text:
                return reasoning_response_text

        return ""

    @staticmethod
    def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
        """Extract first JSON object found anywhere in free-form text."""

        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        return None

    def _parse_answer_format_content(self, content: Any) -> AnswerFormat:
        """Parse provider output into AnswerFormat with graceful degradation."""

        content_text = self._content_to_text(content).strip()
        if not content_text:
            fallback = self._empty_response_fallback_text()
            return AnswerFormat(full_answer=fallback, final_answer=fallback)

        parsed_payload: Optional[Dict[str, Any]] = None
        try:
            loaded = json.loads(content_text)
            if isinstance(loaded, dict):
                parsed_payload = loaded
        except json.JSONDecodeError:
            parsed_payload = self._extract_first_json_object(content_text)

        if isinstance(parsed_payload, dict):
            lowered_payload = {
                key.lower(): value for key, value in parsed_payload.items() if isinstance(key, str)
            }
            full_answer = parsed_payload.get("full_answer", lowered_payload.get("full_answer"))
            final_answer = parsed_payload.get(
                "final_answer", lowered_payload.get("final_answer")
            )
            generic_answer = parsed_payload.get("answer", lowered_payload.get("answer"))

            if full_answer is None:
                full_answer = generic_answer
            if final_answer is None:
                final_answer = generic_answer if generic_answer is not None else full_answer

            if full_answer is not None or final_answer is not None:
                return AnswerFormat(
                    full_answer=str(
                        full_answer if full_answer is not None else final_answer
                    ),
                    final_answer=str(
                        final_answer if final_answer is not None else full_answer
                    ),
                )

        # Last-resort behavior: avoid failing the request when JSON is imperfect.
        return AnswerFormat(full_answer=content_text, final_answer=content_text)

    def _extract_token_usage(
        self,
        response: Any,
        prompt_messages: Optional[List[Any]] = None,
        completion_text: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Extract prompt/completion/total tokens across provider-specific usage schemas.

        Handles normalized OpenAI-style fields and alternate provider nomenclature
        used by Gemini/Anthropic/Mistral wrappers when present.
        """

        response_dict = self._obj_to_dict(response)
        usage_obj = getattr(response, "usage", None)
        usage_dict = self._obj_to_dict(usage_obj)

        containers: List[Dict[str, Any]] = [usage_dict, response_dict]
        nested_candidates = [
            response_dict.get("usage_metadata"),
            usage_dict.get("usage_metadata"),
            response_dict.get("token_usage"),
            usage_dict.get("token_usage"),
            response_dict.get("usage"),
            usage_dict.get("usage"),
        ]

        for candidate in nested_candidates:
            candidate_dict = self._obj_to_dict(candidate)
            if candidate_dict:
                containers.append(candidate_dict)

        prompt_tokens = self._lookup_token_value(
            containers,
            [
                "prompt_tokens",
                "input_tokens",
                "prompt_token_count",
                "input_token_count",
                "promptTokens",
                "inputTokens",
            ],
        )
        completion_tokens = self._lookup_token_value(
            containers,
            [
                "completion_tokens",
                "output_tokens",
                "candidates_token_count",
                "output_token_count",
                "completionTokens",
                "outputTokens",
                "candidatesTokenCount",
            ],
        )
        total_tokens = self._lookup_token_value(
            containers,
            [
                "total_tokens",
                "total_token_count",
                "totalTokens",
            ],
        )

        if prompt_tokens is None and prompt_messages is not None:
            prompt_tokens = self._estimate_tokens_from_messages(prompt_messages)

        if completion_tokens is None and completion_text is not None:
            completion_tokens = self._estimate_tokens_from_messages(
                [{"role": "assistant", "content": completion_text}]
            )

        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        if total_tokens is None and prompt_tokens is not None:
            total_tokens = prompt_tokens
        if total_tokens is None and completion_tokens is not None:
            total_tokens = completion_tokens

        if prompt_tokens is None and total_tokens is not None and completion_tokens is not None:
            prompt_tokens = max(total_tokens - completion_tokens, 0)
        if (
            completion_tokens is None
            and total_tokens is not None
            and prompt_tokens is not None
        ):
            completion_tokens = max(total_tokens - prompt_tokens, 0)

        return {
            "prompt_tokens": prompt_tokens if prompt_tokens is not None else 0,
            "completion_tokens": completion_tokens if completion_tokens is not None else 0,
            "total_tokens": total_tokens if total_tokens is not None else 0,
        }

    @staticmethod
    def _timestamp_utc() -> str:
        """Return UTC timestamp in ISO-like format used by history rows."""

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        """Return whether a SQLite table exists."""

        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        """Return whether a table already contains a given column."""

        table_info = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(str(row[1]) == column_name for row in table_info)

    def _ensure_mcp_server_column(self, conn: sqlite3.Connection, table_name: str) -> None:
        """Ensure mcp_server column exists and is populated."""

        if not self._table_exists(conn, table_name):
            return

        if not self._column_exists(conn, table_name, "mcp_server"):
            default_literal = self.mcp_server_name.replace("'", "''")
            conn.execute(
                f"""
                ALTER TABLE {table_name}
                ADD COLUMN mcp_server TEXT NOT NULL DEFAULT '{default_literal}'
                """
            )

        conn.execute(
            f"""
            UPDATE {table_name}
            SET mcp_server = ?
            WHERE mcp_server IS NULL OR TRIM(mcp_server) = ''
            """,
            (self.mcp_server_name,),
        )

    def _ensure_storage_paths(self) -> None:
        """Ensure directories/files used by tool history exist."""

        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)
        self.history_db_path.parent.mkdir(parents=True, exist_ok=True)
        default_mcp_server = self.mcp_server_name.replace("'", "''")
        with sqlite3.connect(self.history_db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS request_history (
                    request_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    generator_model TEXT NOT NULL,
                    question_tkns INTEGER,
                    answer_tkns INTEGER,
                    tot_tkns INTEGER,
                    full_answer TEXT,
                    final_answer TEXT,
                    error_message TEXT,
                    tool_call_count INTEGER NOT NULL DEFAULT 0,
                    mcp_server TEXT NOT NULL DEFAULT '{default_mcp_server}'
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS tool_call_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    call_index INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_args TEXT,
                    tool_resp TEXT,
                    mcp_server TEXT NOT NULL DEFAULT '{default_mcp_server}',
                    FOREIGN KEY(request_id) REFERENCES request_history(request_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tool_call_history_request_id
                ON tool_call_history(request_id)
                """
            )
            for table_name in (
                "request_history",
                "tool_call_history",
                "benchmark_run_history",
                "evaluation_run_history",
            ):
                self._ensure_mcp_server_column(conn, table_name)
            conn.commit()

    def _insert_request_history(self, request_id: str, question: str) -> None:
        """Insert initial request row when a new user query is received."""

        self._ensure_storage_paths()
        now = self._timestamp_utc()
        with sqlite3.connect(self.history_db_path) as conn:
            conn.execute(
                """
                INSERT INTO request_history (
                    request_id, question, status, created_at, updated_at, generator_model, mcp_server
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    question,
                    "received",
                    now,
                    now,
                    self._model_name_for_history(),
                    self.mcp_server_name,
                ),
            )
            conn.commit()

    def _update_request_history(self, request_id: str, **fields: Any) -> None:
        """Update request row as processing advances."""

        if not fields:
            return

        self._ensure_storage_paths()
        fields["updated_at"] = self._timestamp_utc()
        set_clause = ", ".join([f"{field_name} = ?" for field_name in fields.keys()])
        params = list(fields.values()) + [request_id]
        with sqlite3.connect(self.history_db_path) as conn:
            conn.execute(
                f"UPDATE request_history SET {set_clause} WHERE request_id = ?", params
            )
            conn.commit()

    def _insert_tool_call_history(
        self,
        request_id: str,
        call_index: int,
        tool_name: str,
        tool_args: Optional[str],
        tool_resp: Optional[str],
        mcp_server: Optional[str] = None,
    ) -> None:
        """Insert a tool-call event row tied to a request."""

        self._ensure_storage_paths()
        resolved_mcp_server = self._normalize_mcp_server_name(
            mcp_server or self.mcp_server_name
        )
        with sqlite3.connect(self.history_db_path) as conn:
            conn.execute(
                """
                INSERT INTO tool_call_history (
                    request_id, call_index, datetime, tool_name, tool_args, tool_resp, mcp_server
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    call_index,
                    self._timestamp_utc(),
                    tool_name,
                    tool_args,
                    tool_resp,
                    resolved_mcp_server,
                ),
            )
            conn.commit()

    async def connect_to_server(
        self, server_script_path: Optional[Union[str, Path]] = None
    ) -> None:
        """
        Connect to a single MCP server.

        Args:
            server_script_path: Path to server script. Defaults to project_root/server.py.
        """

        resolved_server_path = self._resolve_server_script_path(server_script_path)
        await self.connect_to_servers(server_script_paths=[resolved_server_path])

    async def connect_to_servers(
        self,
        server_script_paths: List[Union[str, Path]],
    ) -> None:
        """
        Connect to exactly one MCP server script and register exposed tools.

        Args:
            server_script_paths: Single-entry list containing one MCP server script path.
        """

        if not server_script_paths:
            raise ValueError(
                "server_script_paths must include at least one MCP server script."
            )

        unique_resolved_paths: List[Path] = []
        seen_paths: set[str] = set()
        for raw_path in server_script_paths:
            resolved_path = self._resolve_server_script_path(raw_path)
            resolved_key = str(resolved_path)
            if resolved_key in seen_paths:
                continue
            seen_paths.add(resolved_key)
            unique_resolved_paths.append(resolved_path)

        if len(unique_resolved_paths) > 1:
            raise ValueError(
                "Multiple MCP servers are not allowed in a single request scope. "
                "Select exactly one MCP server or no MCP server."
            )

        inferred_server_names = [
            self._infer_mcp_server_name_from_script_path(server_path)
            for server_path in unique_resolved_paths
        ]

        if self._mcp_server_name_explicit:
            resolved_request_server_name = self.mcp_server_name
        elif len(inferred_server_names) == 1:
            resolved_request_server_name = inferred_server_names[0]
        else:
            resolved_request_server_name = "all_mcp"
        self.mcp_server_name = self._normalize_mcp_server_name(resolved_request_server_name)

        self._reset_connected_server_state()

        for resolved_server_path, inferred_server_name in zip(
            unique_resolved_paths,
            inferred_server_names,
        ):
            server_params = StdioServerParameters(
                command="python",
                args=[str(resolved_server_path)],
            )
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport

            session = await self.exit_stack.enter_async_context(
                ClientSession(read_stream=stdio, write_stream=write)
            )
            await session.initialize()

            self._connected_sessions.append(session)
            self._connected_server_names.append(inferred_server_name)
            if self.session is None:
                # Keep backwards-compatible primary session pointer.
                self.session = session
            await self._register_session_tools(
                session=session,
                server_name=inferred_server_name,
            )

    async def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        Get available tools from connected MCP server scope in OpenAI function-call format.

        Returns:
            List of tools in OpenAI format.
        """

        if self._cached_tool_schemas:
            return list(self._cached_tool_schemas)

        if self.session is None and not self._cached_tool_schemas:
            # Explicit no-tool mode.
            return []

        await self._register_session_tools(
            session=self.session,
            server_name=self.mcp_server_name,
        )
        return list(self._cached_tool_schemas)

    async def process_query(self, query: str) -> Dict[str, str]:
        """
        Process query using LiteLLM and available MCP tools.

        Args:
            query: User query.

        Returns:
            Dict with assistant role and response content.
        """

        request_id = str(uuid.uuid4())
        self._insert_request_history(request_id=request_id, question=query)
        self._update_request_history(request_id=request_id, status="processing")

        try:
            tools = await self.get_mcp_tools()
            available_tool_names = self._extract_tool_names_from_schemas(tools)
            conversation_messages: List[Any] = [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": query},
            ]
            tool_call_count = 0
            planning_usage_totals = self._zero_usage()

            initial_prompt_messages = list(conversation_messages)
            initial_completion_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": initial_prompt_messages,
                "temperature": self.temper,
                "max_tokens": self.max_compl_tokens,
            }
            if tools:
                initial_completion_kwargs["tools"] = tools
                initial_completion_kwargs["tool_choice"] = "auto"

            response = await self._acompletion_with_retry(**initial_completion_kwargs)

            assistant_message = response.choices[0].message
            initial_usage = self._extract_token_usage(
                response=response,
                prompt_messages=initial_prompt_messages,
                completion_text=self._assistant_message_text_for_count(assistant_message),
            )
            self._accumulate_usage(planning_usage_totals, initial_usage)
            conversation_messages.append(assistant_message)

            if assistant_message.tool_calls:
                self._update_request_history(request_id=request_id, status="processing_tools")
                current_assistant_message = assistant_message
                followup_rounds_requested = 0

                while current_assistant_message.tool_calls:
                    round_tool_names: List[str] = []
                    round_tool_responses: List[str] = []
                    for tool_call in current_assistant_message.tool_calls:
                        tool_call_count += 1

                        tool_name = str(tool_call.function.name or "").strip()
                        tool_session, tool_server_name = self._resolve_tool_session(tool_name)
                        raw_tool_args = tool_call.function.arguments or "{}"
                        parsed_tool_args = (
                            json.loads(raw_tool_args)
                            if isinstance(raw_tool_args, str)
                            else raw_tool_args
                        )
                        tool_result = await tool_session.call_tool(
                            tool_name,
                            arguments=parsed_tool_args,
                        )

                        tool_result_text = (
                            tool_result.content[0].text
                            if tool_result.content and len(tool_result.content) > 0
                            else ""
                        )
                        self._insert_tool_call_history(
                            request_id=request_id,
                            call_index=tool_call_count,
                            tool_name=tool_name,
                            tool_args=(
                                raw_tool_args
                                if isinstance(raw_tool_args, str)
                                else json.dumps(raw_tool_args, default=str)
                            ),
                            tool_resp=tool_result_text,
                            mcp_server=tool_server_name,
                        )

                        round_tool_names.append(tool_name)
                        round_tool_responses.append(tool_result_text)
                        print(
                            f"Using tool: {tool_name} "
                            f"with args: {raw_tool_args}"
                        )

                        conversation_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": tool_result_text,
                            }
                        )

                    should_request_followup = self.should_request_additional_tool_round(
                        query=query,
                        executed_tool_names=round_tool_names,
                        executed_tool_responses=round_tool_responses,
                        available_tool_names=available_tool_names,
                        followup_rounds_already_requested=followup_rounds_requested,
                    )
                    if not should_request_followup:
                        break

                    followup_rounds_requested += 1
                    conversation_messages.append(
                        {
                            "role": "user",
                            "content": self.build_additional_tool_round_prompt(
                                query=query,
                                executed_tool_names=round_tool_names,
                            ),
                        }
                    )

                    followup_prompt_messages = list(conversation_messages)
                    followup_completion_kwargs: Dict[str, Any] = {
                        "model": self.model,
                        "messages": followup_prompt_messages,
                        "temperature": self.temper,
                        "max_tokens": self.max_compl_tokens,
                    }
                    if tools:
                        followup_completion_kwargs["tools"] = tools
                        followup_completion_kwargs["tool_choice"] = "auto"

                    followup_response = await self._acompletion_with_retry(
                        **followup_completion_kwargs
                    )
                    current_assistant_message = followup_response.choices[0].message
                    followup_usage = self._extract_token_usage(
                        response=followup_response,
                        prompt_messages=followup_prompt_messages,
                        completion_text=self._assistant_message_text_for_count(
                            current_assistant_message
                        ),
                    )
                    self._accumulate_usage(planning_usage_totals, followup_usage)
                    conversation_messages.append(current_assistant_message)

                final_usage = self._zero_usage()
                try:
                    final_prompt_messages = list(conversation_messages)
                    if self._supports_json_schema_response_format():
                        try:
                            final_response = await self._acompletion_with_retry(
                                model=self.model,
                                messages=final_prompt_messages,
                                max_tokens=self.max_compl_tokens,
                                temperature=self.temper,
                                response_format=self._json_schema_response_format(),
                            )
                        except Exception as response_format_exc:
                            if not self._is_response_format_unsupported_error(
                                response_format_exc
                            ):
                                raise
                            final_prompt_messages = self._build_json_only_fallback_messages(
                                conversation_messages
                            )
                            final_response = await self._acompletion_with_retry(
                                model=self.model,
                                messages=final_prompt_messages,
                                max_tokens=self.max_compl_tokens,
                                temperature=self.temper,
                            )
                    else:
                        final_prompt_messages = self._build_json_only_fallback_messages(
                            conversation_messages
                        )
                        final_response = await self._acompletion_with_retry(
                            model=self.model,
                            messages=final_prompt_messages,
                            max_tokens=self.max_compl_tokens,
                            temperature=self.temper,
                        )

                    final_message_content = self._response_text(
                        response=final_response,
                        include_reasoning_fallback=self._is_deepseek_model(),
                    )
                    final_usage = self._extract_token_usage(
                        response=final_response,
                        prompt_messages=final_prompt_messages,
                        completion_text=final_message_content,
                    )

                    parsed_final = self._parse_answer_format_content(final_message_content)

                    self._update_request_history(
                        request_id=request_id,
                        status="completed",
                        question_tkns=planning_usage_totals["prompt_tokens"]
                        + final_usage["prompt_tokens"],
                        full_answer=parsed_final.full_answer,
                        final_answer=parsed_final.final_answer,
                        answer_tkns=planning_usage_totals["completion_tokens"]
                        + final_usage["completion_tokens"],
                        tot_tkns=planning_usage_totals["total_tokens"]
                        + final_usage["total_tokens"],
                        tool_call_count=tool_call_count,
                        error_message=None,
                    )

                    print("Question processed, check the answer.")
                    return {"role": "assistant", "content": parsed_final.final_answer}

                except Exception as exc:
                    self._update_request_history(
                        request_id=request_id,
                        status="failed",
                        question_tkns=planning_usage_totals["prompt_tokens"]
                        + final_usage["prompt_tokens"],
                        full_answer="Structured output parsing failed",
                        final_answer="Structured output parsing failed",
                        answer_tkns=planning_usage_totals["completion_tokens"]
                        + final_usage["completion_tokens"],
                        tot_tkns=planning_usage_totals["total_tokens"]
                        + final_usage["total_tokens"],
                        tool_call_count=tool_call_count,
                        error_message=str(exc),
                    )

                    print(f"Structured output parsing failed: {str(exc)}")
                    return {
                        "role": "assistant",
                        "content": "Structured output parsing failed.",
                    }

            assistant_content = (assistant_message.content or "").strip()
            if not assistant_content:
                assistant_content = self._response_text(
                    response=response,
                    include_reasoning_fallback=self._is_deepseek_model(),
                )
            if not assistant_content:
                assistant_content = self._empty_response_fallback_text()
            self._update_request_history(
                request_id=request_id,
                status="completed",
                question_tkns=planning_usage_totals["prompt_tokens"],
                full_answer=assistant_content,
                final_answer=assistant_content,
                answer_tkns=planning_usage_totals["completion_tokens"],
                tot_tkns=planning_usage_totals["total_tokens"],
                tool_call_count=0,
                error_message=None,
            )

            print("Question processed, check the answer.")
            return {"role": "assistant", "content": assistant_content}
        except Exception as exc:
            known_usage = locals().get("planning_usage_totals", self._zero_usage())
            self._update_request_history(
                request_id=request_id,
                status="failed",
                question_tkns=known_usage["prompt_tokens"],
                answer_tkns=known_usage["completion_tokens"],
                tot_tkns=known_usage["total_tokens"],
                error_message=str(exc),
            )
            raise

    async def cleanup(self) -> None:
        """Clean up async resources."""

        await self.exit_stack.aclose()


__all__ = ["AnswerFormat", "LLM_MCP_obj"]
