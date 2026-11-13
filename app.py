from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from theme import NAVY, GOLD, WHITE, FONT, metric_title_bar, legend_row
from data_loader import load_data, load_player_status, CACHE_TTL_SECONDS
import charts

st.set_page_config(page_title="LCWFC Longitudinal Report", layout="wide")

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
    .st-key-header_bar div[data-baseweb="slider"] div[role="slider"] {{
        background-color: {GOLD} !important;
    }}
    .st-key-header_bar div[data-testid="stTickBar"] {{ color: {WHITE} !important; }}
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

# ---------------------------------------------------------------- auto refresh every 60s
st_autorefresh(interval=CACHE_TTL_SECONDS * 1000, key="auto_refresh")

if "cache_buster" not in st.session_state:
    st.session_state.cache_buster = 0

# ---------------------------------------------------------------- load data
try:
    gps_day, fb_day, gps_periods = load_data(st.session_state.cache_buster)
except Exception as e:
    st.error(f"Couldn't load data from Dropbox: {e}")
    st.info("Check .streamlit/secrets.toml has valid Dropbox credentials and file paths.")
    st.stop()

players = sorted(gps_day["Player Name"].dropna().unique())
min_date = gps_day["Date"].min().date()
max_date = gps_day["Date"].max().date()

# Date -> Week Number map from the GPS sheet (the only sheet carrying week
# numbers), reused to tag Firstbeat data by date.
week_map = gps_day[["Date", "Week Number"]].drop_duplicates(subset="Date")

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
                f"Auto-refreshes every {CACHE_TTL_SECONDS}s · last loaded {datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK</div>",
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

# build one row per CALENDAR date in the selected range
full_calendar = pd.DataFrame({"Date": pd.date_range(start_date, end_date, freq="D")})
gps_player_display = full_calendar.merge(gps_player_all, on="Date", how="left")

# Firstbeat: collapse multiple sessions on the same date (HI minutes summed,
# TE = day's peak) BEFORE merging onto the calendar.
fb_daily_full = charts.aggregate_fb_daily(fb_player_full).merge(week_map, on="Date", how="left")
fb_daily_range = fb_daily_full[
    (fb_daily_full["Date"].dt.date >= start_date) & (fb_daily_full["Date"].dt.date <= end_date)
]
fb_player_display = (
    full_calendar.merge(fb_daily_range, on="Date", how="left")
    .merge(gps_player_display[["Date", "Day"]], on="Date", how="left")
)


# ---------------------------------------------------------------- shared panel renderer
def render_panel(title, fig, key, legend_items=None, box_note=None):
    st.markdown(metric_title_bar(title), unsafe_allow_html=True)
    if legend_items:
        st.markdown(legend_row(legend_items, box_note=box_note), unsafe_allow_html=True)
    plot_config = {
        "displayModeBar": True,
        "displaylogo": False,
        "modeBarButtonsToRemove": [
            "zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
            "autoScale2d", "resetScale2d", "hoverClosestCartesian",
            "hoverCompareCartesian", "toggleSpikelines",
        ],
        "toImageButtonOptions": {"format": "png", "filename": key, "scale": 2},
    }
    st.plotly_chart(fig, width="stretch", config=plot_config, key=key, theme=None)


# ---------------------------------------------------------------- weekly summary configuration
PLAYER_METRICS = {
    "olivia mcloughlin": {
        "avg": {"total_distance": 32996, "hsr_sd": 778, "accel": 271, "decel": 279, "hr_hi": None, "accel_hi": 33, "decel_hi": 47},
        "max": {"total_distance": 34200, "hsr_sd": 1293 + 92, "accel": 355, "decel": 327, "hr_hi": None, "accel_hi": 57, "decel_hi": 73},
    },
    "emma jansson": {
        "avg": {"total_distance": 25713, "hsr_sd": 690 + 72, "accel": 260, "decel": 272, "hr_hi": None, "accel_hi": 31, "decel_hi": 44},
        "max": {"total_distance": 29581, "hsr_sd": 1251 + 145, "accel": 363, "decel": 307, "hr_hi": None, "accel_hi": 63, "decel_hi": 67},
    },
    "celeste boureille": {
        "avg": {"total_distance": 28309, "hsr_sd": 721, "accel": 282, "decel": 242, "hr_hi": None, "accel_hi": 39, "decel_hi": 45},
        "max": {"total_distance": 31848, "hsr_sd": 1036 + 189, "accel": 381, "decel": 276, "hr_hi": None, "accel_hi": 62, "decel_hi": 71},
    },
}

