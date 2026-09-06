"""
Squad Availability dashboard, requested by the physio team.

Shows, for a selected date: every player's availability status (from the
manually-maintained "Squad Availability 2026-27.xlsx" file in Dropbox) next
to their minutes played that day (computed from the same GPS data already
loaded elsewhere in this app), plus a squad-wide availability summary at
the bottom.
"""
import io
import unicodedata
from datetime import datetime, date
from zoneinfo import ZoneInfo

import dropbox
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from theme import NAVY, GOLD, WHITE, FONT, metric_title_bar
from data_loader import load_data, CACHE_TTL_SECONDS

st.set_page_config(page_title="Squad Availability", layout="wide")

# ---------------------------------------------------------------------------
# SEASON MATCHES & LOG
# Add games/sessions here as the season goes on!
# Format: date(YYYY, MM, DD): {"location": "...", "score": "..."}
# ---------------------------------------------------------------------------
SEASON_MATCHES = {
    date(2026, 9, 6): {"location": "Away vs Sheffield United", "score": "2 - 1"},
}


# ---------------------------------------------------------------------------
# Reused name-cleaning logic
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
# Global CSS
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
# Download + cache the availability Excel file from Dropbox
# ---------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_availability(_cache_buster):
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=st.secrets["dropbox"]["refresh_token"],
        app_key=st.secrets["dropbox"]["app_key"],
        app_secret=st.secrets["dropbox"]["app_secret"],
    )
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
    df = pd.read_excel(io.BytesIO(resp.content))

    df["Name"] = df["Name"].apply(normalize_name)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Minutes Played Calculation
# ---------------------------------------------------------------------------
def parse_duration_to_minutes(duration_text):
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

    return half_rows.groupby("_player_norm")["_minutes"].sum().to_dict()


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

refresh_col1, refresh_col2, refresh_col3 = st.columns([3, 1, 3])
with refresh_col2:
    if st.button("🔄 Refresh data now", key="availability_refresh_button"):
        st.session_state.cache_buster += 1
        load_data.clear()
        load_availability.clear()
        st.rerun()
    st.markdown(
        f"<div style='font-size:10.5px;opacity:0.7;text-align:center;margin-top:2px'>"
        f"Auto-refreshes every {CACHE_TTL_SECONDS}s &middot; last loaded "
        f"{datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK</div>",
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


# ---------------------------------------------------------------------------
# LOOKUP MATCH METADATA FOR SELECTED DATE
# ---------------------------------------------------------------------------
match_info = SEASON_MATCHES.get(selected_date, {})
location = match_info.get("location", "")
match_score = match_info.get("score", "")

meta_html = ""
if location or match_score:
    meta_parts = []
    if location:
        meta_parts.append(f"📍 {location}")
    if match_score:
        meta_parts.append(f"⚽ Score: {match_score}")
    meta_text = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(meta_parts)
    meta_html = f"""
    <div style='background:{NAVY};color:{GOLD};text-align:center;padding:8px;font-size:14px;font-weight:700;border-bottom:1px solid rgba(255,255,255,0.2)'>
        {meta_text}
    </div>
    """

table_html = f"""
<div style='font-family:{FONT};max-width:600px;margin:20px auto;border:2px solid {NAVY};border-radius:6px;overflow:hidden'>
{meta_html}
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
