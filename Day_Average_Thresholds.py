"""
Day Average Thresholds -- ONE file, reads straight from your Dropbox GPS file. Nothing to upload.

For one type of training day (Activation, Extensive, Intensive or MD-1) it works out each player's AVERAGE for five
measures, counting only the sessions where that player was marked FIT, and gives you a CSV in exactly the layout of
your Catapult athlete thresholds file, ready to import:

    Athlete ID, Athlete Name, Position, High Speed Distance, Total Distance,
    Acceleration Bands 1-3 Efforts, Deceleration Bands 1-3 Efforts, Very High Speed Distance

Three exports to choose from: the day average, the average plus one standard deviation, or the average minus one
standard deviation (a normal-for-this-player range to show against in Catapult).

The measures
  * High Speed Distance      = velocity band 4 + band 5 distance
  * Total Distance
  * Acceleration / Deceleration Bands 1-3 Efforts
  * Very High Speed Distance = velocity band 6 DISTANCE. Your GPS file needs that column. If it doesn't have it
    (your database only keeps the band 6 effort COUNT), that one column is left blank and the page says so.

The rules
  * SESSION rows only (the whole-session figures), one per player per day, in-season weeks only (week 1 up),
    week 19's test data left out, and nothing dated after today.
  * "Fit" comes from your Squad Availability file (availability_path in your secrets). A day with no status
    recorded is left out unless you tick the box to count it.
  * The standard deviation is the sample one (n - 1). A player needs the minimum number of sessions you set
    (3 to start with), because an average of one or two sessions says very little.

Your athletes (Catapult ID, name and position) are built into this file (the ROSTER list below). Each is matched by
name to the same person in the GPS file. When the squad changes, edit that list.

Needs the [dropbox] secrets your other pages already use (refresh_token, app_key, app_secret and gps_path),
plus availability_path so it knows who was Fit.
"""
import csv
import datetime as dt
import io
import re
import unicodedata
from zoneinfo import ZoneInfo

import dropbox
import pandas as pd
import streamlit as st

try:
    from theme import NAVY, GOLD, WHITE          # your app's colours, if theme.py is next to this file
except ImportError:
    NAVY, GOLD, WHITE = "#0a2540", "#fdbe11", "#ffffff"

# ============================================================================
# SETTINGS
# ============================================================================
DAY_TYPES = ["Activation", "Extensive", "Intensive", "MD-1"]     # the days you can export, as written in the GPS file's Day column
EXCLUDE_WEEKS = [19]                 # test data weeks, always left out (as in your Power BI weekly card)
DEFAULT_MIN_SESSIONS = 3             # fewer Fit sessions than this and a player is left blank
CACHE_TTL_SECONDS = 60

# If a player's name in the GPS file is spelt differently from your Catapult list, say so here, as
#     "name as it appears in the GPS file": "name as it appears below (Surname, First)",
# e.g.  "Liv McLoughlin": "McLoughlin, Olivia",
# The page names anyone it can't match, so you'll know when this is needed.
NAME_ALIASES = {
}

