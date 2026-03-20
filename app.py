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

                                                                      # define disclaimer
                                                                      html.Div(children = [html.Label(['Disclaimer: No business relationship exists between the author and LSEG.'])],
                                                                             
                                                                              className='sources-disclaimer'),

                                                                      html.Div(style={'display': 'inline-block'},
                                                                                   
                                                                               # define text area for question input
                                                                               children=[html.Div([ChatComponent(id="chat-component",
                                                                                                                 messages=[])])])])],                                               
                                         )])])

# run callbacks script
exec(open(r'callbacks.py').read())

# host dashboard locally
if __name__ == '__main__':
    app.run(debug=False)