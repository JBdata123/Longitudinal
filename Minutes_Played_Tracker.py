"""
Minutes Played Tracker.

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
import plotly.graph_objects as go
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
    .st-key-header_bar div[data-testid="stHorizontalBlock"] {{
        align-items: center !important;
    }}
    .st-key-header_bar, .st-key-header_bar * {{
        color: {WHITE} !important;
    }}
    .st-key-header_bar label, .st-key-header_bar p {{
        color: {WHITE} !important;
        font-family: {FONT};
    }}
    .st-key-header_bar [data-testid="stWidgetLabel"] {{
        display: flex;
        justify-content: center;
        width: 100%;
    }}
    .st-key-header_bar.st-key-header_bar.st-key-header_bar div[data-testid="stSelectbox"] * {{
        background-color: {NAVY} !important;
        color: {WHITE} !important;
        -webkit-text-fill-color: {WHITE} !important;
        border-color: {WHITE} !important;
        fill: {WHITE} !important;
    }}
    .st-key-header_bar.st-key-header_bar.st-key-header_bar div[data-testid="stSelectbox"] svg {{
        display: none !important;
    }}
    div[data-baseweb="popover"] ul[role="listbox"] {{
        background-color: {NAVY} !important;
    }}
    div[data-baseweb="popover"] li {{
        background-color: {NAVY} !important;
        color: {WHITE} !important;
    }}
    div[data-baseweb="popover"] li:hover {{
        background-color: {GOLD} !important;
        color: {NAVY} !important;
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
    .st-key-header_bar div[data-testid="stHorizontalBlock"] > div:last-child {{
        display: flex !important;
        justify-content: flex-end !important;
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
    h1, h2, h3 {{ text-align: center; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data loading
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading match data...")
def load_match_minutes(_cache_buster: int = 0) -> pd.DataFrame:
    """One row per (player, match date), with minutes played and match
    context. Pulls straight from master_data, so it automatically stays in
    sync with the same match-day parsing the rest of the project relies on."""
    conn = psycopg2.connect(st.secrets["supabase"]["db_url"])
    try:
        query = """
            select
                "player",
                session_date,
                match_opposition,
                match_location,
                match_score,
                gps_total_duration
            from master_data
            where drill_label in ('1ST HALF', '2ND HALF')
              and position <> 'Goalkeeper'
              and session_date is not null
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
        df.groupby(["session_date", "player", "match_opposition", "match_location", "match_score"], dropna=False)
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

if data.empty:
    st.warning("No match data found yet.")
    st.stop()

games = (
    data[["session_date", "match_opposition", "match_location", "match_score"]]
    .drop_duplicates()
    .sort_values("session_date", ascending=False)
)

def format_game_label(row):
    date_str = pd.to_datetime(row["session_date"]).strftime("%d/%m/%Y")
    opposition = row["match_opposition"] if pd.notna(row["match_opposition"]) else "Unknown opposition"
    loc_letter = str(row["match_location"])[:1].upper() if pd.notna(row["match_location"]) else "?"
    score = f" - {row['match_score']}" if pd.notna(row["match_score"]) else ""
    return f"vs {opposition} ({loc_letter}){score} - {date_str}"

games["label"] = games.apply(format_game_label, axis=1)
game_labels = games["label"].tolist()


# ---------------------------------------------------------------- header bar
with st.container(key="header_bar", border=True):
    st.markdown(
        "<div style='font-size:40px; font-weight:800; letter-spacing:1px; "
        "text-align:center; padding:4px 0 10px 0;'>MINUTES PLAYED TRACKER</div>",
        unsafe_allow_html=True,
    )
    selector_col, refresh_col = st.columns([4.8, 1.6])
    with selector_col:
        selected_label = st.selectbox("Select a game", game_labels)
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

selected_date = games.loc[games["label"] == selected_label, "session_date"].iloc[0]

# ---------------------------------------------------------------- filter + chart
game_data = (
    data[data["session_date"] == selected_date]
    .sort_values("minutes", ascending=True)  # ascending so the longest bar plots at the top
)

fig = go.Figure()
fig.add_bar(
    x=game_data["minutes"],
    y=game_data["player"],
    orientation="h",
    marker_color=GOLD,
    text=[f"{m:.0f}" for m in game_data["minutes"]],
    textposition="outside",
    textfont=dict(color=NAVY, size=13, family=FONT),
    hoverinfo="skip",
)
fig.update_layout(
    height=max(400, len(game_data) * 32),
    plot_bgcolor=WHITE,
    paper_bgcolor=WHITE,
    font=dict(family=FONT, color=NAVY),
    xaxis=dict(title="Minutes Played", range=[0, 100], gridcolor="#e5e5e0"),
    yaxis=dict(title=None),
    margin=dict(l=10, r=40, t=20, b=40),
)

st.plotly_chart(
    fig,
    width="stretch",
    config={"displayModeBar": False},
)