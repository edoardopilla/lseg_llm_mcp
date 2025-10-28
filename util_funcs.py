# import necessary libraries
from auth_mgmt import *

import json

def get_company_oapermid(comp_name: str) -> str:
    """
    Get the OAPermID of a company given its name.
    
    Args:
        comp_name (str): The name of the company.

    Returns:
        comp_oapermid (str): The OAPermID of the company.
    """

    # attempt bearer token generation or refresh
    request_lseg_bearer_token()

    url = 'https://api.refinitiv.com/discovery/searchlight/v1/'

    payload = json.dumps({'Query': comp_name,
                          'Select': 'DocumentTitle,OAPermID',
                          'Top': 1,
                          'View': 'Organisations'})

    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.post(url=url,
                             headers=headers,
                             data=payload)
    
    comp_oapermid = response.json()['Hits'][0]['OAPermID']

    return comp_oapermid

def get_company_primaryric(comp_name: str) -> str:
    """
    Get the primary RIC of a company given its name.
    
    Args:
        comp_name (str): The name of the company.

    Returns:
        primary_ric (str): The primary RIC of the company.
    """
    
    # attempt bearer token generation or refresh
    request_lseg_bearer_token()

    url = 'https://api.refinitiv.com/discovery/searchlight/v1/'

    payload = json.dumps({'Query': comp_name,
                          'Select': 'DocumentTitle,PrimaryRIC',
                          'Top': 1,
                          'View': 'Organisations'})

    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.post(url=url,
                             headers=headers,
                             data=payload)
    
    primary_ric = response.json()['Hits'][0]['PrimaryRIC']

    return primary_ric
    