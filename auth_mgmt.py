# import necessary libraries
from dotenv import load_dotenv, set_key

import os
import requests

def request_lseg_bearer_token():
    """
    Requests the generation of a temporary bearer token to process further API requests.

    Args:
        None

    Returns:
        Empty.
    """

    # define auth endpoint
    auth_url = 'https://api.refinitiv.com/auth/oauth2/v1/token'

    # load environment variables
    load_dotenv()

    # define credentials for v1 auth
    credentials = {'username': os.getenv('LSEG_USERNAME'),
                   'password': os.getenv('LSEG_PASSWORD'),
                   'client_id': os.getenv('LSEG_EDP_APP_KEY'),
                   'grant_type': 'password',
                   'scope': 'trapi',
                   'takeExclusiveSignOnControl': 'true'}

    # send POST request
    response = requests.post(url=auth_url,
                             data=credentials)

    # if generated correctly, store the access token for further use
    if response.status_code == 200:
        lseg_access_token = response.json().get('access_token')

        # save to .env file
        set_key(dotenv_path='.env',
                key_to_set='LSEG_ACCESS_TOKEN',
                value_to_set=lseg_access_token)
        
        # load .env file
        load_dotenv(override=True)

        return f'Tokens generated successfully'

    # else, prompt user to fix issue
    else:
        return f'Failed to generate bearer token: {response.status_code}, {response.json()}'