# Your Catapult athletes, exactly as in your athlete thresholds file: ID, name, position.
ROSTER = [
    ("c2dbd597-beee-4e56-a5b3-f8c5ddc7bfe6", "Ale, Asmita", "Full Back"),
    ("e18b89c9-ae9a-4722-8032-b9fb73125948", "Baker, Phoebe", "Goal Keeper"),
    ("b0b57e9c-baa6-46e7-a626-df4cdfcfb8cc", "Bance, Libby", "Midfielder"),
    ("06d2f8ac-83c6-4e8b-899b-95beabc7f3ea", "Binning, Sareet", "Central Midfielder"),
    ("a967aa00-c9e2-41ce-829d-10c0ef99a119", "Boureille, Celeste", "Central Midfielder"),
    ("b2c02aa4-13a4-4eb3-831b-0c49a50d5eb4", "Bowen, Ffion", "Attacker"),
    ("80abebc4-1550-4f4e-bccb-f9fc5796c849", "Clark, Liv", "Goal Keeper"),
    ("2c104015-d7cd-4fff-b3cb-f80d4f2b9ca9", "Collinson, Ella", "Central Midfielder"),
    ("518c2f73-7f63-4f43-8fb9-41fb56f07c75", "Dennis, Araya", "Attacker"),
    ("9b2a5fdf-5850-476f-bcca-b5891f44e86e", "Draper, Denny", "Striker"),
    ("21b1dd21-58b2-4597-922d-84a33bd12648", "Eddie, Leah", "Defender"),
    ("80ad1ce4-78c3-4f30-b5fe-f1593798c3d6", "Goodwin, Missy", "Attacker"),
    ("b643e967-d913-4d51-ae64-b190ffaaa266", "Graham, Harper", "Attacker"),
    ("0eb7db1b-0635-467b-8799-adff072e8d5b", "Greatorex, Alicia", "Central Midfielder"),
    ("caf830d3-3d34-4512-ad3c-13e6f73d1bca", "Hollis, Savanah", "Attacker"),
    ("d400afa6-b4ee-4d04-b78b-6cca267fa74c", "James, Daisy", "Midfielder"),
    ("a304430c-86d7-4559-a618-b4011d9df4e7", "Jansson, Emma", "Central Midfielder"),
    ("0a509c5f-5237-4bfd-adb8-9c83f6ac7fbd", "Keane, Katie", "Goal Keeper"),
    ("1a49d498-7846-434d-80e9-c5ecfbdc934f", "King, Beau", "Attacker"),
    ("fea32bc0-18eb-43ce-9c89-a17d616cd132", "Kirk, Hannah", "Goal Keeper"),
    ("8272c39b-01da-4826-96e1-efcaea93f0dd", "Lehmann, Alisha", "Attacker"),
    ("e0be6c39-f32c-4299-bef5-09ec84114cca", "Mayling, Sarah", "Full Back"),
    ("81db2ce6-a7b2-45b7-8d6d-ddfcc6e4eb68", "McLoughlin, Olivia", "Central Midfielder"),
    ("767e2c5f-cc15-4323-b99e-d76558d6de06", "Nyström, Paulina", "Attacker"),
    ("7f751020-9f64-46b5-b54c-0d42548dc8a8", "Palmer, Izzy", "Midfielder"),
    ("d6df271b-f62b-4524-8f12-9c86a6a964de", "Payne, Heather", "Full Back"),
    ("db4c640a-98f8-4ffb-96f4-25782efca493", "Pelgander, Emilia", "Central Midfielder"),
    ("f2cc42eb-425a-4e68-97ba-6e4577ab6d19", "Pritchard, Poppy", "Striker"),
    ("f7589966-78fe-4d6e-87ae-88da7aab9ba5", "Sherwood, Simone", "Central Midfielder"),
    ("0396f46c-d3ec-4f91-b0cc-e1e832903a12", "Shirley, Meg", "Attacking Midfielder"),
    ("ca50d71a-e3a9-4b67-a91d-07a01d808295", "Stapleton, Jessie", "Defender"),
    ("c907a1cf-1cb8-475e-b3de-0c848783b37c", "Tierney, Samantha", "Central Midfielder"),
    ("66d0e5f3-d8e9-45d1-9a09-95a81f037230", "Ziu, Jessica", "Midfielder"),
]

OUT_COLUMNS = ["Athlete ID", "Athlete Name", "Position", "Total Distance", "High Speed Distance"]
GPS_COLUMNS = ["Player Name", "Date", "Period Name", "Week Number", "Day", "Total Distance",
               "Velocity Band 4 Total Distance", "Velocity Band 5 Total Distance"]
MODE_STILL = "What they still need on match day (to reach their average week)"
MODE_AVERAGE = "Their full average week"

