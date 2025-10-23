# import necessary libraries
from dotenv import load_dotenv, set_key

import os
import requests

# authenticate or refresh token
def request_lseg_bearer_token():
    """
    Requests the generation of a temporary bearer token to process further API requests.

    Args:
        None

    Returns:
        Empty.
    """

    # define auth URL
    auth_url = 'https://api.refinitiv.com/auth/oauth2/v1/token'

    # load environment variables
    load_dotenv()

    # define credentials for v1 auth
    credentials = {'username': os.getenv('LSEG_USERNAME'),
                   'password': os.getenv('LSEG_PASSWORD'),
                   'grant_type': 'password', # choose between 'password' and 'refresh_token'
                   'client_id': os.getenv('LSEG_EDP_APP_KEY'),
                   'scope': 'trapi', # set to grant access to APIs based on login
                   'takeExclusiveSignOnControl': 'true'} # set to true to kick out from existing sessions (seems to still work while playground is turned on)

    # send POST request
    response = requests.post(url=auth_url,
                             data=credentials)

    # if generated correctly, store the access token for further use
    if response.status_code == 200:
        lseg_access_token = response.json().get('access_token')
        lseg_refresh_token = response.json().get('refresh_token')

        # save to .env file
        set_key(dotenv_path='.env',
                key_to_set='LSEG_ACCESS_TOKEN',
                value_to_set=lseg_access_token)
        
        set_key(dotenv_path='.env',
                key_to_set='LSEG_REFRESH_TOKEN',
                value_to_set=lseg_refresh_token)
        
        # load .env file
        load_dotenv(override=True)

        return f'Tokens generated successfully'

    # if first attempt fails due to session quota reached, attempt to refresh token instead
    elif response.status_code == 400:

        credentials_refresh = {'username': os.getenv('LSEG_USERNAME'),
                               'refresh_token': os.getenv('LSEG_REFRESH_TOKEN'), # generated after first login
                               'grant_type': 'refresh_token',
                               'client_id': os.getenv('LSEG_EDP_APP_KEY')}
        
        # send POST request
        response = requests.post(url=auth_url,
                                 data=credentials_refresh)
        
        # extract tokens
        lseg_access_token = response.json().get('access_token')
        lseg_refresh_token = response.json().get('refresh_token')

        # save to .env file
        set_key(dotenv_path='.env',
                key_to_set='LSEG_ACCESS_TOKEN',
                value_to_set=lseg_access_token)
        
        set_key(dotenv_path='.env',
                key_to_set='LSEG_REFRESH_TOKEN',
                value_to_set=lseg_refresh_token)
        
        # load .env file and overwrite tokens
        load_dotenv(override=True)
        
        return f'Tokens refreshed successfully'

    # else, prompt user to fix issue
    else:
        return f'Failed to generate bearer token: {response.status_code}, {response.json()}'