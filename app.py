# import necessary libraries
from dash import Dash, dcc, html
from dash_chat import ChatComponent

# define color palette
colormap = {'blue': '#003299',
            'yellow': '#FFB400',
            'orange': '#FF4B00',
            'light_green': '#65B800',
            'cyan': '#00B1EA',
            'dark_green': '#007816',
            'purple': '#8139C6',
            'dark_gray': '#5C5C5C',
            'gray': '#A9A9A9',
            'grid': '#D9D9D9',
            'labels': '#535353',
            'axes': '#7D7D7D'}

# define logo path
header_logo = 'assets/resized.png'

# initialize dash instance
app = Dash(__name__)

# specify dashboard title (this is what is displayed in web browser tab)
app.title = 'LSEG APIs MCP server'

# specify style for inactive tabs
tab_style = {'color': colormap['blue'],
             'borderBottom': '#FFFFFF',
             'fontWeight': '400',
             'borderTop': '#FFFFFF',
             'backgroundColor': '#FFFFFF',
             'line-height': '1vh'}

# specify style for active tab
tab_selected_style = {'color': colormap['blue'],
                      'borderBottom': '#FFFFFF',
                      'fontWeight': 'bold',
                      'borderTop': '#FFFFFF',
                      'backgroundColor': '#FFFFFF',
                      'line-height': '1vh'}

# specify dashboard layout
app.layout = html.Div([html.H2(style={'display': 'flex'},
                               children=[html.Img(src=header_logo,
                                                  className='center'),
                                         html.H3(children='LSEG APIs MCP server',
                                                 className='header-title')]),

                       # initialize tabs
                                # define first tab
                       dcc.Tabs([dcc.Tab(style=tab_style,
                                         selected_style=tab_selected_style,
                                         label='Chat with LSEG services',
                                         
                                                                                   # define tab1 title
                                         children=[html.Div(children=[html.Div(children='Chat with LSEG data',
                                                                               className='header-title'),

                                                                      html.Div(style={'display': 'inline-block'},
                                                                                   
                                                                                   # define text area for question input
                                                                               children=[html.Div([ChatComponent(id="chat-component",
                                                                                                                 messages=[])])])])],
                                                                                        
                                         className='wrapper')])])

# run callbacks script
exec(open(r'callbacks.py').read())

# host dashboard locally
if __name__ == '__main__':
    app.run(debug=True)