# What goes in the CSV, in this order: (column name, the GPS file column(s) it is added up from)
METRICS = [
    ("High Speed Distance", ("Velocity Band 4 Total Distance", "Velocity Band 5 Total Distance")),
    ("Total Distance", ("Total Distance",)),
    ("Acceleration Bands 1-3 Efforts", ("Acceleration B1-3 Total Efforts (Gen 2)",)),
    ("Deceleration Bands 1-3 Efforts", ("Deceleration B1-3 Total Efforts (Gen 2)",)),
    ("Very High Speed Distance", ("Velocity Band 6 Total Distance",)),
]
METRIC_NAMES = [name for name, _ in METRICS]
OUT_COLUMNS = ["Athlete ID", "Athlete Name", "Position"] + METRIC_NAMES
REQUIRED_COLUMNS = ["Player Name", "Date", "Period Name", "Week Number", "Day"]
GPS_COLUMNS = REQUIRED_COLUMNS + [part for _, parts in METRICS for part in parts]
BAND6_NAME = "Velocity Band 6 Total Distance"

MODE_AVERAGE = "Day average"
MODE_PLUS = "Day average + 1 standard deviation"
MODE_MINUS = "Day average - 1 standard deviation"
MODE_SIGN = {MODE_AVERAGE: 0, MODE_PLUS: 1, MODE_MINUS: -1}
MODE_FILE = {MODE_AVERAGE: "average", MODE_PLUS: "average_plus_1sd", MODE_MINUS: "average_minus_1sd"}


# ============================================================================
# NAMES, DATES AND THE CSV  (the same tested pieces as the Top-Up page)
# ============================================================================
def roster_frame():
    return pd.DataFrame(ROSTER, columns=["athlete_id", "athlete_name", "position"])


def person_key(name):
    """What 'Ale, Asmita' (Catapult's way) and 'Asmita Ale' (your GPS file's way) have in common. Ignores capitals,
    extra spaces and accents, so 'Nystr\u00f6m' and 'Nystrom' match."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    if "," in text:
        last, first = (part.strip() for part in text.split(",", 1))
        text = f"{first} {last}"
    return re.sub(r"\s+", " ", text).strip()


def resolve_key(name):
    """person_key, after applying any spelling fixes in NAME_ALIASES."""
    key = person_key(name)
    for gps_name, roster_name in NAME_ALIASES.items():
        if person_key(gps_name) == key:
            return person_key(roster_name)
    return key


_NUMERIC_DATE = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")


def read_dates(series):
    """Real dates stay as they are. Text like 04/10/2026 is read day-first (UK) unless the numbers prove
    otherwise: a second number over 12 can only be the day (10/15/2026), so that one is month-first."""
    def one(value):
        if value is None:
            return pd.NaT
        if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
            return pd.Timestamp(value)
        try:
            if pd.isna(value):
                return pd.NaT
        except (TypeError, ValueError):
            pass
        match = _NUMERIC_DATE.match(str(value))
        if match:
            a, b, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            day, month = (b, a) if (b > 12 >= a) else (a, b)
            try:
                return pd.Timestamp(year, month, day)
            except ValueError:
                return pd.NaT
        return pd.to_datetime(str(value).strip(), errors="coerce")
    return pd.to_datetime(series.map(one))


def _cell(value):
    """A whole number as text, or nothing at all for a blank. (A column of whole numbers with gaps in it turns into
    decimals with 'nan' for the gaps, so 3000 would come out as 3000.0 and a blank as nan.)"""
    if value is None or pd.isna(value):
        return ""
    return str(int(round(float(value))))


def build_csv(table):
    """The CSV in your Catapult layout: the same columns in the same order, one row per athlete in the order of
    your list. Names with a comma in them (Ale, Asmita) are put in quotes, as Catapult does."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(OUT_COLUMNS)
    for row in table.to_dict("records"):
        writer.writerow([row["athlete_id"], row["athlete_name"], row["position"]] + [_cell(row[f"out_{n}"]) for n in METRIC_NAMES])
    return buffer.getvalue().encode("utf-8")


# ============================================================================
# THE GPS FILE -> ONE ROW PER SESSION
# ============================================================================
def is_band6_distance(header):
    """Any column that is band 6 DISTANCE, however it's worded (but not the band 6 effort COUNT)."""
    text = str(header).strip().casefold()
    return "band 6" in text and "distance" in text and "count" not in text and "effort" not in text


