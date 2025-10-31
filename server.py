# import necessary libraries
from fastmcp import FastMCP
from pypdf import PdfReader
from util_funcs import *

import io
import os
import pandas as pd
import re
import time

# create MCP server
mcp = FastMCP(name='LSEG APIs MCP server',
              host='127.0.0.1') # kept here regardless of deprecated warning to avoid RuntimeError: Attempted to exit cancel scope in a different task than it was entered in

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

    # look up the company's primary RIC
    primary_ric = get_company_primaryric(comp_name)

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
    
    # look up the company's OAPermID
    comp_oapermid = get_company_oapermid(comp_name)

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
    
    # look up the company's OAPermID
    comp_oapermid = get_company_oapermid(comp_name)

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
def get_company_business_info(comp_name: str) -> str:
    """
    Gets business information for a given company, including industry sector and NAICS codes.

    Args:
        comp_name: The name of the company whose business information must be retrieved.

    Returns:
        The business information of the company.
    """

    # look up the company's OAPermID
    comp_oapermid = get_company_oapermid(comp_name)

    time.sleep(1)

    url = f'https://api.refinitiv.com/user-framework/mobile/overview-service/v1/corp/business-classification/{comp_oapermid}'

    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.get(url=url,
                            headers=headers)

    business_info_str = json.dumps(response.json()['data'])

    return business_info_str

@mcp.tool()
def get_company_business_summary(comp_name: str) -> str:
    """
    Gets the business summary for a given company.

    Args:
        comp_name: The name of the company whose business summary must be retrieved.

    Retunrs:
        The business summary of the company, along with incorporation information such as incorporation date and country.
    """

    # look up the company's primary RIC
    primary_ric = get_company_primaryric(comp_name)

    time.sleep(1)

    url = f'https://api.refinitiv.com/user-framework/mobile/overview-service/v1//corp/business-summary/{primary_ric}'

    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.get(url=url,
                            headers=headers)

    business_summary_str = json.dumps(response.json()['data'])

    return business_summary_str

@mcp.tool()
def get_company_capital_structure(comp_name: str) -> str:
    """
    Gets the capital structure for a given company.

    Args:
        comp_name: The name of the company whose capital structure must be retrieved.

    Returns:
        Information on the capital structure of the company.
    """

    # look up the company's primary RIC
    primary_ric = get_company_primaryric(comp_name)

    time.sleep(1)

    url = f'https://api.refinitiv.com/user-framework/mobile/overview-service/v1//corp/capital-structure/{primary_ric}'

    headers = {'Content-Type': 'application/json',
               'Accept-Language': 'en-US',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.get(url=url,
                            headers=headers)

    capital_structure_str = json.dumps(response.json()['data'])

    return capital_structure_str

@mcp.tool()
def get_company_fiscalyear_date(comp_name: str,
                                period: str = f'FY{str(pd.to_datetime('now').year - 1)}') -> str:
    """
    Gets the fiscal year end date for a given company.

    Args:
        comp_name: The name of the company whose fiscal year end date must be retrieved.

        period: The financial period the user wishes to retrieve the fiscal year date for,
                defaults to the current year minus 1, reflecting the fact that results are only reported
                once the fiscal year ends, usually a few months after the beginning of a new
                calendar year.
    
    Returns:
        The fiscal year end date of the company.
    """

    # look up the company's OAPermID
    comp_oapermid = get_company_oapermid(comp_name)

    # sleep 1 second
    time.sleep(1)

    # set API endpoint
    url = 'https://api.refinitiv.com/data/datagrid/beta1/'

    # set request payload
    payload = json.dumps({'universe': [comp_oapermid],
                          'fields': ['TR.F.PeriodEndDate'],
                          'parameters': {'Period': period}})

    # set request headers
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    # send POST request
    response = requests.post(url=url,
                             headers=headers,
                             data=payload)

    # extract fiscal year date to string
    fiscalyear_date_str = json.dumps(response.json()['data'][0][1])

    return fiscalyear_date_str

@mcp.tool()
def get_company_officers_directors(comp_name: str) -> str:
    """
    Gets the list of officers and directors for a given company.

    Args:
        comp_name: The name of the company whose officers and directors must be retrieved.

    Returns:
        The list of officers and directors of the company.
    """

    # look up the company's primary RIC
    primary_ric = get_company_primaryric(comp_name)

    time.sleep(1)

    url = f'https://api.refinitiv.com/user-framework/mobile/overview-service/v1/corp/officer-and-directors-public/{primary_ric}'

    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.get(url=url,
                            headers=headers)

    officers_directors_str = json.dumps(response.json()['data']['officersAndDirectorsPublic'])

    return officers_directors_str

@mcp.tool()
def get_company_ownership(comp_name: str) -> str:
    """
    Gets the ownership information for a given company.

    Args:
        comp_name: The name of the company whose ownership information must be retrieved.

    Returns:
        The ownership information of the company.
    """

    # look up the company's primary RIC
    primary_ric = get_company_primaryric(comp_name)

    time.sleep(1)

    url = f'https://api.refinitiv.com/user-framework/mobile/overview-service/v1/corp/ownership/{primary_ric}'

    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    response = requests.get(url=url,
                            headers=headers)

    ownership_str = json.dumps(response.json()['data'])

    return ownership_str

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
    
    # look up the company's primary RIC
    primary_ric = get_company_primaryric(comp_name)

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
    
        earningscall_transcript_str = '\n\n'.join([pag.extract_text() for pag in pdf_file.pages])

        return earningscall_transcript_str

@mcp.tool()
def get_headlines() -> str:
    """
    Gets the top news headlines.

    Args:
        None.

    Returns:
        The top news headlines as a string.
    """

    # attempt bearer token generation
    request_lseg_bearer_token()

    # sleep 1 second
    time.sleep(1)

    # set most recent news URL
    url = "https://api.refinitiv.com/user-framework/mobile/news-service/v1/news/headlines"

    # set request headers
    headers = {'Authorization': f'Bearer {os.getenv('LSEG_ACCESS_TOKEN')}'}

    # set request payload (initialized even if empty to avoid validation error)
    payload = json.dumps({})

    # send post request
    response = requests.post(url=url,
                             headers=headers,
                             data=payload)

    # initialize empty list to collect all headlines
    headlines_lst = []

    # slice response object to get relevant information
    for i in range(len(response.json()['data'])):
        headline_dct = {'title': response.json()['data'][i]['title'],
                        'createdAt': response.json()['data'][i]['createdAt'],
                        'source': response.json()['data'][i]['source']}

        # append to list
        headlines_lst.append(headline_dct)

    headlines_str = json.dumps(headlines_lst)

    # return headlines as string
    return headlines_str

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

    # look up the company's OAPermID
    comp_oapermid = get_company_oapermid(comp_name)

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

# Run the server
if __name__ == '__main__':
    mcp.run(transport='stdio')