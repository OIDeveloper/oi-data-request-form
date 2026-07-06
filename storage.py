"""
storage.py — Google Sheets/Drive persistence (via a service account).

Per submission:
  1. create_request_workbook() — a NEW spreadsheet file per request, created
     inside the Shared Drive, named with the requester email + IST timestamp,
     laid out Field | Value like the campaign template.
  2. append_master() — one row (with a link to that file) in the separate
     "Submissions Log" master workbook; self-heals its header on row 1.

Secrets:
    [sheets]
    id = "<master Submissions Log spreadsheet id>"
    request_folder_id = "<Shared Drive id (or a folder in it)>"
    [gcp_service_account]
    ... service-account JSON fields ...

A service account has NO personal Drive quota, so per-request files must be
created inside a Shared Drive (request_folder_id) — never the SA's own Drive.
"""

import re

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
MASTER_TITLE = "Submissions Log"


def storage_configured():
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


def request_folder_id():
    try:
        return st.secrets["sheets"]["request_folder_id"]
    except Exception:
        return None


def append_master(header, row):
    """Append a row to the FIRST sheet of the master log file, guaranteeing
    `header` sits on row 1."""
    ws = _client().open_by_key(st.secrets["sheets"]["id"]).sheet1
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(header, value_input_option="RAW")
    elif existing[0] != header:
        ws.insert_row(header, index=1, value_input_option="RAW")
    ws.append_row(row, value_input_option="USER_ENTERED")


def read_all_requests():
    """All rows from the master-log first sheet as a list of dicts (header-keyed)."""
    ws = _client().open_by_key(st.secrets["sheets"]["id"]).sheet1
    return ws.get_all_records()


def _spreadsheet_id_from_url(url):
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def delete_requests(urls):
    """Delete each request's workbook file AND its master-log row.

    A master row is removed only if its file was deleted (or already gone), so a
    file is never orphaned. Deleting a file needs the service account to be
    'Content Manager' on the shared drive (Contributor can't delete).
    Returns (deleted_count, errors).
    """
    client = _client()
    ok, errors = [], []
    for url in urls:
        fid = _spreadsheet_id_from_url(url)
        if not fid:
            errors.append(f"Couldn't parse workbook id from: {url}")
            continue
        try:
            client.del_spreadsheet(fid)
            ok.append(url)
        except Exception as exc:
            msg = str(exc)
            if "404" in msg or "notfound" in msg.lower():
                ok.append(url)          # already gone — still clean up the row
            else:
                errors.append(f"{url}: {msg}")
    if ok:
        ws = client.open_by_key(st.secrets["sheets"]["id"]).sheet1
        values = ws.get_all_values()
        if values and "request_url" in values[0]:
            uc = values[0].index("request_url")
            rows = [i + 1 for i, row in enumerate(values)
                    if i >= 1 and len(row) > uc and row[uc] in ok]
            for r in sorted(rows, reverse=True):   # delete bottom-up
                ws.delete_rows(r)
    return len(ok), errors


def _safe_filename(name):
    name = re.sub(r"[\r\n/\\]", " ", name or "").strip()
    return (name or "OI Data Request")[:120]


def create_request_workbook(title, pairs):
    """Create a new spreadsheet per request inside the Shared Drive, write the
    Field | Value content, and return (title, url)."""
    folder = request_folder_id()
    if not folder:
        raise RuntimeError(
            "sheets.request_folder_id is not set in secrets — needed because a "
            "service account cannot own files in its own Drive."
        )
    sh = _client().create(_safe_filename(title), folder_id=folder)
    ws = sh.sheet1
    ws.update_title("Request")
    ws.append_rows(
        [["Field", "Value"]] + [[k, str(v)] for k, v in pairs],
        value_input_option="USER_ENTERED",
    )
    return sh.title, sh.url


def service_account_email():
    try:
        return st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        return None
