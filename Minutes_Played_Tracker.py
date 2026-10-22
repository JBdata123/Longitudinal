"""
Minutes Tracker -- one hub for minutes: games and training.

Two views, switched with the buttons at the top:

  * Match minutes     -- minutes played in each game (colour-coded), as before.
  * Training minutes  -- minutes trained so far this season: every training session,
                         i.e. every day that is NOT a match day (MD). One column per GPS
                         week, plus a Total and the number of days trained. No colours.

Pulls everything directly from Supabase (not Dropbox) -- match-day period
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

st.set_page_config(page_title="Minutes Tracker", layout="wide")

# ---------------------------------------------------------------- global CSS
st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    
    /* Table styling to match the navy/gold theme */
    .stDataFrame {{ border: 1px solid {NAVY}22; }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data loading
def parse_duration_to_minutes(duration_text):
    """HH:MM:SS text -> minutes. Anything unusable counts as 0."""
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


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading match data...")
def load_match_minutes(_cache_buster: int = 0) -> pd.DataFrame:
    """One row per (player, match date), with minutes played and match
    context. Pulls straight from master_data, so it automatically stays in
    sync with the same match-day parsing the rest of the project relies on.

    Filtered to genuine match/game days only (gps_day is EXACTLY 'MD' or contains 'GAME',
    excluding lead-up days like 'MD-1'/'MD-2')."""
    conn = psycopg2.connect(st.secrets["supabase"]["db_url"])
    try:
        query = """
            select
                "player",
                session_date,
                gps_week_number,
                match_opposition,
                match_location,
                match_competition,
                gps_total_duration
            from master_data
            where upper(trim(drill_label)) in ('1ST HALF', '2ND HALF', 'FIRST HALF', 'SECOND HALF')
              and position <> 'Goalkeeper'
              and session_date is not null
              and (
                  upper(trim(gps_day)) = 'MD' 
                  or upper(gps_day) like '%GAME%'
              )
        """
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    df["minutes"] = df["gps_total_duration"].apply(parse_duration_to_minutes)
    df["session_date"] = pd.to_datetime(df["session_date"])

    grouped = (
        df.groupby(
            ["session_date", "gps_week_number", "player", "match_opposition", "match_location", "match_competition"], 
            dropna=False
        )["minutes"]
        .sum()
        .reset_index()
    )
    return grouped


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading training data...")
def load_training_minutes(_cache_buster: int = 0) -> pd.DataFrame:
    """One row per (player, training session): the player's whole time on the
    pitch for that session (the SESSION row), on every day that is NOT a match
    day. 'Not a match day' is the exact opposite of the match rule above, so
    every day belongs to one view or the other, never both. Same players as the
    match view (no goalkeepers). Sessions with no usable duration are left out."""
    conn = psycopg2.connect(st.secrets["supabase"]["db_url"])
    try:
        query = """
            select
                "player",
                session_date,
                gps_week_number,
                gps_total_duration
            from master_data
            where upper(trim(drill_label)) = 'SESSION'
              and position <> 'Goalkeeper'
              and session_date is not null
              and gps_total_duration is not null
              and not coalesce(
                  upper(trim(gps_day)) = 'MD'
                  or upper(gps_day) like '%GAME%', false)
        """
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    df["minutes"] = df["gps_total_duration"].apply(parse_duration_to_minutes)
    df = df[df["minutes"] > 0].copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    return df.drop(columns="gps_total_duration").reset_index(drop=True)


if "cache_buster" not in st.session_state:
    st.session_state.cache_buster = 0


# ---------------------------------------------------------------- header bar
st.markdown(
    f"""
    <div style="
        background-color: {NAVY};
        border-bottom: 5px solid {GOLD};
        padding: 16px 24px;
        margin-bottom: 20px;
        color: {WHITE};
        display: flex;
        align-items: center;
        justify-content: space-between;
    ">
        <div style="font-size: 28px; font-weight: 800; letter-spacing: 1px; color: {WHITE};">
            MINUTES TRACKER
        </div>
        <div style="font-size: 11px; opacity: 0.85; text-align: right; color: {WHITE}; white-space: nowrap;">
            last loaded {datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

btn_col, mode_col = st.columns([2, 5])
with btn_col:
    if st.button("🔄 Refresh data now"):
        st.session_state.cache_buster += 1
        load_match_minutes.clear()
        load_training_minutes.clear()
        st.rerun()
with mode_col:
    view = st.radio(
        "View", ["Match minutes", "Training minutes"], horizontal=True,
        label_visibility="collapsed", key="minutes_view",
    )


# ---------------------------------------------------------------- training view
def show_training_minutes():
    try:
        data = load_training_minutes(st.session_state.cache_buster)
    except Exception as e:
        st.error(f"Couldn't load data from Supabase: {e}")
        st.info("Check .streamlit/secrets.toml has a valid [supabase] db_url entry.")
        st.stop()

    if data.empty:
        st.warning("No training sessions found.")
        st.stop()

    # Week filter (same idea as the match view)
    available_weeks = sorted(w for w in data["gps_week_number"].dropna().unique())
    selected_weeks = st.multiselect(
        "Filter by GPS Week Number",
        options=["All"] + list(available_weeks),
        default=["All"],
        help="Select specific week numbers or leave 'All' selected.",
        key="training_weeks",
    )
    if "All" in selected_weeks or not selected_weeks:
        filtered = data.copy()
    else:
        filtered = data[data["gps_week_number"].isin(selected_weeks)].copy()

    if filtered.empty:
        st.info("No training sessions match the selected filter criteria.")
        st.stop()

    def week_label(week):
        return "No week" if pd.isna(week) else f"Wk {int(week)}"

    # Columns run in the order the weeks actually happened (by their first session
    # date), so pre-season weeks come first whatever way they are numbered.
    first_session = filtered.groupby("gps_week_number", dropna=False)["session_date"].min().sort_values()
    week_columns = []
    for week in first_session.index:
        label = week_label(week)
        if label not in week_columns:
            week_columns.append(label)
    filtered["week_label"] = filtered["gps_week_number"].map(week_label)

    pivot = filtered.pivot_table(index="player", columns="week_label", values="minutes", aggfunc="sum")
    pivot = pivot.reindex(columns=week_columns)
    pivot["Total"] = pivot.sum(axis=1)
    pivot["Days trained"] = filtered.groupby("player")["session_date"].nunique()
    pivot = pivot.sort_index()

    # No colour banding on training minutes -- just the numbers.
    st.dataframe(
        pivot.style.format(precision=0, na_rep="-"),
        width="stretch",
        height=min(800, 46 * (len(pivot) + 1)),
    )
    first_day = filtered["session_date"].min().strftime("%d/%m/%Y")
    last_day = filtered["session_date"].max().strftime("%d/%m/%Y")
    st.caption(
        f"Training minutes from {first_day} to {last_day}: each player's whole time on the pitch in every session "
        f"that isn't a match day (MD). Days trained counts the days with any training. Goalkeepers aren't included."
    )


if view == "Training minutes":
    show_training_minutes()
    st.stop()


# ================================================================ match view (unchanged)
try:
    data = load_match_minutes(st.session_state.cache_buster)
except Exception as e:
    st.error(f"Couldn't load data from Supabase: {e}")
    st.info("Check .streamlit/secrets.toml has a valid [supabase] db_url entry.")
    st.stop()

if data.empty:
    st.warning("No MD/Game match data found.")
    st.stop()

# ---------------------------------------------------------------- match label format
def format_match_label(row):
    opposition = row["match_opposition"] if pd.notna(row["match_opposition"]) else "Unknown"
    loc_letter = str(row["match_location"])[:1].upper() if pd.notna(row["match_location"]) else "?"
    competition = row["match_competition"] if pd.notna(row["match_competition"]) else "?"
    date_str = row["session_date"].strftime("%d/%m/%Y") if pd.notna(row["session_date"]) else "??"
    return f"{opposition} - {loc_letter} - {competition} - {date_str}"

data["match_label"] = data.apply(format_match_label, axis=1)

# ---------------------------------------------------------------- filters
filter_col1, filter_col2 = st.columns(2)

# 1. GPS Week Number Filter
available_weeks = sorted([w for w in data["gps_week_number"].dropna().unique()])
week_options = ["All"] + list(available_weeks)

with filter_col1:
    selected_weeks = st.multiselect(
        "Filter by GPS Week Number",
        options=week_options,
        default=["All"],
        help="Select specific week numbers or leave 'All' selected.",
        key="match_weeks",
    )

if "All" in selected_weeks or not selected_weeks:
    filtered_data = data.copy()
else:
    filtered_data = data[data["gps_week_number"].isin(selected_weeks)].copy()

# 2. Match Specific Filter
available_matches = (
    filtered_data[["session_date", "match_label"]]
    .drop_duplicates()
    .sort_values("session_date")["match_label"]
    .tolist()
)
match_options = ["All"] + available_matches

with filter_col2:
    selected_matches = st.multiselect(
        "Filter by Match",
        options=match_options,
        default=["All"],
        help="Select specific matches to display.",
        key="match_matches",
    )

if "All" not in selected_matches and selected_matches:
    filtered_data = filtered_data[filtered_data["match_label"].isin(selected_matches)]

# ---------------------------------------------------------------- build the longitudinal table
if filtered_data.empty:
    st.info("No matches match the selected filter criteria.")
    st.stop()

matches_sorted = (
    filtered_data[["session_date", "match_label"]]
    .drop_duplicates()
    .sort_values("session_date")
)
match_columns = matches_sorted["match_label"].tolist()

pivot = filtered_data.pivot_table(
    index="player", columns="match_label", values="minutes", aggfunc="sum"
)

# Calculate total minutes across selected matches for each player
pivot["Total"] = pivot.sum(axis=1)

# Reindex to keep match columns in chronological order and append 'Total' at the end
column_order = match_columns + ["Total"]
pivot = pivot.reindex(columns=column_order)
pivot = pivot.sort_index()

# Colour bands (minutes). Edit these two numbers to change the cut-offs.
GREEN_FROM = 75    # 75 or more        -> green
YELLOW_FROM = 45   # 45 up to 74       -> yellow   (anything lower -> red)

def color_minutes(val):
    """Colour is decided from the SAME rounded number the table displays,
    so what you read is always what was coloured. (Previously the unrounded
    value was used and the rules had a gap between 74 and 75, so a cell
    showing 75 could be red.) Every value now falls into exactly one band."""
    if pd.isna(val):
        return ""
    shown = int(f"{val:.0f}")   # identical rounding to the displayed value
    if shown >= GREEN_FROM:
        return "background-color: #2e7d32; color: #ffffff; font-weight: bold;"
    elif shown >= YELLOW_FROM:
        return "background-color: #fdbe11; color: #0a192f; font-weight: bold;"
    else:
        return "background-color: #d32f2f; color: #ffffff; font-weight: bold;"

# Apply styling to match columns only (excluding Total)
styled_pivot = (
    pivot.style
    .map(color_minutes, subset=match_columns)
    .format(precision=0, na_rep="-")
)

st.dataframe(
    styled_pivot,
    width="stretch",
    height=min(800, 46 * (len(pivot) + 1)),
)
