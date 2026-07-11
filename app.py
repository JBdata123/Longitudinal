import time
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from theme import NAVY, GOLD, WHITE, FONT, metric_title_bar, legend_row
from data_loader import load_data, CACHE_TTL_SECONDS
import charts

st.set_page_config(page_title="LCFC Longitudinal Report", layout="wide", page_icon="🦊")

# ---------------------------------------------------------------- global CSS
st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    div.block-container {{ padding-top: 0rem; }}

    /* ---- header bar (navy, gold underline) ---- */
    .st-key-header_bar {{
        background-color: {NAVY} !important;
        border: none !important;
        border-bottom: 5px solid {GOLD} !important;
        border-radius: 0 !important;
        padding: 10px 24px 20px 24px !important;
        box-shadow: none !important;
    }}
    /* vertically align the dropdown / slider / refresh button on one row,
       regardless of each widget's own natural height */
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
    /* centre every widget label in the header (e.g. "Date range") */
    .st-key-header_bar [data-testid="stWidgetLabel"] {{
        display: flex;
        justify-content: center;
        width: 100%;
    }}

    /* Blue background, white text, everywhere inside the selectbox -
       maximum specificity via repeated class chaining, pure universal
       selector, no exceptions of any kind. */
    .st-key-header_bar.st-key-header_bar.st-key-header_bar div[data-testid="stSelectbox"] * {{
        background-color: {NAVY} !important;
        color: {WHITE} !important;
        -webkit-text-fill-color: {WHITE} !important;
        border-color: {WHITE} !important;
        fill: {WHITE} !important;
    }}

    /* the dropdown popover/menu that appears when you click the selectbox */
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

    /* slider track/handles */
    .st-key-header_bar div[data-baseweb="slider"] div[role="slider"] {{
        background-color: {GOLD} !important;
    }}
    .st-key-header_bar div[data-testid="stTickBar"] {{ color: {WHITE} !important; }}

    /* refresh button - permanently navy in every state */
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

    /* right-align the refresh column's content block within its column */
    .st-key-header_bar div[data-testid="stHorizontalBlock"] > div:last-child {{
        display: flex !important;
        justify-content: flex-end !important;
    }}
    /* refresh_box: strip its visible border (only needed so Streamlit
       reliably attaches the st-key class to a real wrapper div), then
       shrink-wrap it and push it to the right edge, centring the button
       and caption relative to each other inside it */
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

# ---------------------------------------------------------------- password gate
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown(
        "<div style='text-align:center; margin-top:80px;'>"
        "<h2>🦊 LCFC Longitudinal Report</h2>"
        "<p>Enter the password to continue.</p></div>",
        unsafe_allow_html=True,
    )
    _, mid_col, _ = st.columns([1, 1.2, 1])
    with mid_col:
        entered = st.text_input("Password", type="password", label_visibility="collapsed",
                                 placeholder="Password")
        if st.button("Enter", width="stretch"):
            if entered == st.secrets.get("app_password", ""):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()

# ---------------------------------------------------------------- auto refresh every 60s
st_autorefresh(interval=CACHE_TTL_SECONDS * 1000, key="auto_refresh")

if "cache_buster" not in st.session_state:
    st.session_state.cache_buster = 0

# ---------------------------------------------------------------- load data
try:
    gps_day, fb_day = load_data(st.session_state.cache_buster)
except Exception as e:
    st.error(f"Couldn't load data from Dropbox: {e}")
    st.info("Check .streamlit/secrets.toml has valid Dropbox credentials and file paths.")
    st.stop()

players = sorted(gps_day["Player Name"].dropna().unique())
min_date = gps_day["Date"].min().date()
max_date = gps_day["Date"].max().date()

