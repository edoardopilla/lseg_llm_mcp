# import necessary libraries
from dash import Dash, dcc, html
from dash_chat import ChatComponent

# define color palette
colormap = {'black': '#000000',
            'white': '#FFFFFF'}

# define logo path
header_logo = 'assets/resized.png'

# initialize dash instance
app = Dash(__name__)

# specify dashboard title
app.title = 'LSEG APIs MCP server'

# specify style for inactive tabs
tab_style = {'color': colormap['black'],
             'backgroundColor': colormap['white'],
             'borderBottom': colormap['white'],
             'borderTop': colormap['white'],
             'fontWeight': '400',
             'line-height': '1vh'}

# specify style for active tab
tab_selected_style = {'color': colormap['black'],
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

                                         html.H3(children='LSEG APIs MCP server',
                                                 style={'color': colormap['black'],
                                                        'font-size': '24px',
                                                        'font-weight': 'normal',
                                                        'margin-right': 'auto',
                                                        'margin-bottom': 'auto',
                                                        'text-align': 'left'})]),

                       # initialize tabs
                                # define first tab
                       dcc.Tabs([dcc.Tab(label='Chat with LSEG services',
                                         selected_style=tab_selected_style,
                                         style=tab_style,
                                         
                                                                               # define tab1 title
                                         children=[html.Div(children=[html.Div(children='Chat with LSEG data',
                                                                               style={'color': colormap['black'],
                                                                                      'font-size': '24px',
                                                                                      'font-weight': 'normal',
                                                                                      'margin-right': 'auto',
                                                                                      'margin-bottom': 'auto',
                                                                                      'text-align': 'left'}),

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