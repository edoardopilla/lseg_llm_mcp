# import necessary libraries
from dash import Dash, dcc, html
from dash_chat import ChatComponent

# define color palette
colormap = {'black': '#000000',
            'blue': "#0D45B6",
            'white': '#FFFFFF',
            'dark-bg': '#0f1419',
            'darker-bg': '#0a0e13',
            'card-bg': '#1a2332',
            'text-light': '#e8eaed',
            'text-muted': '#8b92a0',
            'accent-blue': '#3b82f6',
            'accent-red': '#ef4444',
            'border-color': '#2a3f5f'}

# define logo path
header_logo = 'assets/resized.png'

# initialize dash instance
app = Dash(__name__)

# specify dashboard title
app.title = 'Bypassing Document Ingestion - Custom MCP servers'

# specify style for inactive tabs
tab_style = {'color': colormap['text-muted'],
             'backgroundColor': 'transparent',
             'borderBottom': '2px solid transparent',
             'borderTop': 'none',
             'borderLeft': 'none',
             'borderRight': 'none',
             'fontWeight': '400',
             'line-height': '1vh',
             'padding': '12px 20px',
             'cursor': 'pointer',
             'transition': 'all 0.3s ease'}

# specify style for active tab
tab_selected_style = {'color': colormap['accent-blue'],
                      'backgroundColor': 'transparent',
                      'borderBottom': '3px solid ' + colormap['accent-blue'],
                      'borderTop': 'none',
                      'borderLeft': 'none',
                      'borderRight': 'none',
                      'fontWeight': 'bold',
                      'line-height': '1vh',
                      'padding': '12px 20px'}

# specify dashboard layout
app.layout = html.Div([
    # Header container
    html.Div(className='header-container',
             children=[
                 html.Div(className='header-content',
                          style={'display': 'flex', 'align-items': 'center', 'gap': '20px'},
                          children=[
                              html.Img(src=header_logo,
                                      className='header-logo',
                                      style={'height': '60px', 'width': 'auto'}),
                              html.H3(children='Bypassing Document Ingestion - Custom MCP Servers',
                                     className='header-title',
                                     style={'color': colormap['text-light'],
                                            'font-size': '24px',
                                            'font-weight': 'bold',
                                            'margin': '0',
                                            'text-align': 'left'})
                          ])
             ]),
    
    # Disclaimer
    html.Div(className='sources-disclaimer',
             children=[html.Label('Disclaimer: No business relationship exists between the author and LSEG.')],
             style={'color': colormap['text-muted'],
                    'font-size': '12px',
                    'margin-top': '12px',
                    'margin-bottom': '12px',
                    'text-align': 'left'}),
    
    # Main content - Tabs
    dcc.Tabs([
        dcc.Tab(
            label='Single-turn QA',
            selected_style=tab_selected_style,
            style=tab_style,
            className='custom-tab',
            children=[
                html.Div(className='tab-content',
                         children=[
                             # Tab title
                             html.Div(className='tab-title-section',
                                     children=[
                                         html.Div(children='Interact with selected MCP data',
                                                 style={'color': colormap['accent-blue'],
                                                        'font-size': '24px',
                                                        'font-weight': 'bold',
                                                        'margin-bottom': '24px',
                                                        'text-align': 'left'})
                                     ]),
                             
                             # Model selector section
                             html.Div(className='form-section',
                                     children=[
                                         html.Div(className='form-group',
                                                 children=[
                                                     html.Label(
                                                         'Generator Model',
                                                         className='form-label',
                                                         style={
                                                             'color': colormap['text-light'],
                                                             'font-weight': 'bold',
                                                             'margin-bottom': '8px',
                                                             'display': 'block'
                                                         }
                                                     ),
                                                      dcc.Dropdown(
                                                          id='generator-model-dropdown',
                                                          options=[
                                                              {'label': 'OpenAI GPT-4o mini', 'value': 'openai/gpt-4o-mini'},
                                                              {'label': 'Gemini 3.1 Flash Lite', 'value': 'gemini/gemini-3.1-flash-lite'},
                                                              {'label': 'Anthropic Claude Haiku 4.5', 'value': 'anthropic/claude-haiku-4-5'},
                                                              {'label': 'Mistral Small 2506', 'value': 'mistral/mistral-small-2506'},
                                                              {'label': 'DeepSeek V4 Flash', 'value': 'deepseek/deepseek-v4-flash'},
                                                          ],
                                                          value='mistral/mistral-small-2506',
                                                          clearable=False,
                                                          searchable=False,
                                                          className='model-dropdown',
                                                          style={'width': '100%', 'maxWidth': '420px'}
                                                      ),
                                                  ]),
                                         html.Div(className='form-group',
                                                 children=[
                                                     html.Label(
                                                         'MCP Server Access',
                                                         className='form-label',
                                                         style={
                                                             'color': colormap['text-light'],
                                                             'font-weight': 'bold',
                                                             'margin-bottom': '8px',
                                                             'margin-top': '12px',
                                                             'display': 'block'
                                                         }
                                                     ),
                                                     dcc.Dropdown(
                                                         id='mcp-server-dropdown',
                                                         options=[
                                                             {'label': 'LSEG MCP', 'value': 'lseg'},
                                                             {'label': 'SEC EDGAR MCP', 'value': 'edgar'},
                                                             {'label': 'RAG 10-K Baseline MCP', 'value': 'rag'},
                                                             {'label': 'No MCP Server (No Tools)', 'value': 'none'},
                                                         ],
                                                         value='lseg',
                                                         clearable=False,
                                                         searchable=False,
                                                         className='model-dropdown',
                                                         style={'width': '100%', 'maxWidth': '420px'}
                                                     ),
                                                 ])
                                      ]),
                             
                             # Chat component section
                             html.Div(className='chat-section',
                                     children=[
                                         html.Div(children=[
                                             ChatComponent(id="chat-component",
                                                          messages=[],
                                                          container_style={
                                                              'backgroundColor': colormap['card-bg'],
                                                              'color': colormap['text-light'],
                                                              'borderRadius': '12px',
                                                              'border': f"1px solid {colormap['border-color']}",
                                                              'maxHeight': '450px',
                                                              'overflowY': 'auto'
                                                          },
                                                          input_container_style={
                                                              'backgroundColor': colormap['darker-bg'],
                                                              'borderTop': f"1px solid {colormap['border-color']}"
                                                          },
                                                          input_text_style={
                                                              'color': colormap['text-light'],
                                                              'backgroundColor': colormap['darker-bg']
                                                          },
                                                          user_bubble_style={
                                                              'backgroundColor': colormap['accent-blue'],
                                                              'color': '#ffffff',
                                                              'borderRadius': '12px'
                                                          },
                                                          assistant_bubble_style={
                                                              'backgroundColor': colormap['border-color'],
                                                              'color': colormap['text-light'],
                                                              'borderRadius': '12px'
                                                          })
                                         ])
                                     ])
                         ])
            ]
        )
    ],
    className='custom-tabs',
    parent_className='custom-tabs-parent')
],
className='main-container')

# run callbacks script
exec(open(r'callbacks.py').read())

# host dashboard locally
if __name__ == '__main__':
    app.run(debug=False)
