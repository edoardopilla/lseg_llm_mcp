# import necessary libraries
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from typing import Any, Dict, List

import json
import os
import pandas as pd

class LLM_MCP_server:
    """
    Class to establish LLM and MCP functionalities.
    """

    # load environment variables
    load_dotenv()

    def __init__(self,
                 client=AsyncOpenAI(),
                 exit_stack=AsyncExitStack(),
                 max_compl_tokens=512,
                 model='gpt-4o-mini',
                 seed=17,
                 session=None,
                 stdio=None,
                 system_message="You are a helpful assistant.",
                 temper=.01,
                 top_p=.15,
                 write=None):
        """
        Constructor

        Args:
            client: Default client to instantiate.
            exit_stack: Default exit stack for async client.
            max_compl_tokens: Default number of tokens serving as upper bound for completions.
            model: Default model to instantiate.
            seed: Default seed for chat completions.
            session: Default session to instantiate.
            stdio: Default read stream for client session.
            system_message: Default system message passed to chat.
            temper: Default temperature for chat completions.
            top_p: Default top_p for chat completions.
            write: Default write stream for client session.
        """

        self.client=client
        self.exit_stack=exit_stack
        self.max_compl_tokens=max_compl_tokens
        self.model=model
        self.seed=seed
        self.session=session
        self.stdio=stdio
        self.system_message=system_message
        self.temper=temper
        self.top_p=top_p
        self.write=write

    async def connect_to_server(self,
                                server_script_path: str='server.py'):
        """
        Connect to MCP server.

        Args:
            server_script_path: Path to the server script.
        """

        # server configuration
        server_params=StdioServerParameters(command='python',
                                            args=[server_script_path])

        # connect to server
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))

        stdio, write = stdio_transport

        session = await self.exit_stack.enter_async_context(ClientSession(read_stream=stdio,
                                                                          write_stream=write))
        
        # initialize connection
        await session.initialize()

        # list available tools
        tools_result = await session.list_tools()

        print('\nConnected to server with tools:')

        for tool in tools_result.tools:
            print(f' - {tool.name}: {tool.description}')

        # attribute session to self, allows to list tool in subsequent method
        self.session=session

    async def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        Get available tools from MCP server in OpenAI format.
        
        Returns:
            A list of tools in OpenAI format.
        """

        # list tools
        tools_result = await self.session.list_tools()

        # return tools in OpenAI format
        return [{'type': 'function',
                 'function': {'name': tool.name,
                              'description': tool.description,
                              'parameters': tool.inputSchema}} for tool in tools_result.tools]

    async def process_query(self,
                            query: str) -> str:
        """
        Process query using OpenAI and available MCP tools.

        Args:
            query: User query.

        Returns:
            Response from OpenAI.
        """

        # get available tools
        tools = await self.get_mcp_tools()

        # read OAPermID map
        #content = await self.session.read_resource("data://oapermids")

        # extract string storing file content
        #comp_oapermids = content.contents[0].text

        # initial openai api call
        response = await self.client.chat.completions.create(model=self.model,
                                                             messages=[{'role': 'user',
                                                                        'content': query}],
                                                             seed=self.seed,
                                                             temperature=self.temper,
                                                             tools=tools,
                                                             tool_choice="auto",
                                                             top_p=self.top_p)

        # get assistant response
        assistant_message = response.choices[0].message

        # initialize conversation with user query and assistant response
        messages = [{'role': 'user', 'content': query},
                    assistant_message]
        
        # create knowledge base and earnings calls folders if not existing
        os.makedirs('./knowledge_base/earnings_calls', exist_ok=True)
        
        # create tool call history file if not existing
        if not os.path.exists('tool_call_hist.json'):
             
            with open('tool_call_hist.json', 'w') as file:
                    json.dump([], file)
        
        with open('tool_call_hist.json', 'r') as file:
                tool_hist_dct_old = json.load(file)
        
        tool_hist_dct_lst = []

        tool_hist_dct = {'question': query,
                         'question_tkns': None,
                         'datetime': pd.to_datetime('now').strftime('%Y-%m-%dT%H:%M:%S'),
                         'tool_name': None,
                         'tool_args': None,
                         'tool_resp': None,
                         'answer': 'final_answer_placeholder',
                         'answer_tkns': None,
                         'tot_tkns': None}

        # handle tool calls if present
        if assistant_message.tool_calls:

            # process each tool call
            for tool_call in assistant_message.tool_calls:

                tool_hist_dct = {'question': query,
                         'question_tkns': response.usage.prompt_tokens,
                         'datetime': pd.to_datetime('now').strftime('%Y-%m-%dT%H:%M:%S'),
                         'tool_name': None,
                         'tool_args': None,
                         'tool_resp': None,
                         'answer': 'final_answer_placeholder',
                         'answer_tkns': response.usage.completion_tokens,
                         'tot_tkns': response.usage.total_tokens}

                # execute tool call
                result = await self.session.call_tool(tool_call.function.name,
                                                      arguments=json.loads(tool_call.function.arguments))
                
                tool_hist_dct.update({'tool_name': tool_call.function.name,
                                      'tool_args': tool_call.function.arguments,
                                      'tool_resp': result.content[0].text})
                
                tool_hist_dct_lst.append(tool_hist_dct)

                print(f'Using tool: {tool_call.function.name} with args: {tool_call.function.arguments}')

                # add tool response to conversation
                messages.append({'role': 'tool',
                                 'tool_call_id': tool_call.id,
                                 'content': result.content[0].text})
                
                # tool_hist_dct = {query: [pd.to_datetime('now').strftime('%Y-%m-%dT%H:%M:%S'),
                #                          tool_call.function.name,
                #                          tool_call.function.arguments,
                #                          result.content[0].text]}

            # tool_hist_dct_merge = {k: [d[k] for d in tool_hist_dct_lst] for k in tool_hist_dct_lst[0]}

            messages.append({'role': 'system',
                             'content': self.system_message})

            # get final response from OpenAI with tool results
            final_response = await self.client.chat.completions.create(model=self.model,
                                                                       messages=messages,
                                                                       max_completion_tokens=self.max_compl_tokens,
                                                                       seed=self.seed,
                                                                       temperature=self.temper,
                                                                       tools=tools,
                                                                       tool_choice='none',
                                                                       top_p=self.top_p)  # don't allow more tool calls
            
            for i in range(len(tool_hist_dct_lst)):
                tool_hist_dct_lst[i].update({'question_tkns': response.usage.prompt_tokens + final_response.usage.prompt_tokens,
                                             'answer': final_response.choices[0].message.content.strip(),
                                             'answer_tkns': response.usage.completion_tokens + final_response.usage.completion_tokens,
                                             'tot_tkns': response.usage.total_tokens + final_response.usage.total_tokens})
                
            # for i in range(len(tool_hist_dct_merge[query])):
            #     tool_hist_dct_merge[query][i].append(final_response.choices[0].message.content.strip())

            tool_hist_dct_new = tool_hist_dct_old.copy()

            for dct in tool_hist_dct_lst:
                tool_hist_dct_new.append(dct)

            with open('tool_call_hist.json', 'w') as f:
                json.dump(tool_hist_dct_new,
                          f,
                          indent=1)

            return {"role": "assistant", "content": final_response.choices[0].message.content.strip()}
        
        tool_hist_dct_new = tool_hist_dct_old.copy()

        tool_hist_dct.update({'question_tkns': response.usage.prompt_tokens,
                              'answer': response.choices[0].message.content.strip(),
                              'answer_tkns': response.usage.completion_tokens,
                              'tot_tkns': response.usage.total_tokens})

        tool_hist_dct_new.append(tool_hist_dct)

        with open('tool_call_hist.json', 'w') as f:
                json.dump(tool_hist_dct_new,
                          f,
                          indent=1)

        return {"role": "assistant", "content": assistant_message.content.strip()}
    
    async def cleanup(self):
        """
        Clean up resources.
        """

        await self.exit_stack.aclose()