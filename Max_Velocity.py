"""
Max Velocity.

For every player on the squad list (the `players` table in Supabase): the last
day they reached 90% of their max speed, how many days ago that was, what
percentage they actually reached, and on how many of the last 7 days they got
there.

Needs [supabase] db_url in the Streamlit secrets (same as the other pages) and
the velocity_logic.py file next to it.
"""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
import streamlit as st

import velocity_logic as vl
from theme import NAVY, GOLD, WHITE, FONT

CACHE_TTL_SECONDS = 60
VELOCITY_VERSION = 1          # keep in step with velocity_logic.py

st.set_page_config(page_title="Max Velocity", layout="wide")

st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    h1, h2, h3 {{ color: {NAVY}; }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- is velocity_logic.py the right file?
_NEEDED = ("build_squad_table", "players_not_on_squad", "sort_table", "summarise", "colour_state", "today_uk")
if (getattr(vl, "VELOCITY_FILE", None) != "velocity_logic.py"
        or getattr(vl, "VELOCITY_VERSION", None) != VELOCITY_VERSION
        or any(not hasattr(vl, n) for n in _NEEDED)):
    st.error("The Max Velocity files in your GitHub repo don't match each other. "
             "Out of date or wrong file: velocity_logic.py.")
    st.info("Upload the latest version of both files together (Max_Velocity.py and velocity_logic.py), replacing the "
            "old ones, each under its own name. To check, open velocity_logic.py on GitHub: it should start with the "
            "words 'Max velocity app calculations'. Then open Manage app and choose Reboot app.")
    st.stop()


# ---------------------------------------------------------------- data
def connect():
    return psycopg2.connect(st.secrets["supabase"]["db_url"])


SQUAD_SQL = "select player_name, position from players order by player_name"

# Each day's top percentage of max speed per player: the highest any period reached that day (training drills,
# match halves and intervals all count). Catapult's own "Max Vel (% Max)" is used; where it's missing it is worked
# out from the speed and the player's profile max, which is the same thing.
DAILY_SQL = """
    select player, session_date, max(pct) as day_pct
    from (
        select player, session_date,
               coalesce(gps_max_vel_max,
                        case when gps_profile_max_velocity > 0
                             then gps_maximum_velocity / gps_profile_max_velocity * 100 end) as pct
        from master_data
        where player is not null and session_date is not null
    ) x
    where pct is not null
    group by player, session_date
"""


def _frame(cur):
    return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading the squad list...")
def load_squad():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(SQUAD_SQL)
            return _frame(cur)
    finally:
        conn.close()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading max speed data...")
def load_daily():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DAILY_SQL)
            df = _frame(cur)
    finally:
        conn.close()
    df["day_pct"] = pd.to_numeric(df["day_pct"], errors="coerce")
    return df


try:
    squad = load_squad()
    daily = load_daily()
except Exception as exc:
    st.error(f"Couldn't load data from Supabase: {exc}")
    st.info("Check the [supabase] db_url secret, and that the players table (the squad list) exists.")
    st.stop()

