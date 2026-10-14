# import necessary libraries
from dash import Input, Output, State
from typing import List
from pathlib import Path
from contextlib import suppress

import sys

lseg_src_dir = (Path(__file__).resolve().parent / ".." / "lseg_llm_mcp" / "src").resolve()

if str(lseg_src_dir) not in sys.path:
    sys.path.insert(0, str(lseg_src_dir))

from LLM_MCP import LLM_MCP_obj


MCP_SERVER_SCOPE_TO_SCRIPTS = {
    "lseg": ["server.py"],
    "edgar": ["edgar_server.py"],
    "rag": ["rag_server.py"],
    "none": [],
}
DEFAULT_MCP_SERVER_SCOPE = "lseg"

MCP_SERVER_SCOPE_TO_NAME = {
    "lseg": "lseg_mcp",
    "edgar": "edgar_mcp",
    "rag": "rag_mcp",
    "none": "no_mcp",
}


def _resolve_server_scope_scripts(scope_value: str) -> list[Path]:
    normalized_scope = str(scope_value or DEFAULT_MCP_SERVER_SCOPE).strip().lower()
    selected_scope = (
        normalized_scope
        if normalized_scope in MCP_SERVER_SCOPE_TO_SCRIPTS
        else DEFAULT_MCP_SERVER_SCOPE
    )
    project_root = Path(__file__).resolve().parent
    resolved_scripts = [
        (project_root / script_name).resolve()
        for script_name in MCP_SERVER_SCOPE_TO_SCRIPTS[selected_scope]
    ]
    missing_scripts = [str(script_path) for script_path in resolved_scripts if not script_path.exists()]
    if missing_scripts:
        raise FileNotFoundError(
            f"MCP server script(s) not found for scope '{selected_scope}': {missing_scripts}"
        )
    return resolved_scripts


def _resolve_server_scope_name(scope_value: str) -> str:
    normalized_scope = str(scope_value or DEFAULT_MCP_SERVER_SCOPE).strip().lower()
    selected_scope = (
        normalized_scope
        if normalized_scope in MCP_SERVER_SCOPE_TO_NAME
        else DEFAULT_MCP_SERVER_SCOPE
    )
    return MCP_SERVER_SCOPE_TO_NAME[selected_scope]

# define callback to process user query in conversational flow
@app.callback(Output("chat-component", "messages"),
              Input("chat-component", "new_message"),
              State("chat-component", "messages"),
              State("generator-model-dropdown", "value"),
              State("mcp-server-dropdown", "value"),
              prevent_initial_call=True)

async def handle_chat(new_message: str,
                      messages: List[str],
                      generator_model: str,
                      mcp_server_scope: str) -> List[str]:
    """
    Enable conversational flow between user and LLM.

    Args:
        new_message: Last message object entered by user.

        messages: Message object.

    Returns:
        Updated message object.
    """

    # if no new message object exists, return previous message object
    if not new_message:
        return messages or []

    # otherwise, add latest message to message object
    updated_messages = (messages or []) + [new_message]

    # if the latest message is coming from the user
    if new_message["role"] == "user":
        # initialize llm instance using user-selected model
        selected_model = generator_model or "mistral/mistral-small-2506"
        selected_mcp_server_name = _resolve_server_scope_name(mcp_server_scope)
        LLM_client = LLM_MCP_obj(
            model=selected_model,
            mcp_server_name=selected_mcp_server_name,
        )

        try:
            server_scripts = _resolve_server_scope_scripts(mcp_server_scope)
            if not server_scripts:
                # Explicit no-tool mode.
                pass
            elif len(server_scripts) == 1:
                await LLM_client.connect_to_server(server_script_path=server_scripts[0])
            else:
                raise RuntimeError(
                    "Invalid MCP scope configuration: multiple MCP servers are not allowed."
                )

            # process user prompt
            bot_response = await LLM_client.process_query(query=new_message['content'])
        except Exception as exc:
            bot_response = {
                "role": "assistant",
                "content": f"Request failed for selected MCP scope '{mcp_server_scope}': {exc}",
            }
        finally:
            with suppress(Exception):
                await LLM_client.cleanup()

        # return updated message object and LLM response
        return updated_messages + [bot_response]

    # return updated message object
    return updated_messages
