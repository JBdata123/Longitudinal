"""
SIMPLE VERSION - no Dropbox needed. Just upload your two Excel files
directly in the browser. Use this to confirm the dashboard itself works,
then switch back to app.py (the live Dropbox version) once that's sorted.
"""
import pandas as pd
import streamlit as st

from theme import NAVY, GOLD, WHITE, FONT, metric_title_bar
import charts

st.set_page_config(page_title="LCFC Longitudinal Report", layout="wide", page_icon="🦊")

st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    div.block-container {{ padding-top: 0rem; }}

    .st-key-header_bar {{
        background-color: {NAVY} !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 10px 24px 4px 24px !important;
        box-shadow: none !important;
    }}
    .st-key-header_bar2 {{
        background-color: {NAVY} !important;
        border: none !important;
        border-bottom: 5px solid {GOLD} !important;
        border-radius: 0 !important;
        padding: 0px 24px 14px 24px !important;
        box-shadow: none !important;
    }}
    .st-key-header_bar, .st-key-header_bar *,
    .st-key-header_bar2, .st-key-header_bar2 * {{ color: {WHITE} !important; }}
    .st-key-header_bar label, .st-key-header_bar p {{ color: {WHITE} !important; font-family: {FONT}; }}
    .st-key-header_bar div[data-baseweb="select"] > div,
    .st-key-header_bar2 div[data-baseweb="select"] > div {{
        background-color: {NAVY} !important; border-color: {WHITE} !important; color: {WHITE} !important;
    }}
    .st-key-header_bar div[data-baseweb="select"] svg,
    .st-key-header_bar2 div[data-baseweb="select"] svg {{ fill: {WHITE} !important; }}
    div[data-baseweb="popover"] ul[role="listbox"] {{ background-color: {NAVY} !important; }}
    div[data-baseweb="popover"] li {{ background-color: {NAVY} !important; color: {WHITE} !important; }}
    div[data-baseweb="popover"] li:hover {{ background-color: {GOLD} !important; color: {NAVY} !important; }}
    h1, h2, h3 {{ text-align: center; }}
</style>
""", unsafe_allow_html=True)

with st.container(key="header_bar", border=True):
    st.markdown(
        "<div style='font-size:26px; font-weight:700; letter-spacing:1px;'>LONGITUDINAL REPORT</div>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        gps_file = st.file_uploader("Upload GPS Dummy Data.xlsx", type="xlsx")
    with c2:
        fb_file = st.file_uploader("Upload firstbeat_data.xlsx", type="xlsx")

if not gps_file or not fb_file:
    st.info("Upload both files above to see the report.")
    st.stop()

gps = pd.read_excel(gps_file)
fb = pd.read_excel(fb_file)
gps["Date"] = pd.to_datetime(gps["Date"])
fb["Date"] = pd.to_datetime(fb["Start date (dd.mm.yyyy)"], format="%d.%m.%Y")

gps_day = gps[(gps["Period Number"] == 0) & (gps["Period Name"] == "Session")].copy()
fb_day = fb[fb["Analysis period"] == "Measurement"].copy()

players = sorted(gps_day["Player Name"].dropna().unique())
min_date = gps_day["Date"].min().date()
max_date = gps_day["Date"].max().date()

with st.container(key="header_bar2", border=True):
    d1, d2 = st.columns([3, 1.5])
    with d1:
        date_range = st.slider("Date range", min_value=min_date, max_value=max_date,
                                value=(min_date, max_date), format="DD/MM")
    with d2:
        player = st.selectbox("Player Name dropdown", players)

start_date, end_date = date_range
gps_player_full = gps_day[gps_day["Player Name"] == player].sort_values("Date")
fb_player_full = fb_day[fb_day["Athlete name"] == player].sort_values("Date")

mask = (gps_player_full["Date"].dt.date >= start_date) & (gps_player_full["Date"].dt.date <= end_date)
gps_player_all = gps_player_full[mask]
fb_mask = (fb_player_full["Date"].dt.date >= start_date) & (fb_player_full["Date"].dt.date <= end_date)
fb_player = fb_player_full[fb_mask].merge(gps_player_all[["Date", "Day"]], on="Date", how="inner")

if gps_player_all.empty:
    st.warning("No GPS data found for this player in the selected date range.")
    st.stop()

def render_panel(title, fig, key):
    st.markdown(metric_title_bar(title), unsafe_allow_html=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)

render_panel("Total Distance | Metres per Minute",
             charts.chart_total_distance(gps_player_all, gps_player_full), key="c1")
render_panel("HSR (Velocity Band 4 + 5) | Sprint Distance",
             charts.chart_hsr_sd(gps_player_all, gps_player_full), key="c2")
render_panel("Accelerations (1-3) | Decelerations (1-3)",
             charts.chart_accel_decel(gps_player_all, gps_player_full,
                 "Acceleration B1-3 Total Efforts (Gen 2)", "Deceleration B1-3 Total Efforts (Gen 2)"), key="c3")
render_panel("Accelerations (2-3) | Decelerations (2-3)",
             charts.chart_accel_decel(gps_player_all, gps_player_full,
                 "Acceleration B2-3 Total Efforts (Gen 2)", "Deceleration B2-3 Total Efforts (Gen 2)"), key="c4")
if not fb_player.empty:
    render_panel("70-79% HR Max | 80-89% HR Max | 90%+ HR Max",
                 charts.chart_hr_zones(fb_player), key="c5")
