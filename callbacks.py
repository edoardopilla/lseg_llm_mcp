# import necessary libraries
from LLM_MCP import *
from dash import Output, Input, State

# initialize llm instance
LLM_client = LLM_MCP_server()

# define callback to process user query in conversational flow
@app.callback(Output("chat-component", "messages"),
              Input("chat-component", "new_message"),
              State("chat-component", "messages"),
              prevent_initial_call=True)

async def handle_chat(new_message,
                      messages):
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
        return messages

    # otherwise, add latest message to message object
    updated_messages = messages + [new_message]

    # if the latest message is coming from the user
    if new_message["role"] == "user":

        # connect to server
        await LLM_client.connect_to_server('server.py')

        # process user prompt
        bot_response = await LLM_client.process_query(query=new_message['content'])

        # clean up resources
        await LLM_client.cleanup()

        # return updated message object and LLM response
        return updated_messages + [bot_response]

    # return updated message object
    return updated_messages