player_key = player.strip().lower()
player_data = PLAYER_METRICS.get(player_key, {"avg": {}, "max": {}})

avg_total_distance = player_data["avg"].get("total_distance")
avg_hsr_sd = player_data["avg"].get("hsr_sd")
avg_accel = player_data["avg"].get("accel")
avg_decel = player_data["avg"].get("decel")
avg_hr_hi = player_data["avg"].get("hr_hi")
avg_accel_hi = player_data["avg"].get("accel_hi")
avg_decel_hi = player_data["avg"].get("decel_hi")

max_total_distance = player_data["max"].get("total_distance")
max_hsr_sd = player_data["max"].get("hsr_sd")
max_accel = player_data["max"].get("accel")
max_decel = player_data["max"].get("decel")
max_hr_hi = player_data["max"].get("hr_hi")
max_accel_hi = player_data["max"].get("accel_hi")
max_decel_hi = player_data["max"].get("decel_hi")

# ---------------------------------------------------------------- week range filter (weekly charts)
# Only filters which weekly bars are drawn - the Average bar and max lines
# still use every week.
all_weeks = sorted(
    {int(w) for w in pd.to_numeric(gps_day["Week Number"], errors="coerce").dropna().unique()},
    key=charts._week_sort_key,
)
selected_weeks = None
if all_weeks:
    wk_slider_col, _wk_spacer = st.columns([3, 4])
    with wk_slider_col:
        wk_lo, wk_hi = st.select_slider(
            "Weekly charts: week range",
            options=all_weeks,
            value=(all_weeks[0], all_weeks[-1]),
            format_func=lambda w: f"Week {w}",
            key="week_range_slider",
        )
    selected_weeks = all_weeks[all_weeks.index(wk_lo): all_weeks.index(wk_hi) + 1]

wk1, wk2, wk3, wk4 = st.columns(4)
with wk1:
    render_panel(
        "Weekly Total Distance",
        charts.chart_weekly_single(
            gps_player_full, "Total Distance", avg_total_distance, charts.GOLD,
            bullet_marker=max_total_distance, weeks=selected_weeks,
        ),
        key="chart_weekly_total_distance",
        legend_items=charts.LEGEND_WEEKLY_TOTAL_DISTANCE,
    )
with wk2:
    render_panel(
        "Weekly HSR + SD",
        charts.chart_weekly_hsr_sd(
            gps_player_full, avg_hsr_sd,
            bullet_marker=max_hsr_sd, weeks=selected_weeks,
        ),
        key="chart_weekly_hsr_sd",
        legend_items=charts.LEGEND_WEEKLY_HSR_SD,
    )
with wk3:
    render_panel(
        "Weekly Accelerations | Decelerations",
        charts.chart_weekly_accel_decel(
            gps_player_full,
            "Acceleration B1-3 Total Efforts (Gen 2)", "Deceleration B1-3 Total Efforts (Gen 2)",
            avg_accel=avg_accel, avg_decel=avg_decel,
            bullet_marker_accel=max_accel, bullet_marker_decel=max_decel,
            weeks=selected_weeks,
        ),
        key="chart_weekly_accel_decel",
        legend_items=charts.LEGEND_WEEKLY_ACCEL_DECEL,
    )
with wk4:
    render_panel(
        "Weekly HR Minutes >90% Max",
        charts.chart_weekly_hr_hi(
            fb_daily_full, avg_hr_hi,
            bullet_marker=max_hr_hi, weeks=selected_weeks,
        ),
        key="chart_weekly_hr_hi",
        legend_items=charts.LEGEND_WEEKLY_HR_HI,
    )

# ---------------------------------------------------------------- second weekly row
player_max_vel = charts.player_max_velocity(gps_player_full)

wk5, wk6 = st.columns(2)
with wk5:
    render_panel(
        "Weekly High Intensity Accelerations | Decelerations (2-3)",
        charts.chart_weekly_accel_decel(
            gps_player_full,
            "Acceleration B2-3 Total Efforts (Gen 2)", "Deceleration B2-3 Total Efforts (Gen 2)",
            avg_accel=avg_accel_hi, avg_decel=avg_decel_hi,
            bullet_marker_accel=max_accel_hi, bullet_marker_decel=max_decel_hi,
            weeks=selected_weeks,
        ),
        key="chart_weekly_accel_decel_23",
        legend_items=charts.LEGEND_WEEKLY_ACCEL_DECEL,
    )
