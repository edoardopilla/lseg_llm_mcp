# import necessary libraries
from dash import Dash, dcc, html
from dash_chat import ChatComponent

# define color palette
colormap = {'black': '#000000',
            'blue': "#0D45B6",
            'white': '#FFFFFF'}

# define logo path
header_logo = 'assets/resized.png'

# initialize dash instance
app = Dash(__name__)

# specify dashboard title
app.title = 'Bypassing Document Ingestion - Custom LSEG MCP server'

# specify style for inactive tabs
tab_style = {'color': colormap['blue'],
             'backgroundColor': colormap['white'],
             'borderBottom': colormap['white'],
             'borderTop': colormap['white'],
             'fontWeight': '400',
             'line-height': '1vh'}

# specify style for active tab
tab_selected_style = {'color': colormap['blue'],
                      'backgroundColor': colormap['white'],
                      'borderBottom': colormap['white'],
                      'borderTop': colormap['white'],
                      'fontWeight': 'bold',
                      'line-height': '1vh'}

# specify dashboard layout
app.layout = html.Div([html.H2(style={'display': 'flex'},
                               children=[html.Img(src=header_logo,
                                                  className='center',
                                                  style={'display': 'block',
                                                         'margin-right': 'auto'}),

                                         html.H3(children='Bypassing Document Ingestion - Custom LSEG MCP server',
                                                 style={'color': colormap['blue'],
                                                        'font-size': '24px',
                                                        'font-weight': 'bold',
                                                        'margin-right': 'auto',
                                                        'margin-bottom': 'auto',
                                                        'text-align': 'left'})]),

                                        # define disclaimer
                                        html.Div(children = [html.Label(['Disclaimer: No business relationship exists between the author and LSEG.'])],
                                                
                                                className='sources-disclaimer'),

                       # initialize tabs
                                # define first tab
                       dcc.Tabs([dcc.Tab(label='Single-turn QA',
                                         selected_style=tab_selected_style,
                                         style=tab_style,
                                         
                                                                               # define tab1 title
                                         children=[html.Div(children=[html.Div(children='Interact with LSEG data',
                                                                               style={'color': colormap['blue'],
                                                                                      'font-size': '24px',
                                                                                      'font-weight': 'bold',
                                                                                      'margin-right': 'auto',
                                                                                      'margin-bottom': 'auto',
                                                                                      'margin-top': '1%',
                                                                                      'text-align': 'left'}),

                                                                       

                                                                      # define model selector
                                                                      html.Div(
                                                                          children=[
                                                                              html.Label(
                                                                                  'Generator model',
                                                                                  style={
                                                                                      'color': colormap['blue'],
                                                                                      'font-weight': 'bold',
                                                                                      'margin-bottom': '8px',
                                                                                      'display': 'block'
                                                                                  }
                                                                              ),
                                                                              dcc.Dropdown(
                                                                                  id='generator-model-dropdown',
                                                                                  options=[
                                                                                      {'label': 'OpenAI GPT-4o mini', 'value': 'openai/gpt-4o-mini'},
                                                                                      {'label': 'Gemini 2.5 Flash Lite', 'value': 'gemini/gemini-2.5-flash-lite'},
                                                                                      {'label': 'Anthropic Claude Haiku 4.5', 'value': 'anthropic/claude-haiku-4-5'},
                                                                                      {'label': 'Mistral Small 2506', 'value': 'mistral/mistral-small-2506'},
                                                                                      {'label': 'ZAI GLM 4.5', 'value': 'zai/glm-4.5'},
                                                                                  ],
                                                                                  value='openai/gpt-4o-mini',
                                                                                  clearable=False,
                                                                                  searchable=False,
                                                                                  style={'width': '420px'}
                                                                              ),
                                                                          ],
                                                                          style={'margin-top': '1%', 'margin-bottom': '1%'}
                                                                      ),

                                                                      html.Div(style={'display': 'inline-block'},
                                                                                    
                                                                               # define text area for question input
                                                                               children=[html.Div([ChatComponent(id="chat-component",
                                                                                                                 messages=[])])])])],                                               
                                         )])])

# run callbacks script
exec(open(r'callbacks.py').read())

# host dashboard locally
if __name__ == '__main__':
    app.run(debug=True)