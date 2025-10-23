# import necessary libraries
from auth_mgmt import *
from fastmcp import FastMCP
from pypdf import PdfReader
from typing import List

import io
import json
import os
import pandas as pd
import re
import time

# create MCP server
mcp = FastMCP(name='LSEG APIs MCP server',
              host='127.0.0.1') # kept here regardless of deprecated warning to avoid RuntimeError: Attempted to exit cancel scope in a different task than it was entered in

# @mcp.tool()
# def get_OAPermID(query: str) -> str:
#     """
#     Look up the OAPermID for a given organisation, useful if no mapping between entity name and OAPermID exists.

#     Args:
#         query: Free-form, unstructured text search.

#     Returns:
#         The relevant OAPermID.
#     """

#     # attempt bearer token generation or refresh
#     request_lseg_bearer_token()

#     import requests
#     import json
#     import os

#     url = 'https://api.refinitiv.com/discovery/searchlight/v1/'

#     payload = json.dumps({'Query': query,
#                           'Select': 'DocumentTitle,OAPermID',
#                           'Top': 1,
#                           'View': 'Organisations'})

#     headers = {'Content-Type': 'application/json',
#                'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

#     response = requests.post(url=url,
#                              headers=headers,
#                              data=payload)
    
#     comp_oapermid = response.json()['Hits'][0]['OAPermID']

#     return comp_oapermid

# @mcp.resource('data://oapermids')
# def get_oapermid() -> str:
#     """
#     Provides a mapping between OAPermIDs, company names and primary RICs.
#     """
#     with open('./knowledge_base/resources/finbench_sp500_jun25_oapermid_map.json', 'r') as file:
#         comp_oapermids = json.load(file)

#     return json.dumps(comp_oapermids)

