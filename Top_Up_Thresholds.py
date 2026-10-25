"""
Top-Up Thresholds -- one file.

After a game, shows how far each player is from their AVERAGE WEEK for total distance
and high speed running, and gives you a CSV in exactly the layout of your Catapult
athlete thresholds file, ready to import:

    Athlete ID, Athlete Name, Position, Total Distance, High Speed Distance

The numbers
  * The week is worked out by itself: the latest week in the GPS data (you can pick another).
  * A player's "average week" is the average of their own weekly totals over the earlier
    weeks, using the same rules as your Power BI weekly report: SESSION rows only, Fit
    players only, in-season weeks only (week 1 up), week 19's test data left out, and only
    weeks where that player took part in every session the squad had (a part-week would
    drag the average down).
  * "This week so far" is their total for the selected week up to now.
  * "Still to do" = average week minus this week so far (blank if they've already reached it).
  * High speed running = velocity band 4 + band 5 distance, as everywhere else in your reports.

Your athlete list (ID, name, position as Catapult writes them) comes from your own Catapult
file. Upload it the first time and press Save, and the page remembers it.

Needs the [supabase] db_url secret your other pages already use.
"""
import csv
import datetime as dt
import io
import re
import unicodedata
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
import streamlit as st

try:
    from theme import NAVY, GOLD, WHITE          # your app's colours, if theme.py is next to this file
except ImportError:
    NAVY, GOLD, WHITE = "#0a2540", "#fdbe11", "#ffffff"

# ============================================================================
# SETTINGS
# ============================================================================
EXCLUDE_WEEKS = [19]                 # test data weeks, left out of everyone's history (as in the Power BI weekly card)
SKIP_POSITIONS_CONTAINING = "keeper"   # goalkeepers get no thresholds (their rows stay in the file, blank)
CACHE_TTL_SECONDS = 60

OUT_COLUMNS = ["Athlete ID", "Athlete Name", "Position", "Total Distance", "High Speed Distance"]
REQUIRED_COLUMNS = ["Athlete ID", "Athlete Name", "Position"]
MODE_STILL = "Still to do this week (the top-up)"
MODE_AVERAGE = "Their full average week"

CREATE_ROSTER_SQL = """
create table if not exists catapult_athletes (
    athlete_id   text primary key,
    athlete_name text not null,
    position     text,
    sort_order   integer not null default 0
)
"""


# ============================================================================
# NAMES AND FILES
# ============================================================================
def person_key(name):
    """What 'Ale, Asmita' (Catapult's way) and 'Asmita Ale' (your database's way) have in common. Ignores capitals,
    extra spaces and accents, so 'Nystr\u00f6m' and 'Nystrom' match."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    if "," in text:
        last, first = (part.strip() for part in text.split(",", 1))
        text = f"{first} {last}"
    return re.sub(r"\s+", " ", text).strip()


def read_template(raw):
    """Read your Catapult athlete file (comma- or tab-separated, as downloaded or pasted from Excel) into the
    three columns that identify each athlete. Any numbers already in it are ignored."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    try:
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError(f"That file couldn't be read as a table ({exc}).") from exc
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("The file is missing these columns: " + ", ".join(missing) +
                         ". It should have: " + ", ".join(OUT_COLUMNS) + ".")
    df = df[REQUIRED_COLUMNS].apply(lambda col: col.str.strip())
    df = df[(df["Athlete ID"] != "") & (df["Athlete Name"] != "")].drop_duplicates("Athlete ID").reset_index(drop=True)
    if df.empty:
        raise ValueError("The file has no athletes in it.")
    return df


def _cell(value):
    """A whole number as text, or nothing at all for a blank. (A column of whole numbers with gaps in it turns into
    decimals with 'nan' for the gaps, so 3000 would come out as 3000.0 and a blank as nan.)"""
    if value is None or pd.isna(value):
        return ""
    return str(int(round(float(value))))


