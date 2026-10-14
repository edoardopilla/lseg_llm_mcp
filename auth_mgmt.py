# import necessary libraries
from dotenv import load_dotenv, set_key

import os
import requests
from datetime import datetime, timedelta, timezone


# Refresh slightly before hard expiry to avoid edge races.
TOKEN_EXPIRY_SAFETY_WINDOW_SECONDS = 30


def _safe_response_json(response):
    """Return JSON payload when available, otherwise response text."""
    try:
        return response.json()
    except ValueError:
        return {'raw_response': response.text}


def _utc_now():
    """Return current UTC timestamp as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def _format_utc_timestamp(value):
    """Serialize UTC datetime to ISO-8601 `Z` format."""
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_utc_timestamp(value):
    """Parse ISO-8601 UTC timestamp from env, returning None on failure."""
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    try:
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_expires_in_seconds(expires_in):
    """Normalize auth payload `expires_in` value to int seconds when possible."""
    if expires_in is None:
        return None

    try:
        parsed = int(str(expires_in).strip())
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None
    return parsed


def _compute_expiration_timestamp(expires_in):
    """
    Build absolute UTC expiry timestamp from `expires_in` seconds.

    Returns:
        datetime | None: Expiry timestamp in UTC when parseable.
    """
    expires_in_seconds = _parse_expires_in_seconds(expires_in)
    if expires_in_seconds is None:
        return None

    return _utc_now() + timedelta(seconds=expires_in_seconds)


def _is_cached_access_token_valid():
    """
    Return True when a local access token exists and has not reached expiry window.

    This allows tool calls to skip unnecessary refresh/login requests.
    """
    access_token = os.getenv('LSEG_ACCESS_TOKEN')
    if not access_token:
        return False

    expires_at_value = os.getenv('LSEG_ACCESS_TOKEN_EXPIRES_AT')
    expires_at = _parse_utc_timestamp(expires_at_value)
    if expires_at is None:
        return False

    refresh_threshold = expires_at - timedelta(seconds=TOKEN_EXPIRY_SAFETY_WINDOW_SECONDS)
    return _utc_now() < refresh_threshold


def _store_tokens(access_token, refresh_token=None, expires_in=None):
    """
    Persist auth tokens and access-token expiration in `.env` and process env.

    Args:
        access_token (str): Access token returned by auth endpoint.
        refresh_token (str | None): Refresh token returned by auth endpoint.
        expires_in (str | int | None): Access token lifetime in seconds.
    """
    if access_token:
        set_key(dotenv_path='.env',
                key_to_set='LSEG_ACCESS_TOKEN',
                value_to_set=access_token)
        os.environ['LSEG_ACCESS_TOKEN'] = access_token

    expires_at = _compute_expiration_timestamp(expires_in)
    if expires_at is not None:
        expires_at_str = _format_utc_timestamp(expires_at)
        set_key(dotenv_path='.env',
                key_to_set='LSEG_ACCESS_TOKEN_EXPIRES_AT',
                value_to_set=expires_at_str)
        os.environ['LSEG_ACCESS_TOKEN_EXPIRES_AT'] = expires_at_str
    else:
        # Avoid reusing stale expiry metadata for newly-issued tokens.
        set_key(dotenv_path='.env',
                key_to_set='LSEG_ACCESS_TOKEN_EXPIRES_AT',
                value_to_set='')
        os.environ.pop('LSEG_ACCESS_TOKEN_EXPIRES_AT', None)

    if refresh_token:
        set_key(dotenv_path='.env',
                key_to_set='LSEG_REFRESH_TOKEN',
                value_to_set=refresh_token)
        os.environ['LSEG_REFRESH_TOKEN'] = refresh_token

    load_dotenv(override=True)


def request_lseg_bearer_token():
    """
    Request a valid bearer token for LSEG APIs.

    Refresh token is used first when available. Password login is only used as
    fallback when refresh is unavailable or rejected.

    Args:
        None

    Returns:
        str: Status message.
    """

    # define auth endpoint
    auth_url = 'https://api.refinitiv.com/auth/oauth2/v1/token'

    # load environment variables
    load_dotenv(override=True)

    # Reuse cached token whenever still valid to minimize auth requests.
    if _is_cached_access_token_valid():
        return 'Using cached access token'

    client_id = os.getenv('LSEG_EDP_APP_KEY')
    refresh_token = os.getenv('LSEG_REFRESH_TOKEN')
    refresh_error = None

    # 1) Prefer refresh token flow when available.
    if refresh_token:
        refresh_credentials = {'grant_type': 'refresh_token',
                               'refresh_token': refresh_token,
                               'client_id': client_id}

        refresh_response = requests.post(url=auth_url,
                                         data=refresh_credentials)
        refresh_payload = _safe_response_json(refresh_response)

        if refresh_response.status_code == 200:
            _store_tokens(access_token=refresh_payload.get('access_token'),
                          refresh_token=refresh_payload.get('refresh_token') or refresh_token,
                          expires_in=refresh_payload.get('expires_in'))
            return 'Tokens refreshed successfully'

        refresh_error = f'Refresh failed: {refresh_response.status_code}, {refresh_payload}'

    # 2) Fallback to password login only when refresh is unavailable/failed.
    credentials = {'username': os.getenv('LSEG_USERNAME'),
                   'password': os.getenv('LSEG_PASSWORD'),
                   'client_id': client_id,
                   'grant_type': 'password',
                   'scope': 'trapi',
                   'takeExclusiveSignOnControl': 'true'}

    response = requests.post(url=auth_url,
                             data=credentials)
    payload = _safe_response_json(response)

    if response.status_code == 200:
        _store_tokens(access_token=payload.get('access_token'),
                      refresh_token=payload.get('refresh_token') or refresh_token,
                      expires_in=payload.get('expires_in'))
        return 'Tokens generated successfully'

    if refresh_error:
        return f'{refresh_error}; Login failed: {response.status_code}, {payload}'

    return f'Failed to generate bearer token: {response.status_code}, {payload}'


def get_sec_user_agent():
    """
    Return SEC-compliant declared user agent for EDGAR API requests.

    Resolution order:
    1) SEC_USER_AGENT
    2) SEC_COMPANY_NAME + SEC_CONTACT_EMAIL
    3) conservative fallback string
    """
    load_dotenv(override=False)

    explicit_user_agent = str(os.getenv('SEC_USER_AGENT') or '').strip()
    if explicit_user_agent:
        return explicit_user_agent

    company_name = str(os.getenv('SEC_COMPANY_NAME') or '').strip()
    contact_email = str(os.getenv('SEC_CONTACT_EMAIL') or '').strip()
    if company_name and contact_email:
        return f'{company_name} {contact_email}'

    # Keep a non-empty declared value so requests are not sent as undeclared tools.
    return 'lseg-llm-mcp-edgar contact@example.com'


def get_sec_request_headers(host='data.sec.gov'):
    """
    Build request headers for SEC EDGAR APIs.

    SEC guidance asks scripted traffic to declare a user agent and include
    standard compression headers.
    """
    return {
        'User-Agent': get_sec_user_agent(),
        'Accept-Encoding': 'gzip, deflate',
        'Host': host,
    }