def session_rows(gps):
    """From the raw GPS sheet: one row per SESSION row, with the five measures worked out. A measure's figure is blank
    if none of its columns are in the file. Returns (rows, number of unreadable dates, notes about missing columns)."""
    d = gps.copy()
    parsed = read_dates(d["Date"])
    unreadable = int(parsed.isna().sum() - d["Date"].isna().sum())
    d["session_date"] = [x.date() if pd.notna(x) else None for x in parsed]
    d = d[d["Period Name"].astype(str).str.strip().str.casefold() == "session"]
    d = d[d["Player Name"].notna() & d["session_date"].notna()]
    out = pd.DataFrame({
        "player": d["Player Name"].astype(str).str.strip(), "session_date": d["session_date"],
        "week": pd.to_numeric(d["Week Number"], errors="coerce"), "day": d["Day"],
    })
    notes = []
    for name, parts in METRICS:
        present = [p for p in parts if p in d.columns]
        if not present:
            out[name] = float("nan")
            notes.append(f"{name} is blank because the GPS file has no '{parts[0]}' column"
                         + (" (your database only keeps the band 6 effort count, not its distance, so add that distance to your Catapult export)"
                            if name == "Very High Speed Distance" else "") + ".")
            continue
        if len(present) < len(parts):
            missing = [p for p in parts if p not in present]
            notes.append(f"{name} is missing '{missing[0]}' in the GPS file, so it only uses {present[0]}.")
        out[name] = pd.concat([pd.to_numeric(d[p], errors="coerce") for p in present], axis=1).sum(axis=1, min_count=1)
    return out.reset_index(drop=True), unreadable, notes


def attach_status(rows, availability):
    """Add each session's Fit / Injured / Modified status from the Squad Availability file (matched on player and
    day). With no availability file, or no entry for that day, the status stays blank, which counts as available."""
    d = rows.copy()
    d["status"] = None
    if availability is None or availability.empty or d.empty:
        return d
    lookup = {(k, day): status for k, day, status in zip(availability["key"], availability["day"], availability["status"])}
    d["status"] = [lookup.get((resolve_key(p), day)) for p, day in zip(d["player"], d["session_date"])]
    return d


# ============================================================================
# THE CALCULATION
# ============================================================================
def normal_day(label):
    """'Activation', ' activation ', 'MD -1' -> 'ACTIVATION', 'MD-1'."""
    return re.sub(r"\s+", "", str(label or "")).upper()


def available_weeks(rows, today, exclude_weeks=EXCLUDE_WEEKS):
    d = rows[[x is not None and x <= today for x in pd.to_datetime(rows["session_date"]).dt.date]]
    weeks = pd.to_numeric(d["week"], errors="coerce").dropna()
    return sorted({int(w) for w in weeks if w > 0 and w not in exclude_weeks})


def day_stats(rows, day, first_week, last_week, today, leave_out=(), include_no_status=False, exclude_weeks=EXCLUDE_WEEKS):
    """Each player's average and standard deviation of the five measures on one type of day, over their Fit sessions.
    Returns (stats, counts): stats is keyed by person_key with 'player', 'sessions', '<measure>|mean' and '<measure>|sd'."""
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    d = d[[x is not None and x <= today for x in d["session_date"]]]
    d["week"] = pd.to_numeric(d["week"], errors="coerce")
    d = d[(d["week"] > 0) & (d["week"] >= first_week) & (d["week"] <= last_week)
          & ~d["week"].isin(list(exclude_weeks) + list(leave_out))]
    d = d[d["day"].map(normal_day) == normal_day(day)]
    status = d["status"].map(lambda x: "" if x is None or pd.isna(x) else str(x).strip().lower())
    fit = status == "fit"
    blank = status == ""
    counts = {"all": int(len(d)), "fit": int(fit.sum()), "other_status": int((~fit & ~blank).sum()), "no_status": int(blank.sum())}
    kept = d[fit | blank] if include_no_status else d[fit]
    kept = kept.copy()
    counts["used"] = int(len(kept))
    kept["key"] = kept["player"].map(resolve_key)
    g = kept.groupby("key")
    stats = pd.DataFrame({"player": g["player"].first(), "sessions": g.size()})
    if len(kept):
        for name in METRIC_NAMES:
            stats[f"{name}|mean"] = g[name].mean()
            stats[f"{name}|sd"] = g[name].std()                 # sample standard deviation (n - 1); blank for one session
    else:
        for name in METRIC_NAMES:
            stats[f"{name}|mean"] = float("nan")
            stats[f"{name}|sd"] = float("nan")
    return stats, counts