def build_csv(table):
    """The CSV in your Catapult layout: the same five columns in the same order, one row per athlete in the order
    of your file. Names with a comma in them (Ale, Asmita) are put in quotes, as Catapult does."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(OUT_COLUMNS)
    for row in table.itertuples():
        writer.writerow([row.athlete_id, row.athlete_name, row.position,
                         _cell(row.csv_total_distance), _cell(row.csv_high_speed)])
    return buffer.getvalue().encode("utf-8")


# ============================================================================
# THE CALCULATION
# ============================================================================
def _fit_rows(d):
    status = d["status"].astype("string").str.strip().str.lower()
    return d[status.isna() | (status == "") | (status == "fit")]       # no status recorded counts as available


def weekly_totals(rows, today, fit_only=True):
    """One row per player per week: how many SESSIONs, and the total distance and high speed distance."""
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    d = d[pd.Series([x is not None and x <= today for x in d["session_date"]], index=d.index, dtype=bool)]
    d["week"] = pd.to_numeric(d["week"], errors="coerce")
    d["total_distance"] = pd.to_numeric(d["total_distance"], errors="coerce")
    d["hsr"] = pd.to_numeric(d["hsr"], errors="coerce")
    d = d.dropna(subset=["player", "week", "total_distance"])
    if fit_only:
        d = _fit_rows(d)
    d["key"] = d["player"].map(person_key)
    g = d.groupby(["key", "week"])
    weekly = pd.DataFrame({
        "player": g["player"].first(), "sessions": g.size(),
        "td": g["total_distance"].sum(), "hsr": g["hsr"].sum(min_count=1),
    }).reset_index()
    weekly["squad_max_sessions"] = weekly.groupby("week")["sessions"].transform("max")
    weekly["full_week"] = weekly["sessions"] == weekly["squad_max_sessions"]
    return weekly


def latest_week(rows, today, exclude_weeks=EXCLUDE_WEEKS):
    """The in-season week of the most recent session up to today, or None."""
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    d["week"] = pd.to_numeric(d["week"], errors="coerce")
    d = d[pd.Series([x is not None and x <= today for x in d["session_date"]], index=d.index, dtype=bool)]
    d = d[(d["week"] > 0) & (~d["week"].isin(exclude_weeks))].dropna(subset=["week"])
    if d.empty:
        return None
    return int(d.loc[d["session_date"].idxmax(), "week"])


def available_weeks(rows, today, exclude_weeks=EXCLUDE_WEEKS):
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    d["week"] = pd.to_numeric(d["week"], errors="coerce")
    d = d[pd.Series([x is not None and x <= today for x in d["session_date"]], index=d.index, dtype=bool)]
    d = d[(d["week"] > 0) & (~d["week"].isin(exclude_weeks))].dropna(subset=["week"])
    return sorted({int(w) for w in d["week"]}, reverse=True)


def week_summary(rows, week, today, exclude_weeks=EXCLUDE_WEEKS, fit_only=True):
    """Per player (keyed by person_key): their average week, this week so far, and what's still to do."""
    weekly = weekly_totals(rows, today, fit_only=fit_only)
    history = weekly[(weekly["week"] > 0) & (weekly["week"] < week) & (~weekly["week"].isin(exclude_weeks))
                     & weekly["full_week"]]
    average = history.groupby("key").agg(avg_td=("td", "mean"), avg_hsr=("hsr", "mean"), weeks_used=("week", "nunique"))
    now = weekly[weekly["week"] == week].set_index("key")[["player", "sessions", "td", "hsr"]]
    now = now.rename(columns={"sessions": "sessions_this_week", "td": "so_far_td", "hsr": "so_far_hsr"})
    out = now.join(average, how="left")
    out["weeks_used"] = out["weeks_used"].fillna(0).astype(int)
    out["remaining_td"] = (out["avg_td"] - out["so_far_td"]).clip(lower=0)
    out["remaining_hsr"] = (out["avg_hsr"] - out["so_far_hsr"].fillna(0)).clip(lower=0)
    out.loc[out["avg_hsr"].isna(), "remaining_hsr"] = float("nan")
    return out


def _whole(value):
    """A positive amount as a whole number, otherwise None (a blank in the file)."""
    if value is None or pd.isna(value):
        return None
    rounded = int(round(float(value)))
    return rounded if rounded > 0 else None


def build_table(roster, summary, mode=MODE_STILL):
    """One row per athlete in your file's order: what goes in the CSV, plus the numbers behind it and a note."""
    rows = []
    for athlete in roster.itertuples():
        key = person_key(athlete.athlete_name)
        position = athlete.position or ""
        base = {"athlete_id": athlete.athlete_id, "athlete_name": athlete.athlete_name, "position": position,
                "sessions": None, "weeks_used": None, "avg_td": None, "so_far_td": None, "remaining_td": None,
                "avg_hsr": None, "so_far_hsr": None, "remaining_hsr": None,
                "csv_total_distance": None, "csv_high_speed": None}
        if SKIP_POSITIONS_CONTAINING in position.casefold():
            rows.append({**base, "note": "Goalkeeper - left blank"})
            continue
        if key not in summary.index:
            rows.append({**base, "note": "No Fit session this week (or name not found in the GPS data)"})
            continue
        s = summary.loc[key]
        base.update({"sessions": int(s["sessions_this_week"]), "weeks_used": int(s["weeks_used"]),
                     "avg_td": s["avg_td"], "so_far_td": s["so_far_td"], "remaining_td": s["remaining_td"],
                     "avg_hsr": s["avg_hsr"], "so_far_hsr": s["so_far_hsr"], "remaining_hsr": s["remaining_hsr"]})
        if int(s["weeks_used"]) == 0:
            rows.append({**base, "note": "No full earlier week to average yet"})
            continue
        pick_td, pick_hsr = (("remaining_td", "remaining_hsr") if mode == MODE_STILL else ("avg_td", "avg_hsr"))
        td, hsr = _whole(s[pick_td]), _whole(s[pick_hsr])
        base.update({"csv_total_distance": td, "csv_high_speed": hsr})
        if mode == MODE_STILL and td is None and hsr is None:
            note = "Already at their average week"
        elif mode == MODE_STILL:
            note = "Top-up needed"
        else:
            note = "Average week"
        rows.append({**base, "note": note})
    return pd.DataFrame(rows)


