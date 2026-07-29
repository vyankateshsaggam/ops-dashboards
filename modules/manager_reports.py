"""
manager_reports.py
-------------------
Lets an Admin swap the dashboard's ACTIVE DATASET to one of several
managers' Google Sheets, pulled live — no download/upload step needed.

This intentionally does NOT run its own separate charts/KPIs. Instead it
fetches the manager's sheet and hands it to
DataLoader.save_dataframe_as_source(), which is the exact same mechanism
save_uploaded_file() uses for an Excel upload. That means: once a manager's
report is loaded, ALL 14 dashboard tabs (Executive, Daily Performance, ...
Reports/Data) recompute from that manager's data automatically — identical
behaviour to uploading a new Excel file, just sourced from Google Sheets.

Adding a new manager requires ZERO code changes — just add an entry to
config.json -> "manager_reports" (see README.md).
"""
import re
import io
import requests
import pandas as pd
import streamlit as st

_SHEET_ID_RE = re.compile(r"/d/([a-zA-Z0-9-_]+)")
_GID_RE = re.compile(r"[?&#]gid=(\d+)")


def parse_sheet_url(url: str):
    """Extract (sheet_id, gid) from any Google Sheets share/edit URL."""
    m = _SHEET_ID_RE.search(url)
    if not m:
        raise ValueError(
            f"That doesn't look like a Google Sheets link (no '/d/<id>/' found): {url}"
        )
    sheet_id = m.group(1)
    g = _GID_RE.search(url)
    gid = g.group(1) if g else "0"
    return sheet_id, gid


def csv_export_url(sheet_id: str, gid: str = "0") -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_manager_sheet(sheet_url: str) -> pd.DataFrame:
    """Fetch one manager's sheet as a raw DataFrame (headers stripped, but
    NOT yet column-resolved — that happens later via the normal
    load_raw() -> resolve_columns() pipeline once this is saved as the
    active source file, keeping column-matching logic in one place)."""
    sheet_id, gid = parse_sheet_url(sheet_url)
    export_url = csv_export_url(sheet_id, gid)
    try:
        # Fetch as text first so we can detect Google's HTML "you need
        # permission" page — a non-public sheet doesn't always raise a
        # parser error, it can silently parse into a garbage 1-column
        # DataFrame, which then fails later with a confusing "missing
        # required column" message instead of the real cause.
        resp = requests.get(export_url, timeout=20)
        resp.raise_for_status()
        text = resp.text
        if "<html" in text[:500].lower() or "accounts.google.com" in text[:2000].lower():
            raise RuntimeError(
                "Google returned a login/permission page instead of the sheet's data. "
                "This sheet is NOT shared publicly yet — open it, click Share, and set "
                "General access to 'Anyone with the link' -> Viewer, then try again."
            )
        raw = pd.read_csv(io.StringIO(text))
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            "Could not fetch this sheet. Make sure its sharing is set to "
            "'Anyone with the link -> Viewer' (Share button -> General access), "
            f"then try again. Original error: {e}"
        )
    raw.columns = [str(c).strip() for c in raw.columns]
    if raw.empty or len(raw.columns) < 3:
        raise RuntimeError(
            "This sheet returned no usable data (fewer than 3 columns). Double-check "
            "the link points to the correct tab and that sharing is set to "
            "'Anyone with the link -> Viewer'."
        )
    return raw


def test_manager_connection(sheet_url: str) -> dict:
    """Used by the Admin Panel's connection tester: tries a full fetch and
    returns a small result dict instead of raising, so many managers can
    be checked in one pass and shown as a status table."""
    try:
        raw = fetch_manager_sheet(sheet_url)
        return {"ok": True, "rows": len(raw), "cols": len(raw.columns), "error": None}
    except Exception as e:
        return {"ok": False, "rows": 0, "cols": 0, "error": str(e)}