def _whole(value):
    """A positive amount as a whole number, otherwise None (a blank in the file)."""
    if value is None or pd.isna(value):
        return None
    rounded = int(round(float(value)))
    return rounded if rounded > 0 else None


def build_table(roster, stats, sign=0, min_sessions=DEFAULT_MIN_SESSIONS, include_goalkeepers=True):
    """One row per athlete in your list's order: what goes in the CSV (sign 0 = average, +1 or -1 = that many standard
    deviations above or below it), the number of sessions behind it, and a note."""
    rows = []
    for athlete in roster.itertuples():
        key = person_key(athlete.athlete_name)
        position = athlete.position or ""
        base = {"athlete_id": athlete.athlete_id, "athlete_name": athlete.athlete_name, "position": position, "sessions": None}
        for name in METRIC_NAMES:
            base[f"out_{name}"] = None
            base[f"mean_{name}"] = None
            base[f"sd_{name}"] = None
        if "keeper" in position.casefold() and not include_goalkeepers:
            rows.append({**base, "note": "Goalkeeper - left blank"})
            continue
        if key not in stats.index:
            rows.append({**base, "note": "No Fit sessions on this day (or name not found in the GPS data)"})
            continue
        s = stats.loc[key]
        base["sessions"] = int(s["sessions"])
        for name in METRIC_NAMES:
            base[f"mean_{name}"], base[f"sd_{name}"] = s[f"{name}|mean"], s[f"{name}|sd"]
        if int(s["sessions"]) < min_sessions:
            rows.append({**base, "note": f"Only {int(s['sessions'])} Fit session(s): needs {min_sessions}"})
            continue
        for name in METRIC_NAMES:
            mean, sd = s[f"{name}|mean"], s[f"{name}|sd"]
            if sign != 0 and pd.isna(sd):
                continue                                      # one session has no standard deviation
            if pd.isna(mean):
                continue
            base[f"out_{name}"] = _whole(mean if sign == 0 else mean + sign * sd)     # the plain average never needs a standard deviation
        no_sd = sign != 0 and int(s["sessions"]) < 2
        rows.append({**base, "note": "Needs 2+ sessions for a standard deviation" if no_sd else "OK"})
    return pd.DataFrame(rows)


# ============================================================================
# DROPBOX (the same connection your other pages use)
# ============================================================================
def today_uk():
    """Today's date from the computer's clock, in UK time."""
    return dt.datetime.now(ZoneInfo("Europe/London")).date()


def dropbox_client():
    cfg = st.secrets["dropbox"]
    if "refresh_token" in cfg:
        dbx = dropbox.Dropbox(oauth2_refresh_token=cfg["refresh_token"], app_key=cfg["app_key"],
                              app_secret=cfg["app_secret"])
    else:
        dbx = dropbox.Dropbox(cfg["access_token"])
    if cfg.get("team_space", True):          # files in a Business "team space" need the team's root folder
        account = dbx.users_get_current_account()
        dbx = dbx.with_path_root(dropbox.common.PathRoot.namespace_id(account.root_info.root_namespace_id))
    return dbx