# ============================================================================
# DATABASE
# ============================================================================
def today_uk():
    """Today's date from the computer's clock, in UK time."""
    return dt.datetime.now(ZoneInfo("Europe/London")).date()


def connect():
    return psycopg2.connect(st.secrets["supabase"]["db_url"])


# SESSION rows only. High speed running = velocity band 4 + band 5 distance (blank only if both are blank).
SESSIONS_SQL = """
    select player, session_date, gps_week_number as week, player_status as status,
           gps_total_distance as total_distance,
           case when gps_velocity_band_4_total_distance is null and gps_velocity_band_5_total_distance is null then null
                else coalesce(gps_velocity_band_4_total_distance, 0) + coalesce(gps_velocity_band_5_total_distance, 0)
           end as hsr
    from master_data
    where upper(trim(drill_label)) = 'SESSION'
      and player is not null and session_date is not null
      and gps_week_number is not null and gps_total_distance is not null
"""


def _frame(cur):
    return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading this season's sessions...")
def load_sessions():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(SESSIONS_SQL)
            return _frame(cur)
    finally:
        conn.close()


def ensure_roster_table(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_ROSTER_SQL)
            cur.execute("alter table catapult_athletes enable row level security")   # not reachable from the public web key


def load_roster(conn):
    with conn.cursor() as cur:
        cur.execute("select athlete_id, athlete_name, position from catapult_athletes order by sort_order, athlete_name")
        df = _frame(cur)
    df["position"] = df["position"].fillna("")
    return df


def save_roster(conn, template):
    """Replace the saved athlete list with this one, in this order."""
    with conn:
        with conn.cursor() as cur:
            cur.execute("delete from catapult_athletes")
            for n, row in enumerate(template.itertuples()):
                cur.execute("insert into catapult_athletes (athlete_id, athlete_name, position, sort_order) "
                            "values (%s, %s, %s, %s)", (row[1], row[2], row[3], n))


