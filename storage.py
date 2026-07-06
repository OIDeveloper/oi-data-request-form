"""
storage.py — Google Sheets persistence for submissions (via a service account).

Reads credentials + the target sheet id from Streamlit secrets:
    [sheets]
    id = "<google-sheet-id>"

    [gcp_service_account]
    ... service-account JSON fields ...

Uses open_by_key + the spreadsheets scope only, so only the Google Sheets API
needs enabling (no Drive scope / Drive API required).
"""

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def storage_configured():
    """True once both the sheet id and service-account creds are in secrets."""
    try:
        return bool(st.secrets["sheets"]["id"]) and bool(st.secrets["gcp_service_account"])
    except Exception:
        return False


@st.cache_resource
def _client():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _worksheet():
    sheet = _client().open_by_key(st.secrets["sheets"]["id"])
    return sheet.sheet1


def append_row(values):
    """Append one row to the first worksheet. Cells are parsed like typed input."""
    _worksheet().append_row(values, value_input_option="USER_ENTERED")


def service_account_email():
    """The service-account address the Sheet must be shared with (for hints)."""
    try:
        return st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        return None