@mcp.tool()
def get_earningscall_transcript(comp_name: str,
                                period: str = f'{pd.to_datetime('now').strftime('%Y-%m-%d')}') -> str:
    """
    Get the relevant earning call transcript for the given primary RIC and financial period.

    Args:
        comp_name: The name of the company whose earnings call must be retrieved.

        period: The financial period for which the user wishes to retrieve the earnings call transcript,
                to be converted to end-of-quarter date in format YYYY-MM-DD from the user prompt
                (e.g. 'Q1 2025': '2025-03-31', '21Q3': '2021-09-30').

    Returns:
        The earnings call transcript.
    """

    # placeholder date for Q1 2025 - 31.03.2025
    qn_yyyy_date = pd.to_datetime(period).tz_localize('UTC')

    # calculate page number
    pag_num = int((((pd.to_datetime('now').tz_localize('UTC') - qn_yyyy_date) / pd.Timedelta(365.2524, 'd')) / 5) + 1)

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

    time.sleep(1)

    # set transcript lookup URL
    url = f"https://api.refinitiv.com/user-framework/mobile/overview-service/v1/corp/events/{primary_ric}"

    headers = {'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    payload = {'pastpage': pag_num,
               'pastlimit': 20,
               'filterId': '1001371874'}

    response = requests.get(url, headers=headers, params=payload)

    time.sleep(1)

    timedelta_lst = []

    for i in range(len(response.json()['data']['past'])):
        timedelt = abs(pd.to_datetime(response.json()['data']['past'][i]['datetime']) - qn_yyyy_date)
        timedelta_lst.append(timedelt)

    filtd_dct = [dct for dct in response.json()['data']['past'] if abs(pd.to_datetime(dct['datetime']) - qn_yyyy_date) == min(timedelta_lst)]

    pdf_file_path = f'./knowledge_base/earnings_calls/{filtd_dct[0]['title']}.pdf'
    
    if os.path.isfile(pdf_file_path):
        pdf_file = PdfReader(pdf_file_path)

        earningscall_transcript_str = '\n\n'.join([pag.extract_text() for pag in pdf_file.pages])
                                                  
        return earningscall_transcript_str                                

    else:
        transcript_url = filtd_dct[0]['fileUrl']

        url = transcript_url

        headers = {'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

        # get transcript
        response = requests.get(url=url,
                                headers=headers)
        
        with open(pdf_file_path, 'wb') as f:
            f.write(response.content)

        # parse response content
        on_fly_mem_obj = io.BytesIO(response.content)

        # read pdf file
        pdf_file = PdfReader(on_fly_mem_obj)

    # extract text - REGEX WORKS IN LSEG_DATALIB ENV BUT NOT HERE, NOT SURE WHAT THE PROBLEM IS
    # page_lst = []
    # for page in pdf_file.pages:
    #     page_lst.append(re.split(r'affiliated companies.\d+',page.extract_text())[1])

    # earningscall_transcript_str = '\n\n'.join(page_lst)
    
        earningscall_transcript_str = '\n\n'.join([pag.extract_text() for pag in pdf_file.pages])

        return earningscall_transcript_str

@mcp.tool()
def get_balancesheet_statement(comp_name: str,
                               period: str = f'FY{str(pd.to_datetime('now').year - 1)}',
                               scale: str = '6') -> str:
    """
    Gets the balance sheet statement for the given universe. Entries are reported in millions by default,
    therefore they may require scaling if the user wishes to receive the answer in a different format.

    Args:
        comp_name: The name of the company whose financial statement must be retrieved.

        period: The financial period the user wishes to retrieve, defaults to the current year minus 1,
                reflecting the fact that results are only reported once the fiscal year ends, usually
                a few months after the beginning of a new calendar year, acceptable formats for frequency are:
                {'Fiscal Year': 'FYyyyy',
                 'Fiscal Quarter': 'FQnyyyy'}
                
                (e.g. 'Q2 2019': 'FQ22019', 'fiscal year 2022': 'FY2022', 'third quarter of 2023': 'FQ32023').

        scale: One of the following options for formatting the answer:
               {'Trillions': '12',
                'Billions': '9',
                'Hundred Million': '8',
                'Ten Million': '7',
                'Millions': '6',
                'Hundred Thousand': '5',
                'Ten Thousand': '4',
                'Thousands': '3',
                'Hundreds': '2',
                'No Scaling': '0'}

    Returns:
        The filtered balance sheet statement text.
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

    time.sleep(1)
    
    url = 'https://api.refinitiv.com/data/datagrid/beta1/'

    payload = json.dumps({'universe': [comp_oapermid],
                          'fields': ['TR.F.BalanceSheet.fielddescription',
                                     'TR.F.BalanceSheet'],
                          'parameters': {'Period': period,
                                         'reportingState':'Rsdt',
                                         'consolBasis': 'Consolidated',
                                         'curn':'Native',
                                         'Scale': scale}})
    
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.post(url=url,
                             headers=headers,
                             data=payload)
    
    balancesheet_resp_lst = response.json()['data'].copy()
    
    balancesheet_dct = {}

    for i in range(len(balancesheet_resp_lst)):
        balancesheet_resp_lst[i][1] = re.sub(r'\[(.*?)\]', '-', balancesheet_resp_lst[i][1])
        balancesheet_dct.update({' - '.join(balancesheet_resp_lst[i][1].split(' - ')[0:2]): balancesheet_resp_lst[i][2]})

    balancesheet_str = json.dumps(balancesheet_dct)
    
    return balancesheet_str

@mcp.tool()
def get_cashflow_statement(comp_name: str,
                           period: str = f'FY{str(pd.to_datetime('now').year - 1)}',
                           scale: str = '6') -> str:
    """
    Gets the cash flow statement for the given universe. Entries are reported in millions by default,
    therefore they may require scaling if the user wishes to receive the answer in a different format.

    Args:
        comp_name: The name of the company whose financial statement must be retrieved.

        period: The financial period the user wishes to retrieve, defaults to the current year minus 1,
                reflecting the fact that results are only reported once the fiscal year ends, usually
                a few months after the beginning of a new calendar year.

        scale: One of the following options for formatting the answer:
            {'Trillions': '12',
             'Billions': '9',
             'Hundred Million': '8',
             'Ten Million': '7',
             'Millions': '6',
             'Hundred Thousand': '5',
             'Ten Thousand': '4',
             'Thousands': '3',
             'Hundreds': '2',
             'No Scaling': '0'}

    Returns:
        The filtered cashflow statement text.
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

    time.sleep(1)
    
    url = 'https://api.refinitiv.com/data/datagrid/beta1/'

    payload = json.dumps({'universe': [comp_oapermid],
                          'fields': ['TR.F.CashFlowStatement.fielddescription',
                                     'TR.F.CashFlowStatement'],
                          'parameters': {'Period': period,
                                         'reportingState':'Rsdt',
                                         'consolBasis': 'Consolidated',
                                         'curn':'Native',
                                         'Scale': scale}})
    
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.post(url=url,
                             headers=headers,
                             data=payload)
    
    cashflow_resp_lst = response.json()['data'].copy()
    
    cashflow_dct = {}

    for i in range(len(cashflow_resp_lst)):
        cashflow_resp_lst[i][1] = re.sub(r'\[(.*?)\]', '-', cashflow_resp_lst[i][1])
        cashflow_dct.update({' - '.join(cashflow_resp_lst[i][1].split(' - ')[0:2]): cashflow_resp_lst[i][2]})

    cashflow_str = json.dumps(cashflow_dct)
    
    return cashflow_str

@mcp.tool()
def get_income_statement(comp_name: str,
                         period: str = f'FY{str(pd.to_datetime('now').year - 1)}',
                         scale: str = '6') -> str:
    """
    Gets the income statement for the given universe. Entries are reported in millions by default,
    therefore they may require scaling if the user wishes to receive the answer in a different format.

    Args:
        comp_name: The name of the company whose financial statement must be retrieved.

        period: The financial period the user wishes to retrieve, defaults to the current year minus 1,
                reflecting the fact that results are only reported once the fiscal year ends, usually
                a few months after the beginning of a new calendar year.

        scale: One of the following options for formatting the answer:
            {'Trillions': '12',
             'Billions': '9',
             'Hundred Million': '8',
             'Ten Million': '7',
             'Millions': '6',
             'Hundred Thousand': '5',
             'Ten Thousand': '4',
             'Thousands': '3',
             'Hundreds': '2',
             'No Scaling': '0'}

    Returns:
        The filtered income statement text.
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

    time.sleep(1)
    
    url = 'https://api.refinitiv.com/data/datagrid/beta1/'

    payload = json.dumps({'universe': [comp_oapermid],
                          'fields': ['TR.F.IncomeStatement.fielddescription',
                                     'TR.F.IncomeStatement'],
                          'parameters': {'Period': period,
                                         'reportingState':'Rsdt',
                                         'consolBasis': 'Consolidated',
                                         'curn':'Native',
                                         'Scale': scale}})
    
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.post(url=url,
                             headers=headers,
                             data=payload)
    
    income_resp_lst = response.json()['data'].copy()
    
    income_dct = {}

    for i in range(len(income_resp_lst)):
        income_resp_lst[i][1] = re.sub(r'\[(.*?)\]', '-', income_resp_lst[i][1])
        income_dct.update({' - '.join(income_resp_lst[i][1].split(' - ')[0:2]): income_resp_lst[i][2]})

    income_str = json.dumps(income_dct)
    
    return income_str

@mcp.tool()
def get_acquisitions(comp_name: str,
                     end_date: str = f'{(pd.to_datetime('now') + pd.offsets.YearEnd()).strftime('%Y-%m-%d')}',
                     start_date: str = f'{(pd.to_datetime('now') - pd.offsets.YearBegin()).strftime('%Y-%m-%d')}') -> str:
    """
    Gets the acquisitions that a company has completed during a given time period.

    Args:
        comp_name: The name of the company whose list of acquisitions must be retrieved.

        end_date: The right boundary to set as a filter to get acquisitions for the relevant time period, formatted as YYYY-MM-DD.

        start_date: The left boundary to set as a filter to get acquisitions for the relevant time period, formatted as YYYY-MM-DD.

    Returns:
        The list of finalized acquisitions as a string.
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

    time.sleep(1)

    url = "https://api.refinitiv.com/discovery/search/v1/"

    payload = json.dumps({'View': 'DealsMergersAndAcquisitions',
                          'Top': 100,
                          'Filter': f"AcquirerRIC eq '{primary_ric}' and (DocumentTitle eq 'Acquisition Of Assets' or DocumentTitle eq 'Merger') and TransactionAnnouncementDate ge {start_date} and TransactionAnnouncementDate le {end_date}",
                          'Select': 'DocumentTitle,TargetCompanyName,TransactionEffectiveDate'})
    
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.post(url=url,
                             headers=headers,
                             data=payload)

    mna_trans_str = json.dumps(response.json())

    return mna_trans_str

# Run the server
if __name__ == '__main__':
    mcp.run(transport='stdio')