# ---------------------------------------------------------------- header
THRESHOLD = vl.THRESHOLD_PCT
WINDOW = vl.WINDOW_DAYS
st.markdown(
    f"""
    <div style="background-color:{NAVY}; border-bottom:5px solid {GOLD}; padding:16px 24px;
                margin-bottom:20px; color:{WHITE}; display:flex; align-items:center;
                justify-content:space-between;">
        <div style="font-size:28px; font-weight:800; letter-spacing:1px; color:{WHITE};">MAX VELOCITY</div>
        <div style="font-size:11px; opacity:0.85; text-align:right; color:{WHITE}; white-space:nowrap;">
            last loaded {datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns([2, 2, 3])
with c1:
    if st.button("Refresh data now"):
        load_squad.clear()
        load_daily.clear()
        st.rerun()
with c2:
    include_gk = st.checkbox("Include goalkeepers", value=False)
with c3:
    sort_by = st.selectbox("Sort by", vl.SORT_OPTIONS, label_visibility="collapsed")

if squad.empty:
    st.info("The squad list is empty. Add players to the players table in Supabase and they'll appear here.")
    st.stop()

today = vl.today_uk()
table = vl.sort_table(vl.build_squad_table(squad, daily, today, include_goalkeepers=include_gk), sort_by)
facts = vl.summarise(table)


# ---------------------------------------------------------------- headline tiles
def tile(label, value, sub=""):
    sub_html = (f"<div style='font-size:12px;opacity:.85;margin-top:2px'>{escape(sub)}</div>" if sub else "")
    return (f"<div style='background:{NAVY};color:{WHITE};border-radius:8px;padding:10px 14px;font-family:{FONT}'>"
            f"<div style='font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.85'>{escape(label)}</div>"
            f"<div style='font-size:24px;font-weight:700;line-height:1.2'>{escape(str(value))}</div>{sub_html}</div>")


longest = (f"{facts['longest_days']} days" if facts["longest_days"] is not None else "n/a")
tiles = [
    tile("Squad players", facts["squad"]),
    tile(f"Reached {THRESHOLD:g}% in the last {WINDOW} days", f"{facts['reached_in_window']} of {facts['squad']}"),
    tile(f"Longest since {THRESHOLD:g}%", longest, facts["longest_player"] or ""),
    tile(f"Never reached {THRESHOLD:g}%", facts["never"]),
]
st.markdown("<div style='display:flex;gap:10px;flex-wrap:wrap;margin:4px 0 14px'>"
            + "".join(f"<div style='flex:1;min-width:170px'>{t}</div>" for t in tiles) + "</div>",
            unsafe_allow_html=True)

# ---------------------------------------------------------------- the table
days_col = f"Days since {THRESHOLD:g}%"
times_col = f"Times in last {WINDOW} days"
display = pd.DataFrame({
    "Player": table["player"],
    "Position": table["position"].fillna(""),
    days_col: [str(int(d)) if s == "hit" else ("Never" if s == "never" else "No data")
               for s, d in zip(table["state"], table["days_since"])],
    "Last reached": [d.strftime("%d/%m/%Y") if s == "hit" else "-" for s, d in zip(table["state"], table["last_date"])],
    "% reached": [f"{p:.1f}%" if s == "hit" else "-" for s, p in zip(table["state"], table["pct_reached"])],
    times_col: table["times_in_window"],
})

CELL = {"green": f"background-color:#2e7d32;color:{WHITE};font-weight:700",
        "amber": f"background-color:{GOLD};color:{NAVY};font-weight:700",
        "red": f"background-color:#d32f2f;color:{WHITE};font-weight:700",
        "grey": "background-color:#9aa5b5;color:#ffffff;font-weight:700"}


def colour_days(column):
    return [CELL[vl.colour_state(s, d)] for s, d in zip(table["state"], table["days_since"])]


st.dataframe(display.style.apply(colour_days, subset=[days_col]), width="stretch", hide_index=True,
             height=min(38 * (len(display) + 1) + 3, 900))
st.caption(
    f"Days since {THRESHOLD:g}% is today minus the last day the player's top speed, in any session, reached "
    f"{THRESHOLD:g}% of their max. % reached is the highest they got on that day. Times in the last {WINDOW} days "
    f"counts the days they reached {THRESHOLD:g}% (today and the {WINDOW - 1} days before), so a session counts once "
    f"however many times it happened. Green is {vl.DAYS_GREEN_UP_TO} days or fewer, amber up to {vl.DAYS_AMBER_UP_TO}, "
    f"red beyond that or never.")

no_data = [p for p, s in zip(table["player"], table["state"]) if s == "nodata"]
if no_data:
    st.caption("No max speed data found for: " + ", ".join(no_data) +
               ". If that's unexpected, the name may be spelled differently in the GPS data.")

with st.expander("Players in the GPS data who aren't on your squad list (left out)"):
    outside = vl.players_not_on_squad(squad, daily)
    st.write(", ".join(outside) if outside else "None. Everyone in the GPS data is on your squad list.")
