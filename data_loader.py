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
    """Reads the GPS Date column, which is a MIX of two things:
    - real Excel dates (these are already correct, Excel just displays them
      US-style as m/d/yyyy, e.g. 11/1/2026 is 1 November), and
    - text dates typed as dd/mm/yyyy (e.g. "17/10/2026"), which Excel could not
      read as a date because the day is above 12.

    Real dates are kept exactly as they are. Text dates are read day-first."""
    def fix(v):
        if isinstance(v, str):
            return pd.to_datetime(v.strip(), dayfirst=True, errors="coerce")
        if pd.isna(v):
            return pd.NaT
        return pd.Timestamp(v).normalize()

    return pd.to_datetime(col.apply(fix))


# ---- combining several sessions on the same day into one daily row ----
_MAX_COLS = ["Maximum Velocity", "Max Vel (% Max)", "Profile Max Velocity", "Max Acceleration"]
_MIN_COLS = ["Max Deceleration"]  # decelerations are negative, so the biggest one is the minimum
_MEAN_COLS = ["Running Imbalance", "Average Time To Feet", "Average Time to Feet Left",
              "Average Time to Feet Centre", "Average Time to Feet Right"]
_KEEP_FIRST = ["Week Number", "Period Number"]


def _minutes(series: pd.Series) -> pd.Series:
    """Total Duration (hh:mm:ss text/time, or plain numbers) -> minutes."""
    def one(t):
        if pd.isna(t):
            return 0.0
        if isinstance(t, pd.Timedelta):
            return t.total_seconds() / 60
        if hasattr(t, "hour"):
            return t.hour * 60 + t.minute + t.second / 60
        if isinstance(t, (int, float)):
            return float(t)
        s = str(t).strip()
        if "days" in s:
            s = s.split()[-1]
        try:
            h, m, sec = [float(p) for p in s.split(":")]
            return h * 60 + m + sec / 60
        except Exception:
            return 0.0
    mins = series.apply(one)
    positive = mins[mins > 0]
    if len(positive) and positive.median() > 200:   # numbers were seconds
        mins = mins / 60
    return mins


def _collapse_duplicate_days(df: pd.DataFrame) -> pd.DataFrame:
    """Gives exactly one row per player per date. If a player has two or more
    'Session' rows on the same day, they are combined: totals (distance, HSR,
    efforts, jumps, dives...) are added, top speeds/peaks take the highest,
    and metres per minute is recalculated from the combined distance and time."""
    key = ["Player Name", "Date"]
    if not df.duplicated(key).any():
        return df

    num_cols = set(df.select_dtypes("number").columns)
    agg = {}
    for c in df.columns:
        if c in key:
            continue
        if c in _KEEP_FIRST:
            agg[c] = "first"
        elif c in _MAX_COLS:
            agg[c] = "max"
        elif c in _MIN_COLS:
            agg[c] = "min"
        elif c in _MEAN_COLS:
            agg[c] = "mean"
        elif c in num_cols and c != "Meterage Per Minute":
            agg[c] = lambda s: s.sum(min_count=1)
        else:
            agg[c] = "first"

    out = df.groupby(key, as_index=False, sort=False).agg(agg)

    if "Meterage Per Minute" in df.columns and "Total Duration" in df.columns:
        mins = _minutes(df["Total Duration"]).groupby([df[k] for k in key], sort=False).sum()
        out = out.set_index(key)
        mins = mins.reindex(out.index)
        out["Meterage Per Minute"] = (out["Total Distance"] / mins).where(mins > 0, out["Meterage Per Minute"])
        out = out.reset_index()
    return out[list(df.columns)]


# ---- player status (fit / injured / ...) from its own Excel file in Dropbox ----
STATUS_FIT_VALUES = {"fit"}   # player_status values that count as fit (compared in lower case)


def _pick_col(columns, keywords, exclude=()):
    """First column whose name contains one of the keywords (case-insensitive,
    underscores treated as spaces)."""
    for c in columns:
        if c in exclude:
            continue
        low = str(c).strip().lower().replace("_", " ")
        if any(k in low for k in keywords):
            return c
    return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_player_status(_cache_buster: int = 0):
    """Reads the player_status workbook. Returns (status_df, message).
    status_df has columns: name_key (lower-case, single-spaced name), Date, Fit (bool).
    If the file can't be read or understood, status_df is empty and message
    says why, so the dashboard can carry on without the filter."""
    try:
        cfg = st.secrets["dropbox"]
        path = cfg.get("player_status_path", "/player_status.xlsx")
        raw = _download_excel(_get_client(), path)
    except Exception as e:
        return pd.DataFrame(), f"Couldn't read the player status file ({e}). Check player_status_path in the Dropbox secrets."

    date_col = _pick_col(raw.columns, ["date"])
    status_col = _pick_col(raw.columns, ["status"], exclude=[date_col])
    name_col = _pick_col(raw.columns, ["player name", "player", "athlete", "name"], exclude=[status_col, date_col])
    if status_col is None or date_col is None or name_col is None:
        return pd.DataFrame(), (
            "The player status file needs a player, a date and a status column. "
            f"Columns found: {', '.join(str(c) for c in raw.columns)}."
        )

    df = pd.DataFrame({
        "name_key": raw[name_col].astype(str).str.lower().str.split().str.join(" "),
        "Date": _fix_gps_dates(raw[date_col]),
        "Fit": raw[status_col].astype(str).str.strip().str.lower().isin(STATUS_FIT_VALUES),
    }).dropna(subset=["Date"])
    # if a player has two rows for one date, the day only counts as fit if all of them say fit
    df = df.groupby(["name_key", "Date"], as_index=False)["Fit"].all()
    return df, ""


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
    gps_day = _collapse_duplicate_days(gps_day)
    fb_day = fb[fb["Analysis period"] == "Measurement"].copy()

    # Half-level rows (1st half / 2nd half) PLUS warm-up rows. The app tells
    # them apart by Period Name: halves build the per-minute match rate,
    # warm-up rows build the average warm-up load.
    period_name = gps["Period Name"].astype(str).str.lower()
    is_warm = period_name.str.contains(r"warm|wup", regex=True)
    # Only the main half rows ("1ST HALF" / "2ND HALF"). The export also has
    # 5-minute / 23-minute slices like "1ST HALF 00_00 - 05_00" (Period Number 0)
    # which overlap the halves, so they are left out to avoid double counting.
    is_half = period_name.str.strip().str.match(r"^(1st|2nd|first|second)\s*half$")
    gps_periods = gps[is_half | is_warm].copy()

    return gps_day, fb_day, gps_periods