# ============================================================================
# THE PAGE
# ============================================================================
def roster_uploader(conn, key, replace):
    """Upload your Catapult athlete file and save it. Returns True once saved."""
    box = st.file_uploader("Your Catapult athlete thresholds file (CSV)", type=["csv", "txt"], key=f"{key}_file",
                           help="The same file you import into Catapult: Athlete ID, Athlete Name, Position, Total "
                                "Distance, High Speed Distance. Any numbers already in it are ignored.")
    if box is None:
        return False
    try:
        template = read_template(box.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        return False
    st.success(f"Read {len(template)} athletes: " + ", ".join(template["Athlete Name"].head(4)) +
               (f" and {len(template) - 4} more." if len(template) > 4 else "."))
    sure = st.checkbox("Replace the saved list with this one", key=f"{key}_sure") if replace else True
    if st.button("Save this athlete list", key=f"{key}_save"):
        if not sure:
            st.warning("Tick the box first, then press Save.")
            return False
        save_roster(conn, template)
        st.session_state["flash"] = f"Saved {len(template)} athletes."
        return True
    return False


def main():
    st.set_page_config(page_title="Top-Up Thresholds", layout="wide")
    st.markdown(f"""
    <style>
        .stApp {{ background-color: {WHITE}; }}
        #MainMenu, footer {{visibility: hidden;}}
        h1, h2, h3 {{ color: {NAVY}; }}
    </style>
    """, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="background-color:{NAVY}; border-bottom:5px solid {GOLD}; padding:16px 24px;
                    margin-bottom:20px; color:{WHITE}; display:flex; align-items:center;
                    justify-content:space-between;">
            <div style="font-size:28px; font-weight:800; letter-spacing:1px; color:{WHITE};">TOP-UP THRESHOLDS</div>
            <div style="font-size:11px; opacity:0.85; text-align:right; color:{WHITE}; white-space:nowrap;">
                last loaded {dt.datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))

    try:
        conn = connect()
        ensure_roster_table(conn)
    except Exception as exc:
        st.error(f"Couldn't connect to Supabase: {exc}")
        st.info("Check the [supabase] db_url secret.")
        st.stop()

    try:
        roster = load_roster(conn)
        if roster.empty:
            st.info("First time here: upload your Catapult athlete thresholds file once and press Save. "
                    "The page remembers the list (IDs, names and positions exactly as Catapult has them).")
            if roster_uploader(conn, "first", replace=False):
                st.rerun()
            st.stop()

        try:
            sessions = load_sessions()
        except Exception as exc:
            st.error(f"Couldn't load the GPS data from Supabase: {exc}")
            st.stop()

        today = today_uk()
        weeks = available_weeks(sessions, today)
        if not weeks:
            st.warning("No in-season sessions found in the GPS data yet.")
            st.stop()
        newest = latest_week(sessions, today)

        if st.button("Refresh data now", key="refresh"):
            load_sessions.clear()
            st.rerun()
        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            labels = {f"Week {w}" + (" (latest)" if w == newest else ""): w for w in weeks}
            week = labels[st.selectbox("Week", list(labels), key="week")]
        with c2:
            fit_only = st.checkbox("Fit players only", value=True, key="fit",
                                   help="Leaves out sessions where the player was recorded as injured, modified or "
                                        "international. A session with no status recorded counts.")
        with c3:
            mode = st.radio("Numbers to put in the CSV", [MODE_STILL, MODE_AVERAGE], key="mode")

        summary = week_summary(sessions, week, today, fit_only=fit_only)
        table = build_table(roster, summary, mode)

        # ------------------------------------------------------------ the CSV
        csv_bytes = build_csv(table)
        filled = int(((table["csv_total_distance"].notna()) | (table["csv_high_speed"].notna())).sum())
        st.download_button("Download CSV for Catapult", data=csv_bytes, file_name=f"athlete_thresholds_week_{week}.csv",
                           mime="text/csv", type="primary", key="download")
        st.caption(f"Week {week}. {filled} of {len(table)} athletes have a number in the file; the rest are blank, "
                   f"as in your Catapult file (goalkeepers, players already at their average, or no data).")

        # ------------------------------------------------------------ the numbers behind it
        def whole(series):
            return [None if pd.isna(v) else int(round(v)) for v in series]
        shown = pd.DataFrame({
            "Athlete": table["athlete_name"], "Position": table["position"],
            "Sessions this week": table["sessions"], "Earlier weeks used": table["weeks_used"],
            "Distance: average week": whole(table["avg_td"]), "Distance: so far": whole(table["so_far_td"]),
            "Distance: still to do": whole(table["remaining_td"]),
            "HSR: average week": whole(table["avg_hsr"]), "HSR: so far": whole(table["so_far_hsr"]),
            "HSR: still to do": whole(table["remaining_hsr"]),
            "Note": table["note"],
        })
        st.dataframe(shown, width="stretch", hide_index=True, height=min(900, 38 * (len(shown) + 1) + 3))
        st.caption("Average week = the average of the player's own weekly totals over earlier weeks (full weeks only, "
                   "Fit players only, SESSION rows, week 19 test data left out). High speed running = velocity band 4 + 5 "
                   "distance. Metres, per player.")

        # ------------------------------------------------------------ so nothing is silently missing
        unmatched = [n for n, note in zip(table["athlete_name"], table["note"]) if note.startswith("No Fit session")]
        if unmatched:
            st.caption("No data this week for: " + "; ".join(unmatched) + ". If someone should have data, their name may "
                       "be spelled differently in the GPS data than in your Catapult file.")
        in_file = {person_key(n) for n in table["athlete_name"]}
        extra = sorted({str(p) for k, p in zip(summary.index, summary["player"]) if k not in in_file}, key=str.casefold)
        if extra:
            st.caption("In this week's GPS data but not in your athlete file (so not in the CSV): " + ", ".join(extra))

        with st.expander("Preview of the CSV exactly as it will be downloaded"):
            st.code(csv_bytes.decode("utf-8"), language=None)
        with st.expander("Replace the saved athlete list (when your squad changes)"):
            if roster_uploader(conn, "replace", replace=True):
                st.rerun()
    finally:
        conn.close()


if __name__ == "__main__":       # Streamlit runs the file this way; importing it (for checks) does not draw the page
    main()
