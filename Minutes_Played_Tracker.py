"""
Minutes Played Tracker -- longitudinal season view.

Pulls match data directly from Supabase (not Dropbox) -- match-day period
parsing, opponent info, and scores all already live correctly there from
the main pipeline, so this page reuses that rather than re-deriving any
of it from scratch.

Requires SUPABASE_DB_URL in .streamlit/secrets.toml -- the same URL your
GitHub Actions sync already uses.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
import streamlit as st

from theme import NAVY, GOLD, WHITE, FONT
from data_loader import CACHE_TTL_SECONDS

st.set_page_config(page_title="Minutes Played Tracker", layout="wide")

# ---------------------------------------------------------------- global CSS
# Same navy/gold header bar convention as the main Longitudinal Report page
st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    div.block-container {{ padding-top: 0rem; }}
    .st-key-header_bar {{
        background-color: {NAVY} !important;
        border: none !important;
        border-bottom: 5px solid {GOLD} !important;
        border-radius: 0 !important;
        padding: 10px 24px 20px 24px !important;
        box-shadow: none !important;
    }}
    .st-key-header_bar, .st-key-header_bar * {{
        color: {WHITE} !important;
    }}
    .st-key-header_bar .stButton > button {{
        background-color: {NAVY} !important;
        color: {WHITE} !important;
        border: 1px solid {WHITE} !important;
    }}
    .st-key-header_bar .stButton > button:hover,
    .st-key-header_bar .stButton > button:active,
    .st-key-header_bar .stButton > button:focus,
    .st-key-header_bar .stButton > button:focus:not(:active) {{
        background-color: {NAVY} !important;
        color: {WHITE} !important;
        border: 1px solid {WHITE} !important;
        box-shadow: none !important;
    }}
    .st-key-refresh_box {{
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        background: transparent !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        width: fit-content !important;
        margin-left: auto !important;
        margin-right: 0 !important;
    }}
    .st-key-refresh_box .stButton {{
        width: fit-content !important;
    }}
    h1 {{ text-align: center; }}
    /* Table styling to match the navy/gold theme */
    .stDataFrame {{ border: 1px solid {NAVY}22; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data loading
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading match data...")
def load_match_minutes(_cache_buster: int = 0) -> pd.DataFrame:
    """One row per (player, match date), with minutes played and match
    context. Pulls straight from master_data, so it automatically stays in
    sync with the same match-day parsing the rest of the project relies on.

    Filtered to genuine match days only (gps_day is EXACTLY 'MD' -- not
    'MD-1'/'MD-2', which are training days that happen to share the same
    prefix) and to 05/09/2026 onward."""
    conn = psycopg2.connect(st.secrets["supabase"]["db_url"])
    try:
        query = """
            select
                "player",
                session_date,
                match_opposition,
                match_location,
                match_competition,
                gps_total_duration
            from master_data
            where drill_label in ('1ST HALF', '2ND HALF')
              and position <> 'Goalkeeper'
              and session_date is not null
              and upper(trim(gps_day)) = 'MD'
              and session_date >= '2026-09-05'
        """
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    def parse_duration_to_minutes(duration_text):
        if pd.isna(duration_text):
            return 0.0
        text = str(duration_text).strip()
        if len(text) < 8:
            return 0.0
        try:
            h, m, s = text[0:2], text[3:5], text[6:8]
            return int(h) * 60 + int(m) + int(s) / 60
        except (ValueError, IndexError):
            return 0.0

    df["minutes"] = df["gps_total_duration"].apply(parse_duration_to_minutes)

    grouped = (
        df.groupby(["session_date", "player", "match_opposition", "match_location", "match_competition"], dropna=False)
        ["minutes"].sum()
        .reset_index()
    )
    return grouped


if "cache_buster" not in st.session_state:
    st.session_state.cache_buster = 0

try:
    data = load_match_minutes(st.session_state.cache_buster)
except Exception as e:
    st.error(f"Couldn't load data from Supabase: {e}")
    st.info("Check .streamlit/secrets.toml has a valid [supabase] db_url entry.")
    st.stop()


# ---------------------------------------------------------------- header bar
with st.container(key="header_bar", border=True):
    header_col, refresh_col = st.columns([5, 1.6])
    with header_col:
        st.markdown(
            "<div style='font-size:40px; font-weight:800; letter-spacing:1px; "
            "text-align:center; padding:4px 0 10px 0;'>MINUTES PLAYED TRACKER</div>",
            unsafe_allow_html=True,
        )
    with refresh_col:
        with st.container(key="refresh_box", border=True):
            if st.button("🔄 Refresh data now"):
                st.session_state.cache_buster += 1
                load_match_minutes.clear()
                st.rerun()
            st.markdown(
                f"<div style='font-size:10.5px; opacity:0.85; margin-top:4px; "
                f"margin-bottom:2px; white-space:nowrap; text-align:center;'>"
                f"last loaded {datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK</div>",
                unsafe_allow_html=True,
            )

if data.empty:
    st.warning("No MD match data found for 05/09/2026 onward yet.")
    st.stop()

# ---------------------------------------------------------------- build the longitudinal table
def format_match_label(row):
    opposition = row["match_opposition"] if pd.notna(row["match_opposition"]) else "Unknown"
    loc_letter = str(row["match_location"])[:1].upper() if pd.notna(row["match_location"]) else "?"
    competition = row["match_competition"] if pd.notna(row["match_competition"]) else "?"
    return f"{opposition} - {loc_letter} - {competition}"

data["match_label"] = data.apply(format_match_label, axis=1)

matches_sorted = (
    data[["session_date", "match_label"]]
    .drop_duplicates()
    .sort_values("session_date")
)
column_order = matches_sorted["match_label"].tolist()

pivot = data.pivot_table(
    index="player", columns="match_label", values="minutes", aggfunc="sum"
)
pivot = pivot.reindex(columns=column_order)
pivot = pivot.sort_index()

st.dataframe(
    pivot.style.format(precision=0, na_rep="-"),
    width="stretch",
    height=min(800, 46 * (len(pivot) + 1)),
)
