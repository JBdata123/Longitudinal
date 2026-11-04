"""
Pulls GPS Dummy Data.xlsx and firstbeat_data.xlsx straight out of Dropbox.
Auth: put your Dropbox credentials in .streamlit/secrets.toml (see
.streamlit/secrets.toml.example). A short-lived "access token" from the
Dropbox App Console works for testing, but it expires every few hours -
for a production app that anyone can open via SharePoint, set up the
refresh-token flow (app_key + app_secret + refresh_token) instead, which
never expires. This module supports both.
"""
import io

import dropbox
import pandas as pd
import streamlit as st

CACHE_TTL_SECONDS = 60  # refresh every 1 minute


def _get_client():
    cfg = st.secrets["dropbox"]
    if "refresh_token" in cfg:
        dbx = dropbox.Dropbox(
            oauth2_refresh_token=cfg["refresh_token"],
            app_key=cfg["app_key"],
            app_secret=cfg["app_secret"],
        )
    else:
        dbx = dropbox.Dropbox(cfg["access_token"])

    # If the files live in a Dropbox Business "Team space" (rather than your
    # personal "My files"), API calls need to be pointed at that space's
    # namespace root, otherwise Dropbox looks in your personal folder and
    # the files "don't exist" even though you can see them on dropbox.com.
    if cfg.get("team_space", True):
        account = dbx.users_get_current_account()
        root_ns = account.root_info.root_namespace_id
        dbx = dbx.with_path_root(dropbox.common.PathRoot.namespace_id(root_ns))
    return dbx


def _download_excel(dbx, path: str) -> pd.DataFrame:
    _, res = dbx.files_download(path)
    return pd.read_excel(io.BytesIO(res.content))


def _fix_gps_dates(col: pd.Series) -> pd.Series:
    """Repairs the Date column of the GPS export.

    Dates typed as dd/mm/yyyy get half-converted by Excel: ones with a day
    above 12 (e.g. 31/10/2026) can't be read as month/day, so they stay as
    text, while ones with a day of 12 or below (e.g. 1/11/2026) get turned
    into real dates with day and month swapped (11 Jan instead of 1 Nov).

    - text values  -> parsed day-first
    - real dates   -> day and month swapped back, but ONLY when the column is
                      a mix of text and real dates (the sign of the problem);
                      a column that is entirely real dates is left alone."""
    is_text = col.apply(lambda v: isinstance(v, str))
    if not is_text.any():
        return pd.to_datetime(col)

    def fix(v):
        if isinstance(v, str):
            return pd.to_datetime(v.strip(), dayfirst=True, errors="coerce")
        if pd.isna(v):
            return pd.NaT
        ts = pd.Timestamp(v)
        if ts.day <= 12:
            return pd.Timestamp(year=ts.year, month=ts.day, day=ts.month)
        return ts.normalize()

    return pd.to_datetime(col.apply(fix))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Refreshing data from Dropbox...")
def load_data(_cache_buster: int = 0):
    """Returns (gps_day, firstbeat_day, gps_periods). Cached for
    CACHE_TTL_SECONDS, so the app auto-refreshes on its own every 60s -
    `_cache_buster` lets the manual Refresh button force an immediate reload
    regardless of the TTL.

    gps_periods = every 1st-half / 2nd-half / warm-up period row, used for
    the match-minute reference lines."""
    cfg = st.secrets["dropbox"]
    dbx = _get_client()
    gps = _download_excel(dbx, cfg["gps_path"])       # e.g. "/GPS Dummy Data.xlsx"
    fb = _download_excel(dbx, cfg["firstbeat_path"])  # e.g. "/firstbeat_data.xlsx"

    gps["Date"] = _fix_gps_dates(gps["Date"])
    fb["Date"] = pd.to_datetime(fb["Start date (dd.mm.yyyy)"], format="%d.%m.%Y")

    # Day-level rows only, as agreed: GPS Session row, Firstbeat Measurement row.
    # (Game days have extra Period Number==0 rows for 5-min sub-segments - exclude those.)
    gps_day = gps[(gps["Period Number"] == 0) & (gps["Period Name"] == "Session")].copy()
    fb_day = fb[fb["Analysis period"] == "Measurement"].copy()

    # Half-level rows (1st half / 2nd half) PLUS warm-up rows. The app tells
    # them apart by Period Name: halves build the per-minute match rate,
    # warm-up rows build the average warm-up load.
    period_name = gps["Period Name"].astype(str).str.lower()
    is_warm = period_name.str.contains(r"warm|wup", regex=True)
    is_half = period_name.str.contains(r"half|1st|2nd|first|second", regex=True) & ~is_warm
    gps_periods = gps[is_half | is_warm].copy()

    return gps_day, fb_day, gps_periods