with wk6:
    render_panel(
        "Weekly Max Velocity",
        charts.chart_weekly_max_velocity(gps_player_full, bullet_marker=player_max_vel, weeks=selected_weeks),
        key="chart_weekly_max_velocity",
        legend_items=charts.LEGEND_WEEKLY_MAX_VEL,
    )

# ---------------------------------------------------------------- third weekly row (jumps / dives)
# Dives = left + centre + right dive counts added together.
gps_player_full = gps_player_full.copy()
_dive_cols = ["Dive Left Count", "Dive Centre Count", "Dive Right Count"]
if all(c in gps_player_full.columns for c in _dive_cols):
    gps_player_full["Dives (L+C+R)"] = (
        gps_player_full[_dive_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    )


def weekly_count_panel(col, title, bar_color, legend, key, avg_value=None, max_value=None):
    """Weekly total of a count metric, with average bar + max line. Skipped
    with a note if the column is missing or the player has none recorded."""
    if col not in gps_player_full.columns:
        st.info(f"No data for {title.lower()} in the GPS sheet.")
        return
    if not (pd.to_numeric(gps_player_full[col], errors="coerce").fillna(0) > 0).any():
        st.info(f"No {title.lower()} recorded for this player.")
        return
    render_panel(
        title,
        charts.chart_weekly_single(gps_player_full, col, avg_value, bar_color, bullet_marker=max_value, weeks=selected_weeks),
        key=key,
        legend_items=legend,
    )


wk7, wk8 = st.columns(2)
with wk7:
    weekly_count_panel(
        "Total Jumps", "Weekly Jumps", charts.GREEN, charts.LEGEND_WEEKLY_JUMPS, "chart_weekly_jumps",
        avg_value=player_data["avg"].get("jumps"), max_value=player_data["max"].get("jumps"),
    )
with wk8:
    weekly_count_panel(
        "Dives (L+C+R)", "Weekly Dives", charts.GOLD, charts.LEGEND_WEEKLY_DIVES, "chart_weekly_dives",
        avg_value=player_data["avg"].get("dives"), max_value=player_data["max"].get("dives"),
    )

# ---------------------------------------------------------------- last-season game data (fallback)
# Players with NO matchday data this season (so the match-minute lines would
# otherwise be blank) use a game from last season instead. Once a player has
# real matchday data in the sheet, the sheet data is used and this is ignored.
_FALLBACK_COLS = [
    "Player Name", "Period Name", "Date", "Total Duration", "Total Distance",
    "Velocity Band 4 Total Distance", "Velocity Band 5 Total Distance", "SD",
    "Acceleration B1-3 Total Efforts (Gen 2)", "Acceleration B2-3 Total Efforts (Gen 2)",
    "Deceleration B1-3 Total Efforts (Gen 2)", "Deceleration B2-3 Total Efforts (Gen 2)",
    "Total Jumps", "Dive Left Count", "Dive Centre Count", "Dive Right Count",
]
_FALLBACK_ROWS = {
    "celeste boureille": [
        ("Celeste Boureille", "WUP",      "2025-12-07", "00:32:43", 2413.01001, 19.25, 0,     0,     27, 4,  16, 1,  5, 0, 0, 0),
        ("Celeste Boureille", "1st Half", "2025-12-07", "00:54:19", 4618.62744, 74.91, 0,     0,     32, 2,  38, 7,  4, 0, 0, 0),
        ("Celeste Boureille", "2nd Half", "2025-12-07", "00:51:57", 4498.51221, 89.19, 23.88, 16.67, 30, 3,  34, 10, 4, 0, 0, 0),
    ],
    "emma jansson": [
        ("Emma Jansson", "WUP",      "2026-05-03", "00:34:50", 2571.42554, 11.76,  0,     0,    34, 7,  31, 6,  1, 0, 0, 0),
        ("Emma Jansson", "1st Half", "2026-05-03", "00:49:04", 5385.03027, 224.89, 59.48, 8.78, 49, 4,  56, 14, 4, 0, 0, 0),
        ("Emma Jansson", "2nd Half", "2026-05-03", "00:52:02", 5375.85986, 215.47, 39.17, 0,    51, 12, 43, 10, 2, 0, 0, 0),
    ],
}
LAST_SEASON_MATCHES = {}
for _k, _rows in _FALLBACK_ROWS.items():
    _df = pd.DataFrame(_rows, columns=_FALLBACK_COLS)
    _df["Date"] = pd.to_datetime(_df["Date"])
    LAST_SEASON_MATCHES[_k] = _df


# ---------------------------------------------------------------- manually entered day-type averages
# For players returning from injury: these figures are shown in the Activation /
# Extensive / Intensive / MD-1 boxes INSTEAD of working them out from the sheet.
# (HSR = their HSR figure, Sprint Distance = their VHSR / SD figure.)
# To go back to automatic for a player, delete their entry.
MANUAL_DAY_AVERAGES = {
    "celeste boureille": {
        "ACTIVATION": {"Total Distance": 3973, "HSR": 3,   "Sprint Distance": 0,  "Accels (1-3)": 36, "Decels (1-3)": 44},
        "EXTENSIVE":  {"Total Distance": 6975, "HSR": 352, "Sprint Distance": 61, "Accels (1-3)": 70, "Decels (1-3)": 63},
        "INTENSIVE":  {"Total Distance": 5613, "HSR": 116, "Sprint Distance": 2,  "Accels (1-3)": 62, "Decels (1-3)": 45},
        "MD-1":       {"Total Distance": 3334, "HSR": 15,  "Sprint Distance": 0,  "Accels (1-3)": 35, "Decels (1-3)": 27},
    },
    "emma jansson": {
        "ACTIVATION": {"Total Distance": 3902, "HSR": 0,   "Sprint Distance": 0,  "Accels (1-3)": 32, "Decels (1-3)": 22},
        "EXTENSIVE":  {"Total Distance": 6295, "HSR": 298, "Sprint Distance": 61, "Accels (1-3)": 60, "Decels (1-3)": 42},
        "INTENSIVE":  {"Total Distance": 5741, "HSR": 218, "Sprint Distance": 0,  "Accels (1-3)": 68, "Decels (1-3)": 52},
        "MD-1":       {"Total Distance": 4574, "HSR": 41,  "Sprint Distance": 0,  "Accels (1-3)": 65, "Decels (1-3)": 37},
    },
}

# ---------------------------------------------------------------- day-type average boxes
# Average per session for each type of day. Respects the week-range slider above.
# MD = the 1st + 2nd half only; "MD + Warm-up" = the same matches with their warm-up added.
_daily_b = gps_player_full
if selected_weeks is not None:
    _daily_b = gps_player_full[pd.to_numeric(gps_player_full["Week Number"], errors="coerce").isin(selected_weeks)]

# Optional filter: only count days where the player_status file says "fit".
fit_only = st.checkbox("Only count days where player status = Fit", value=True, key="fit_only")
_status_df, _status_msg = load_player_status(st.session_state.cache_buster)
_fit_dates, _fit_note = None, ""
if fit_only:
    if _status_msg:
        _fit_note = _status_msg
    else:
        _ps = _status_df[_status_df["name_key"] == " ".join(player.lower().split())]
        if _ps.empty:
            _fit_note = f"No rows for {player} in the player status file, so all days are counted."
        else:
            _fit_dates = set(_ps.loc[_ps["Fit"], "Date"])
            _status_dates = set(_ps["Date"])
if _fit_dates is not None:
    _lab_set = {"ACTIVATION", "EXTENSIVE", "INTENSIVE", "MD-1"}
    _pre = _daily_b[_daily_b["Day"].apply(charts._norm_day).isin(_lab_set)]
    _no_status = int((~_pre["Date"].isin(_status_dates)).sum())
    _daily_b = _daily_b[_daily_b["Date"].isin(_fit_dates)]
    _after = int(_daily_b["Day"].apply(charts._norm_day).isin(_lab_set).sum())
    _fit_note = f"fit days only: {_after} of {len(_pre)} sessions counted" + (
        f" ({_no_status} had no status row)" if _no_status else "")

_pp = gps_periods[gps_periods["Player Name"] == player]
_md_dates_b = set(gps_player_full.loc[charts.is_match_day(gps_player_full["Day"]), "Date"])
_pp_md = _pp[charts.is_match_day(_pp["Day"]) | _pp["Date"].isin(_md_dates_b)]
if selected_weeks is not None and "Week Number" in _pp_md.columns:
    _pp_md = _pp_md[pd.to_numeric(_pp_md["Week Number"], errors="coerce").isin(selected_weeks)]
if _fit_dates is not None:
    _pp_md = _pp_md[_pp_md["Date"].isin(_fit_dates)]
_pp_warm = charts.is_warmup_period(_pp_md["Period Name"])
_halves_b, _warm_b = _pp_md[~_pp_warm], _pp_md[_pp_warm]

_md_note = ""
if _halves_b.empty and player_key in LAST_SEASON_MATCHES:      # no games yet this season
    _fb_b = LAST_SEASON_MATCHES[player_key]
    _fb_w = charts.is_warmup_period(_fb_b["Period Name"])
    _halves_b, _warm_b = _fb_b[~_fb_w], _fb_b[_fb_w]
    _md_note = ""   # (was "last season" - the note under the MD boxes has been removed)

_day_boxes = []
for _title, _label in [("Activation", "ACTIVATION"), ("Extensive", "EXTENSIVE"),
                       ("Intensive", "INTENSIVE"), ("MD-1", "MD-1")]:
    _st, _n = charts.day_type_stats(_daily_b, _label)
    _st = MANUAL_DAY_AVERAGES.get(player_key, {}).get(_label, _st)   # manual figures win, if entered
    _day_boxes.append((_title, _st, _n, ""))
_st, _n = charts.match_day_stats(_halves_b)
_day_boxes.append(("MD", _st, _n, _md_note))
_st, _n = charts.match_day_stats(_halves_b, _warm_b)
_day_boxes.append(("MD + Warm-up", _st, _n, _md_note))

if player_key in MANUAL_DAY_AVERAGES:
    _fit_note = "Activation, Extensive, Intensive and MD-1 use manually entered averages"
st.caption("Average per day type (follows the week range above)" + (f" \u00b7 {_fit_note}" if _fit_note else ""))
for _col, (_title, _st, _n, _note) in zip(st.columns(6), _day_boxes):
    with _col:
        st.markdown(metric_title_bar(_title), unsafe_allow_html=True)
        st.markdown(charts.day_box_html(_st, _n, _note), unsafe_allow_html=True)

# ---------------------------------------------------------------- match-minute reference lines
mm_col, wu_col, _spacer = st.columns([2, 2, 3])
with mm_col:
    minutes_text = st.text_input(
        "Match-minute reference lines (comma separated, e.g. 30, 45, 90)",
        value="45, 90", key="match_minutes_input",
    )
with wu_col:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    include_wu = st.checkbox(
        "Add average warm-up on top of the lines (+ WU)", value=True, key="include_wu",
    )
match_minutes = charts.parse_match_minutes(minutes_text)

# Matchday = Day label containing "GAME" or "MD" (not MD-1 / MD+1). Per-minute
# rates use only that player's matchday 1st/2nd-half rows, pooled: total of the
# metric / total of Total Duration. The warm-up average is the player's
# matchday warm-up load averaged across their matchdays.
md_dates = set(gps_player_full.loc[charts.is_match_day(gps_player_full["Day"]), "Date"])
player_periods = gps_periods[gps_periods["Player Name"] == player]
periods_md = player_periods[
    charts.is_match_day(player_periods["Day"]) | player_periods["Date"].isin(md_dates)
]
_is_warm = charts.is_warmup_period(periods_md["Period Name"])
halves_md = periods_md[~_is_warm]
warm_md = periods_md[_is_warm]

# No matchday data this season -> fall back to last season's game (if we have one).
using_last_season = False
if halves_md.empty and player_key in LAST_SEASON_MATCHES:
    _fb = LAST_SEASON_MATCHES[player_key]
    _fb_warm = charts.is_warmup_period(_fb["Period Name"])
    halves_md, warm_md = _fb[~_fb_warm], _fb[_fb_warm]
    using_last_season = True

_HSR_SD_COLS = ["Velocity Band 4 Total Distance", "Velocity Band 5 Total Distance", "SD"]
_ACC13, _DEC13 = ["Acceleration B1-3 Total Efforts (Gen 2)"], ["Deceleration B1-3 Total Efforts (Gen 2)"]
_ACC23, _DEC23 = ["Acceleration B2-3 Total Efforts (Gen 2)"], ["Deceleration B2-3 Total Efforts (Gen 2)"]

rate_td = charts.match_rate_per_min(halves_md, ["Total Distance"])
rate_hsr_sd = charts.match_rate_per_min(halves_md, _HSR_SD_COLS)
rate_acc_13 = charts.match_rate_per_min(halves_md, _ACC13)
rate_dec_13 = charts.match_rate_per_min(halves_md, _DEC13)
rate_acc_23 = charts.match_rate_per_min(halves_md, _ACC23)
rate_dec_23 = charts.match_rate_per_min(halves_md, _DEC23)


def _wu(cols):
    return charts.warmup_avg(warm_md, cols) if include_wu else None


_JUMPS = ["Total Jumps"]
_DIVES = ["Dive Left Count", "Dive Centre Count", "Dive Right Count"]
rate_jumps = charts.match_rate_per_min(halves_md, _JUMPS)
rate_dives = charts.match_rate_per_min(halves_md, _DIVES)

lines_td = charts.match_lines(rate_td, match_minutes, warmup=_wu(["Total Distance"]))
lines_hsr_sd = charts.match_lines(rate_hsr_sd, match_minutes, warmup=_wu(_HSR_SD_COLS))
lines_acc_13 = charts.match_lines(rate_acc_13, match_minutes, warmup=_wu(_ACC13))
lines_dec_13 = charts.match_lines(rate_dec_13, match_minutes, warmup=_wu(_DEC13))
lines_acc_23 = charts.match_lines(rate_acc_23, match_minutes, warmup=_wu(_ACC23))
lines_dec_23 = charts.match_lines(rate_dec_23, match_minutes, warmup=_wu(_DEC23))
lines_jumps = charts.match_lines(rate_jumps, match_minutes, warmup=_wu(_JUMPS))
lines_dives = charts.match_lines(rate_dives, match_minutes, warmup=_wu(_DIVES))

if match_minutes and using_last_season:
    _gd = halves_md["Date"].min().strftime("%d/%m/%Y")
    st.caption(f"No games played this season yet, so the match-minute lines use {player}'s game on {_gd} (last season).")
elif match_minutes and rate_td is None:
    st.caption("No matchday (MD) 1st/2nd-half data found for this player, so no match-minute lines are shown.")
elif match_minutes and include_wu and charts.warmup_avg(warm_md, ["Total Distance"]) is None:
    st.caption("No matchday warm-up rows found for this player, so the lines show the match-minute value without warm-up.")

# ---------------------------------------------------------------- daily charts
render_panel(
    "Total Distance | Metres per Minute",
    charts.chart_total_distance(gps_player_display, gps_player_full, match_lines=lines_td),
    key="chart_total_distance",
    legend_items=charts.LEGEND_TOTAL_DISTANCE,
    box_note="ACWR",
)
render_panel(
    "HSR (Velocity Band 4 + 5) | Sprint Distance",
    charts.chart_hsr_sd(gps_player_display, gps_player_full, match_lines=lines_hsr_sd),
    key="chart_hsr_sd",
    legend_items=charts.LEGEND_HSR_SD,
    box_note="ACWR",
)
render_panel(
    "Accelerations (1-3) | Decelerations (1-3)",
    charts.chart_accel_decel(
        gps_player_display, gps_player_full,
        "Acceleration B1-3 Total Efforts (Gen 2)", "Deceleration B1-3 Total Efforts (Gen 2)",
        accel_lines=lines_acc_13, decel_lines=lines_dec_13,
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
        accel_lines=lines_acc_23, decel_lines=lines_dec_23,
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

# ---------------------------------------------------------------- jumps / dives
def gk_panel(title, col, key, color, legend, match_lines=None):
    if col not in gps_player_display.columns:
        st.info(f"No '{col}' column found in the GPS data, so {title} can't be shown.")
        return
    vals = pd.to_numeric(gps_player_display[col], errors="coerce")
    if not (vals.fillna(0) > 0).any():
        st.info(f"No {title.lower()} recorded for this player in the selected date range.")
        return
    render_panel(
        title,
        charts.chart_daily_count(gps_player_display, col, color, title, match_lines=match_lines),
        key=key,
        legend_items=legend,
    )


gk_panel("Jumps", "Total Jumps", "chart_jumps", charts.GREEN, charts.LEGEND_JUMPS, match_lines=lines_jumps)
# Dives = left + centre + right dive counts added together
dive_cols = ["Dive Left Count", "Dive Centre Count", "Dive Right Count"]
if all(c in gps_player_display.columns for c in dive_cols):
    gps_player_display["Dives (L+C+R)"] = (
        gps_player_display[dive_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    )
gk_panel("Dives", "Dives (L+C+R)", "chart_dives", charts.GOLD, charts.LEGEND_DIVES, match_lines=lines_dives)
