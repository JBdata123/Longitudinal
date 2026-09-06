"""
Squad Availability dashboard, requested by the physio team.

Shows, for a selected date: every player's availability status (from the
manually-maintained "Squad Availability 2026-27.xlsx" file in Dropbox) next
to their minutes played that day (computed from the same GPS data already
loaded elsewhere in this app), plus a squad-wide availability summary at
the bottom.

ASSUMPTIONS THAT MAY NEED ADJUSTING -- see the comments marked >>> below:
  1. gps_day (from your existing data_loader.load_data()) has raw columns
     called "Period Name" and "Total Duration", matching a standard
     Catapult export. If your data_loader renamed these, update the
     column names in `compute_minutes_played` below.
  2. A new Dropbox secret is needed for the availability file's path --
     see DROPBOX_AVAILABILITY_PATH below. Add this to secrets.toml.
  3. This assumes a multi-page Streamlit app (a "pages/" folder) -- if
     your app is actually single-page, move this code into your main
     script instead, calling it wherever you want the dashboard to show.
"""
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import dropbox
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from theme import NAVY, GOLD, WHITE, FONT, metric_title_bar
from data_loader import load_data, CACHE_TTL_SECONDS

st.set_page_config(page_title="Squad Availability", layout="wide")

# ---------------------------------------------------------------------------
# Reused, proven name-cleaning logic (same as the Supabase pipeline).
# Two independently-maintained spreadsheets (this one, and the GPS export)
# are exactly the kind of place a name mismatch silently breaks a join --
# an accented name typed slightly differently, extra whitespace, etc.
# ---------------------------------------------------------------------------
def normalize_name(name):
    """Strip whitespace, repair mojibake, and normalize Unicode so names
    from two different files reliably match each other."""
    text = str(name).strip()
    try:
        text = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFC", text)