def read_gps_table(content, path):
    """Read only the columns we need from the GPS workbook. The band 6 distance column is found by what it is, not by
    its exact wording, and is called 'Velocity Band 6 Total Distance' from here on."""
    wanted = set(GPS_COLUMNS)
    keep = lambda column: str(column).strip() in wanted or is_band6_distance(column)
    if str(path).lower().endswith((".csv", ".txt")):
        df = pd.read_csv(io.BytesIO(content), usecols=keep)
    else:
        df = pd.read_excel(io.BytesIO(content), usecols=keep)
    df.columns = [str(c).strip() for c in df.columns]
    if BAND6_NAME not in df.columns:
        found = [c for c in df.columns if is_band6_distance(c)]
        if found:
            df = df.rename(columns={found[0]: BAND6_NAME})
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading the GPS file from Dropbox...")
def load_sessions():
    path = st.secrets["dropbox"]["gps_path"]
    _, response = dropbox_client().files_download(path)
    gps = read_gps_table(response.content, path)
    missing = [c for c in REQUIRED_COLUMNS if c not in gps.columns]
    if missing:
        raise ValueError("the GPS file is missing these columns: " + ", ".join(missing))
    return session_rows(gps)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading the squad availability from Dropbox...")
def load_availability():
    """Fit / Injured / Modified per player per day from your Squad Availability file, or None if no path is set up."""
    cfg = st.secrets["dropbox"]
    if "availability_path" not in cfg:
        return None
    path = cfg["availability_path"]
    _, response = dropbox_client().files_download(path)
    raw = pd.read_excel(io.BytesIO(response.content)) if not str(path).lower().endswith(".csv") else pd.read_csv(io.BytesIO(response.content))
    raw.columns = [str(c).strip() for c in raw.columns]
    status_column = next((c for c in raw.columns if c.casefold() in ("avaliability", "availability", "status")), None)
    if "Name" not in raw.columns or "Date" not in raw.columns or status_column is None:
        raise ValueError("the availability file needs Name, Date and Availability columns")
    days = [x.date() if pd.notna(x) else None for x in read_dates(raw["Date"])]
    out = pd.DataFrame({"key": raw["Name"].map(resolve_key), "day": days, "status": raw[status_column]})
    return out[out["day"].notna() & raw["Name"].notna()].drop_duplicates(["key", "day"], keep="last").reset_index(drop=True)


