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

CACHE_TTL_SECONDS = 30  # matches the "refresh every 30 seconds" requirement


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


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Refreshing data from Dropbox...")
def load_data(_cache_buster: int = 0):
    """Returns (gps_df, firstbeat_df). Cached for CACHE_TTL_SECONDS, so the
    app auto-refreshes on its own every 30s - `_cache_buster` lets the
    manual Refresh button force an immediate reload regardless of the TTL."""
    cfg = st.secrets["dropbox"]
    dbx = _get_client()

    gps = _download_excel(dbx, cfg["gps_path"])       # e.g. "/GPS Dummy Data.xlsx"
    fb = _download_excel(dbx, cfg["firstbeat_path"])  # e.g. "/firstbeat_data.xlsx"

    gps["Date"] = pd.to_datetime(gps["Date"])
    fb["Date"] = pd.to_datetime(fb["Start date (dd.mm.yyyy)"], format="%d.%m.%Y")

    # Day-level rows only, as agreed: GPS Session row, Firstbeat Measurement row.
    # (Game days have extra Period Number==0 rows for 5-min sub-segments - exclude those.)
    gps_day = gps[(gps["Period Number"] == 0) & (gps["Period Name"] == "Session")].copy()
    fb_day = fb[fb["Analysis period"] == "Measurement"].copy()

    return gps_day, fb_day