# ---------------------------------------------------------------------------
# Global CSS -- matches the navy/gold styling already used elsewhere in
# this app.
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    div.block-container {{ padding-top: 0rem; }}
    h1, h2, h3 {{ text-align: center; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Download + cache the availability Excel file from Dropbox.
# >>> ADD "availability_path" TO YOUR secrets.toml, e.g.:
#     [dropbox]
#     availability_path = "/Club Data/Squad Availability 2026-27.xlsx"
# ---------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_availability(_cache_buster):
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=st.secrets["dropbox"]["refresh_token"],
        app_key=st.secrets["dropbox"]["app_key"],
        app_secret=st.secrets["dropbox"]["app_secret"],
    )
    # Same team-space handling as the main pipeline -- Business/Team Dropbox
    # accounts store files outside the connecting member's personal folder.
    try:
        account = dbx.users_get_current_account()
        root_info = getattr(account, "root_info", None)
        namespace_id = getattr(root_info, "root_namespace_id", None)
        if namespace_id:
            dbx = dbx.with_path_root(dropbox.common.PathRoot.root(namespace_id))
    except Exception:
        pass

    path = st.secrets["dropbox"]["availability_path"]
    _, resp = dbx.files_download(path)
    import io
    df = pd.read_excel(io.BytesIO(resp.content))

    df["Name"] = df["Name"].apply(normalize_name)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Compute minutes played per player, for one date, from the GPS data
# already loaded by the rest of this app -- no second Dropbox download.
#
# >>> If your gps_day dataframe uses different column names than the raw
# >>> Catapult export ("Period Name", "Total Duration"), update them here.
# ---------------------------------------------------------------------------
def parse_duration_to_minutes(duration_text):
    """Parses an HH:MM:SS string into minutes. Returns 0 for anything
    that isn't a clean HH:MM:SS string (blank, malformed, etc.) rather
    than crashing -- matching the defensive parsing pattern used
    throughout the Supabase pipeline for this exact kind of field."""
    text = str(duration_text).strip()
    if len(text) < 8:
        return 0
    try:
        hours = int(text[0:2])
        minutes = int(text[3:5])
        seconds = int(text[6:8])
        return hours * 60 + minutes + seconds / 60
    except (ValueError, IndexError):
        return 0


def compute_minutes_played(gps_day, selected_date):
    """Returns {normalized_player_name: minutes_played} for one date,
    summing 1st Half + 2nd Half duration -- matching the same convention
    used throughout the Supabase pipeline for match-day totals."""
    day_rows = gps_day[gps_day["Date"].dt.date == selected_date].copy()
    if day_rows.empty:
        return {}

    half_rows = day_rows[
        day_rows["Period Name"].astype(str).str.strip().str.lower().isin(
            ["1st half", "2nd half"]
        )
    ].copy()
    if half_rows.empty:
        return {}

    half_rows["_minutes"] = half_rows["Total Duration"].apply(parse_duration_to_minutes)
    half_rows["_player_norm"] = half_rows["Player Name"].apply(normalize_name)

    minutes_by_player = half_rows.groupby("_player_norm")["_minutes"].sum().to_dict()
    return minutes_by_player


# ---------------------------------------------------------------------------
# Availability badge styling
# ---------------------------------------------------------------------------
def availability_badge(status):
    status_clean = str(status).strip().lower()
    if status_clean == "yes":
        bg, text_color, label = "#C0DD97", "#173404", "Yes"
    elif status_clean == "injured":
        bg, text_color, label = "#F7C1C1", "#501313", "Injured"
    else:
        bg, text_color, label = "#E5E5E0", "#2C2C2A", status if status else "Unknown"
    return (
        f"<span style='background:{bg};color:{text_color};padding:3px 10px;"
        f"border-radius:10px;font-weight:700;font-size:12px'>{label}</span>"
    )


# ---------------------------------------------------------------------------
# Header + date picker
# ---------------------------------------------------------------------------
st_autorefresh(interval=CACHE_TTL_SECONDS * 1000, key="availability_auto_refresh")

st.markdown(
    f"<div style='background-color:{NAVY};border-bottom:5px solid {GOLD};"
    f"padding:18px 24px;text-align:center;overflow:visible;white-space:nowrap'>"
    f"<span style='color:{WHITE};font-size:32px;font-weight:800;letter-spacing:1px;"
    f"line-height:1.4;font-family:{FONT}'>SQUAD AVAILABILITY</span></div>",
    unsafe_allow_html=True,
)

if "cache_buster" not in st.session_state:
    st.session_state.cache_buster = 0

try:
    gps_day, _fb_day = load_data(st.session_state.cache_buster)
    availability_df = load_availability(st.session_state.cache_buster)
except Exception as e:
    st.error(f"Couldn't load data from Dropbox: {e}")
    st.info(
        "Check secrets.toml has a valid 'availability_path' entry under [dropbox], "
        "and that the Squad Availability file is in the expected location."
    )
    st.stop()

available_dates = sorted(availability_df["Date"].dropna().dt.date.unique())
if not available_dates:
    st.warning("No dates found in the Squad Availability file.")
    st.stop()

selected_date = st.selectbox(
    "Select date",
    available_dates,
    index=len(available_dates) - 1,
    format_func=lambda d: d.strftime("%d/%m/%Y"),
)

# ---------------------------------------------------------------------------
# Build the table for the selected date
# ---------------------------------------------------------------------------
day_availability = availability_df[
    availability_df["Date"].dt.date == selected_date
].copy()

minutes_lookup = compute_minutes_played(gps_day, selected_date)
day_availability["_name_norm"] = day_availability["Name"].apply(normalize_name)
day_availability["Minutes Played"] = day_availability["_name_norm"].map(minutes_lookup)

rows_html = ""
for _, row in day_availability.sort_values("Name").iterrows():
    status = row["Avaliability"] if "Avaliability" in row else row.get("Availability", "")
    minutes = row["Minutes Played"]
    minutes_display = "-" if pd.isna(minutes) else f"{minutes:.0f}"
    rows_html += (
        f"<tr style='border-top:1px solid #e5e5e0'>"
        f"<td style='padding:8px 12px;font-weight:600'>{row['Name']}</td>"
        f"<td style='padding:8px 12px;text-align:center'>{availability_badge(status)}</td>"
        f"<td style='padding:8px 12px;text-align:center;font-weight:700'>{minutes_display}</td>"
        f"</tr>"
    )

total_players = len(day_availability)
available_count = (
    day_availability.get("Avaliability", day_availability.get("Availability", pd.Series(dtype=str)))
    .astype(str).str.strip().str.lower().eq("yes").sum()
)
available_pct = (available_count / total_players * 100) if total_players > 0 else 0

table_html = f"""
<div style='font-family:{FONT};max-width:600px;margin:20px auto;border:2px solid {NAVY};border-radius:6px;overflow:hidden'>
<table style='width:100%;border-collapse:collapse'>
<tr style='background:{NAVY};color:{WHITE}'>
<th style='padding:10px 12px;text-align:left'>Name</th>
<th style='padding:10px 12px;text-align:center'>Availability</th>
<th style='padding:10px 12px;text-align:center'>Minutes Played</th>
</tr>
{rows_html}
</table>
<div style='background:{NAVY};color:{WHITE};text-align:center;padding:12px;font-weight:700;font-size:15px;border-top:3px solid {GOLD}'>
Squad Availability: {available_count} / {total_players} ({available_pct:.0f}%)
</div>
</div>
"""

st.markdown(table_html, unsafe_allow_html=True)