# ============================================================================
# THE PAGE
# ============================================================================
def main():
    st.set_page_config(page_title="Day Average Thresholds", layout="wide")
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
            <div style="font-size:28px; font-weight:800; letter-spacing:1px; color:{WHITE};">DAY AVERAGE THRESHOLDS</div>
            <div style="font-size:11px; opacity:0.85; text-align:right; color:{WHITE}; white-space:nowrap;">
                last loaded {dt.datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Refresh data now", key="refresh"):
        load_sessions.clear()
        load_availability.clear()
        st.rerun()

    try:
        sessions, unreadable, metric_notes = load_sessions()
    except Exception as exc:
        st.error(f"Couldn't load the GPS file from Dropbox: {exc}")
        st.info("Check the [dropbox] section of your secrets has gps_path, and that the GPS file is where that path says.")
        st.stop()
    availability, availability_problem = None, None
    try:
        availability = load_availability()
    except Exception as exc:
        availability_problem = str(exc)
    fit_known = availability is not None
    if availability_problem:
        st.warning(f"Couldn't read the Squad Availability file ({availability_problem}), so there is no way to tell who was Fit "
                   f"and every session is being counted. Check availability_path in your secrets.")
    elif not fit_known:
        st.warning("There's no availability_path in your secrets, so there is no way to tell who was Fit: every session is "
                   "being counted. Add availability_path (the same line your Squad Availability page uses) to fix that.")
    sessions = attach_status(sessions, availability)

    today = today_uk()
    weeks = available_weeks(sessions, today)
    if not weeks:
        st.warning("No in-season sessions found in the GPS file yet.")
        st.stop()
    roster = roster_frame()

    c1, c2, c3 = st.columns([2, 3, 2])
    with c1:
        day = st.selectbox("Day", DAY_TYPES, key="day")
    with c2:
        mode = st.radio("Export", [MODE_AVERAGE, MODE_PLUS, MODE_MINUS], key="mode")
    with c3:
        min_sessions = st.number_input("Minimum Fit sessions per player", min_value=1, max_value=10,
                                       value=DEFAULT_MIN_SESSIONS, step=1, key="min_sessions",
                                       help="A player with fewer Fit sessions than this on that day is left blank.")
    c4, c5 = st.columns([3, 3])
    with c4:
        if len(weeks) > 1:
            first_week, last_week = st.select_slider("Weeks to include", options=weeks, value=(weeks[0], weeks[-1]), key="weeks")
        else:
            first_week = last_week = weeks[0]
        leave_out = st.multiselect("Also leave out these weeks (e.g. international weeks)", weeks, key="leave_out")
    with c5:
        include_no_status = st.checkbox("Also count days with no status recorded", value=False, key="no_status",
                                        help="By default only sessions marked exactly Fit are counted. A day missing from "
                                             "your Squad Availability file has no status, so it is left out.",
                                        disabled=not fit_known)
        include_goalkeepers = st.checkbox("Include goalkeepers", value=True, key="goalkeepers")

    stats, counts = day_stats(sessions, day, first_week, last_week, today, leave_out=leave_out,
                              include_no_status=include_no_status or not fit_known)
    table = build_table(roster, stats, MODE_SIGN[mode], int(min_sessions), include_goalkeepers)

    # ------------------------------------------------------------ the CSV
    csv_bytes = build_csv(table)
    filled = int(table[[f"out_{n}" for n in METRIC_NAMES]].notna().any(axis=1).sum())
    st.download_button("Download CSV for Catapult", data=csv_bytes,
                       file_name=f"athlete_thresholds_{day.lower()}_{MODE_FILE[mode]}.csv", mime="text/csv", type="primary", key="download")
    st.caption(f"{day}, weeks {first_week} to {last_week}. {filled} of {len(table)} athletes have numbers in the file; "
               f"the rest are blank, as in your Catapult file.")
    st.caption(f"{counts['all']} {day} sessions in those weeks: {counts['used']} counted"
               + (f", {counts['other_status']} left out because the player wasn't Fit (injured, modified, off...)" if counts["other_status"] else "")
               + (f", {counts['no_status']} {'counted' if include_no_status or not fit_known else 'left out'} with no status recorded" if counts["no_status"] else "")
               + ".")
    for note in metric_notes:
        st.warning(note)

    # ------------------------------------------------------------ the numbers behind it
    shown = pd.DataFrame({"Athlete": table["athlete_name"], "Position": table["position"], "Fit sessions": table["sessions"]})
    for name in METRIC_NAMES:
        shown[name] = table[f"out_{name}"]
    shown["Note"] = table["note"]
    st.dataframe(shown, width="stretch", hide_index=True, height=min(900, 38 * (len(shown) + 1) + 3))
    with st.expander("The averages and standard deviations behind these numbers"):
        detail = pd.DataFrame({"Athlete": table["athlete_name"], "Fit sessions": table["sessions"]})
        for name in METRIC_NAMES:
            detail[f"{name}: average"] = pd.to_numeric(table[f"mean_{name}"]).round(1)
            detail[f"{name}: SD"] = pd.to_numeric(table[f"sd_{name}"]).round(1)
        st.dataframe(detail, width="stretch", hide_index=True)
        st.caption("Standard deviation = how much that player's sessions vary around their average (the sample one, n - 1).")

    # ------------------------------------------------------------ so nothing is silently missing
    in_list = {person_key(n) for n in table["athlete_name"]}
    extra = sorted({str(p) for k, p in zip(stats.index, stats["player"]) if k not in in_list}, key=str.casefold)
    if extra:
        st.caption("In the GPS file but not in your athlete list (so not in the CSV): " + ", ".join(extra))
    unmatched = [n for n, note in zip(table["athlete_name"], table["note"]) if note.startswith("No Fit sessions")]
    if unmatched:
        st.caption("No Fit sessions on this day for: " + "; ".join(unmatched) + ". If someone should have some, their name may "
                   "be spelt differently in the GPS file (add it to NAME_ALIASES at the top of this file) or their status "
                   "isn't marked Fit.")
    if unreadable:
        st.caption(f"{unreadable} GPS row(s) had a date that couldn't be read and were skipped.")
    with st.expander("Preview of the CSV exactly as it will be downloaded"):
        st.code(csv_bytes.decode("utf-8"), language=None)


if __name__ == "__main__":       # Streamlit runs the file this way; importing it (for checks) does not draw the page
    main()