# ---------------------------------------------------------------- header bar
with st.container(key="header_bar", border=True):
    st.markdown(
        "<div style='font-size:40px; font-weight:800; letter-spacing:1px; "
        "text-align:center; padding:4px 0 10px 0;'>LONGITUDINAL REPORT</div>",
        unsafe_allow_html=True,
    )
    player_col, slider_col, refresh_col = st.columns([1.6, 3.2, 1.6])
    with player_col:
        player = st.selectbox("Player Name dropdown", players)
    with slider_col:
        date_range = st.slider(
            "Date range", min_value=min_date, max_value=max_date,
            value=(min_date, max_date), format="DD/MM",
        )
    with refresh_col:
        with st.container(key="refresh_box", border=True):
            if st.button("🔄 Refresh data now"):
                st.session_state.cache_buster += 1
                load_data.clear()
                st.rerun()
            st.markdown(
                f"<div style='font-size:10.5px; opacity:0.85; margin-top:4px; "
                f"margin-bottom:2px; white-space:nowrap; text-align:center;'>"
                f"Auto-refreshes every {CACHE_TTL_SECONDS}s · last loaded {time.strftime('%H:%M:%S')}</div>",
                unsafe_allow_html=True,
            )

start_date, end_date = date_range

# ---------------------------------------------------------------- filter data
gps_player_full = gps_day[gps_day["Player Name"] == player].sort_values("Date")
fb_player_full = fb_day[fb_day["Athlete name"] == player].sort_values("Date")

mask = (gps_player_full["Date"].dt.date >= start_date) & (gps_player_full["Date"].dt.date <= end_date)
gps_player_all = gps_player_full[mask]

fb_mask = (fb_player_full["Date"].dt.date >= start_date) & (fb_player_full["Date"].dt.date <= end_date)
fb_player_range = fb_player_full[fb_mask]

if gps_player_all.empty:
    st.warning("No GPS data found for this player in the selected date range.")
    st.stop()

# build one row per CALENDAR date in the selected range (not just training
# days), so rest days appear on the charts as an empty bar with just the
# date - no value shown, since nothing happened that day.
full_calendar = pd.DataFrame({"Date": pd.date_range(start_date, end_date, freq="D")})
gps_player_display = full_calendar.merge(gps_player_all, on="Date", how="left")
fb_player_display = (
    full_calendar.merge(fb_player_range, on="Date", how="left")
    .merge(gps_player_display[["Date", "Day"]], on="Date", how="left")
)

# ---------------------------------------------------------------- charts
def render_panel(title, fig, key, legend_items=None, box_note=None):
    st.markdown(metric_title_bar(title), unsafe_allow_html=True)
    if legend_items:
        st.markdown(legend_row(legend_items, box_note=box_note), unsafe_allow_html=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)

render_panel(
    "Total Distance | Metres per Minute",
    charts.chart_total_distance(gps_player_display, gps_player_full),
    key="chart_total_distance",
    legend_items=charts.LEGEND_TOTAL_DISTANCE,
    box_note="ACWR",
)

render_panel(
    "HSR (Velocity Band 4 + 5) | Sprint Distance",
    charts.chart_hsr_sd(gps_player_display, gps_player_full),
    key="chart_hsr_sd",
    legend_items=charts.LEGEND_HSR_SD,
    box_note="ACWR",
)

render_panel(
    "Accelerations (1-3) | Decelerations (1-3)",
    charts.chart_accel_decel(
        gps_player_display, gps_player_full,
        "Acceleration B1-3 Total Efforts (Gen 2)", "Deceleration B1-3 Total Efforts (Gen 2)",
    ),
    key="chart_accel_decel_13",
    legend_items=charts.legend_accel_decel("1-3"),
    box_note="ACWR",
)

render_panel(
    "Accelerations (2-3) | Decelerations (2-3)",
    charts.chart_accel_decel(
        gps_player_display, gps_player_full,
        "Acceleration B2-3 Total Efforts (Gen 2)", "Deceleration B2-3 Total Efforts (Gen 2)",
    ),
    key="chart_accel_decel_23",
    legend_items=charts.legend_accel_decel("2-3"),
    box_note="ACWR",
)

render_panel(
    "Max Speed | Max Speed %",
    charts.chart_max_speed(gps_player_display, gps_player_full),
    key="chart_max_speed",
    legend_items=charts.LEGEND_MAX_SPEED,
    box_note="Days Since 90%+",
)

if fb_player_range.empty:
    st.info("No heart rate (Firstbeat) data found for this player in the selected date range.")
else:
    render_panel(
        "Heart Rate Zone Minutes",
        charts.chart_hr_zones(fb_player_display),
        key="chart_hr_zones",
        legend_items=charts.LEGEND_HR_ZONES,
        box_note="Training Effect",
    )