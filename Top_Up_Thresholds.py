"""
Top-Up Thresholds -- ONE file, reads straight from your Dropbox GPS file. Nothing to upload.

Works out what each player still needs ON MATCH DAY to reach their AVERAGE WEEK for total
distance and high speed running, and produces the CSV for you in exactly the layout of your
Catapult athlete thresholds file, ready to import:

    Athlete ID, Athlete Name, Position, Total Distance, High Speed Distance

Your athletes (Catapult ID, name and position) are built into this file (the ROSTER list below),
and each one is matched by name to the same person in your Dropbox GPS file. When the squad
changes, edit that list.

How it decides
  * The cut-off is the most recent MD-1 day in the GPS file (found by itself; you can pick an
    earlier one). Everything up to and including MD-1 counts as done. Match day and anything
    after it does not. The week is the week that MD-1 is in.
  * A player's "average week" is the average of their own weekly totals over the earlier weeks,
    using the same rules as your Power BI weekly report: SESSION rows only, in-season weeks only
    (week 1 up), week 19's test data left out, and only weeks where that player took part in every
    session the squad had (a part-week would drag the average down). If your Squad Availability
    file is set up, sessions where a player was recorded as injured, modified or international
    are left out too.
  * "Still to do" = average week minus what they'd done by MD-1 (blank if they're already there).
  * High speed running = velocity band 4 + band 5 distance, as everywhere else in your reports.

Needs the [dropbox] secrets your other pages already use (refresh_token, app_key, app_secret and
gps_path). availability_path is optional: if it's there, the Fit-players-only rule is applied.
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
EXCLUDE_WEEKS = [19]                 # test data weeks, left out of everyone's history (as in the Power BI weekly card)
SKIP_POSITIONS_CONTAINING = "keeper"   # goalkeepers get no thresholds (their rows stay in the file, blank)
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


# ============================================================================
# NAMES, DATES AND THE CSV
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
    """The CSV in your Catapult layout: the same five columns in the same order, one row per athlete in the order
    of your list. Names with a comma in them (Ale, Asmita) are put in quotes, as Catapult does."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(OUT_COLUMNS)
    for row in table.itertuples():
        writer.writerow([row.athlete_id, row.athlete_name, row.position,
                         _cell(row.csv_total_distance), _cell(row.csv_high_speed)])
    return buffer.getvalue().encode("utf-8")


# ============================================================================
# THE GPS FILE -> ONE ROW PER SESSION
# ============================================================================
def session_rows(gps):
    """From the raw GPS sheet: one row per SESSION row (the whole-session figures). High speed running = velocity
    band 4 + band 5 distance (blank only if both are blank). Returns (rows, number of rows with an unreadable date)."""
    d = gps.copy()
    parsed = read_dates(d["Date"])
    unreadable = int(parsed.isna().sum() - d["Date"].isna().sum())
    d["session_date"] = [x.date() if pd.notna(x) else None for x in parsed]
    d = d[d["Period Name"].astype(str).str.strip().str.casefold() == "session"]
    d = d[d["Player Name"].notna() & d["session_date"].notna()]
    band4 = pd.to_numeric(d["Velocity Band 4 Total Distance"], errors="coerce")
    band5 = pd.to_numeric(d["Velocity Band 5 Total Distance"], errors="coerce")
    hsr = band4.fillna(0) + band5.fillna(0)
    hsr[band4.isna() & band5.isna()] = float("nan")
    rows = pd.DataFrame({
        "player": d["Player Name"].astype(str).str.strip(), "session_date": d["session_date"],
        "week": pd.to_numeric(d["Week Number"], errors="coerce"), "day": d["Day"],
        "total_distance": pd.to_numeric(d["Total Distance"], errors="coerce"), "hsr": hsr,
    }).reset_index(drop=True)
    return rows, unreadable


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
def _fit_rows(d):
    status = d["status"].astype("string").str.strip().str.lower()
    return d[status.isna() | (status == "") | (status == "fit")]       # no status recorded counts as available


def weekly_totals(rows, through, fit_only=True):
    """One row per player per week: how many SESSIONs, and the total distance and high speed distance,
    counting sessions up to and including the day `through`."""
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    d = d[pd.Series([x is not None and x <= through for x in d["session_date"]], index=d.index, dtype=bool)]
    d["week"] = pd.to_numeric(d["week"], errors="coerce")
    d["total_distance"] = pd.to_numeric(d["total_distance"], errors="coerce")
    d["hsr"] = pd.to_numeric(d["hsr"], errors="coerce")
    d = d.dropna(subset=["player", "week", "total_distance"])
    if fit_only:
        d = _fit_rows(d)
    d["key"] = d["player"].map(resolve_key)
    g = d.groupby(["key", "week"])
    weekly = pd.DataFrame({
        "player": g["player"].first(), "sessions": g.size(),
        "td": g["total_distance"].sum(), "hsr": g["hsr"].sum(min_count=1),
    }).reset_index()
    weekly["squad_max_sessions"] = weekly.groupby("week")["sessions"].transform("max")
    weekly["full_week"] = weekly["sessions"] == weekly["squad_max_sessions"]
    return weekly


def _is_md_minus_one(label):
    """True for MD-1 however it's been typed (md-1, MD -1, ' MD-1 ')."""
    return re.sub(r"\s+", "", str(label or "")).upper() == "MD-1"


def md_minus_one_dates(rows, today):
    """Every MD-1 day in the data up to today, newest first."""
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    d = d[d["day"].map(_is_md_minus_one)]
    return sorted({x for x in d["session_date"] if x is not None and x <= today}, reverse=True)


def week_of(rows, day):
    """The GPS week number of a day (the most common one, if the rows that day disagree), or None."""
    d = rows.copy()
    d["session_date"] = pd.to_datetime(d["session_date"]).dt.date
    weeks = pd.to_numeric(d.loc[d["session_date"] == day, "week"], errors="coerce").dropna()
    return None if weeks.empty else int(weeks.mode().min())


def latest_session_day(rows, today):
    """The most recent day with a session, up to today, or None."""
    days = [x for x in pd.to_datetime(rows["session_date"]).dt.date if x is not None and x <= today]
    return max(days) if days else None


def week_summary(rows, week, through, exclude_weeks=EXCLUDE_WEEKS, fit_only=True):
    """Per player (keyed by person_key): their average week, this week's total up to and including the day
    `through` (MD-1), and what's still to do."""
    weekly = weekly_totals(rows, through, fit_only=fit_only)
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
    """One row per athlete in your list's order: what goes in the CSV, plus the numbers behind it and a note."""
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
            rows.append({**base, "note": "No Fit session this week up to MD-1 (or name not found in the GPS data)"})
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
            note = "Needs this on match day"
        else:
            note = "Average week"
        rows.append({**base, "note": note})
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


def read_table(content, path, wanted):
    """Read only the columns we need from an Excel (or CSV) file, tolerating stray spaces in the headings."""
    pick = lambda column: str(column).strip() in wanted
    if str(path).lower().endswith((".csv", ".txt")):
        df = pd.read_csv(io.BytesIO(content), usecols=pick)
    else:
        df = pd.read_excel(io.BytesIO(content), usecols=pick)
    df.columns = [str(c).strip() for c in df.columns]
    return df


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading the GPS file from Dropbox...")
def load_sessions():
    path = st.secrets["dropbox"]["gps_path"]
    _, response = dropbox_client().files_download(path)
    gps = read_table(response.content, path, GPS_COLUMNS)
    missing = [c for c in GPS_COLUMNS if c not in gps.columns]
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

    if st.button("Refresh data now", key="refresh"):
        load_sessions.clear()
        load_availability.clear()
        st.rerun()

    try:
        sessions, unreadable = load_sessions()
    except Exception as exc:
        st.error(f"Couldn't load the GPS file from Dropbox: {exc}")
        st.info("Check the [dropbox] section of your secrets has gps_path, and that the GPS file is where that path says.")
        st.stop()
    availability = None
    try:
        availability = load_availability()
    except Exception as exc:
        st.warning(f"Couldn't read the Squad Availability file ({exc}), so injured and modified players are NOT being "
                   f"left out. Check availability_path in your secrets.")
    sessions = attach_status(sessions, availability)

    today = today_uk()
    if sessions.empty:
        st.warning("No sessions found in the GPS file yet.")
        st.stop()
    roster = roster_frame()

    c1, c2, c3 = st.columns([3, 2, 3])
    with c1:
        # The cut-off is the most recent MD-1: everything up to and including it counts as done.
        cut_days = md_minus_one_dates(sessions, today)
        if cut_days:
            labels = {f"{d:%a %d/%m/%Y} (MD-1), week {week_of(sessions, d)}": d for d in cut_days}
            cutoff = labels[st.selectbox("Counted up to and including", list(labels), key="cutoff")]
        else:
            st.warning("No MD-1 day found in the GPS file, so choose the last day to count instead.")
            fallback = latest_session_day(sessions, today) or today
            cutoff = st.date_input("Last day to count", value=fallback, max_value=today, key="cutoff_date")
    week = week_of(sessions, cutoff)
    if week is None:
        st.warning(f"There are no sessions on {cutoff:%d/%m/%Y}, so there's nothing to work from.")
        st.stop()
    with c2:
        if availability is not None:
            fit_only = st.checkbox("Fit players only", value=True, key="fit",
                                   help="Leaves out sessions where the player was recorded as injured, modified or "
                                        "international. A day with no status recorded counts.")
        else:
            fit_only = False
            st.caption("Injured and modified players aren't being left out, because there's no availability_path in "
                       "your secrets.")
    with c3:
        mode = st.radio("Numbers to put in the CSV", [MODE_STILL, MODE_AVERAGE], key="mode")

    summary = week_summary(sessions, week, cutoff, fit_only=fit_only)
    table = build_table(roster, summary, mode)

    # ------------------------------------------------------------ the CSV
    csv_bytes = build_csv(table)
    filled = int(((table["csv_total_distance"].notna()) | (table["csv_high_speed"].notna())).sum())
    st.download_button("Download CSV for Catapult", data=csv_bytes, file_name=f"athlete_thresholds_week_{week}.csv",
                       mime="text/csv", type="primary", key="download")
    st.caption(f"Week {week}, counted up to and including {cutoff:%A %d/%m/%Y}; match day and anything after it are not "
               f"counted. {filled} of {len(table)} athletes have a number in the file; the rest are blank, as in your "
               f"Catapult file (goalkeepers, players already at their average, or no data)."
               + (" This week is pre-season, so there is no earlier in-season week to average." if week <= 0 else ""))

    # ------------------------------------------------------------ the numbers behind it
    def whole(series):
        return [None if pd.isna(v) else int(round(v)) for v in series]
    shown = pd.DataFrame({
        "Athlete": table["athlete_name"], "Position": table["position"],
        "Sessions counted": table["sessions"], "Earlier weeks used": table["weeks_used"],
        "Distance: average week": whole(table["avg_td"]), "Distance: so far": whole(table["so_far_td"]),
        "Distance: still to do": whole(table["remaining_td"]),
        "HSR: average week": whole(table["avg_hsr"]), "HSR: so far": whole(table["so_far_hsr"]),
        "HSR: still to do": whole(table["remaining_hsr"]),
        "Note": table["note"],
    })
    st.dataframe(shown, width="stretch", hide_index=True, height=min(900, 38 * (len(shown) + 1) + 3))
    st.caption("So far = what the player had done by the cut-off day. Average week = the average of the player's "
               "own weekly totals over earlier weeks (full weeks only, SESSION rows, week 19 test data left out). "
               "Still to do = average week minus so far. High speed running = velocity band 4 + 5 distance. "
               "Metres, per player.")

    # ------------------------------------------------------------ so nothing is silently missing
    unmatched = [n for n, note in zip(table["athlete_name"], table["note"]) if note.startswith("No Fit session")]
    if unmatched:
        st.caption("No sessions up to the cut-off for: " + "; ".join(unmatched) + ". If someone should have data, their "
                   "name may be spelt differently in the GPS file. Add it to NAME_ALIASES at the top of this file.")
    in_list = {person_key(n) for n in table["athlete_name"]}
    extra = sorted({str(p) for k, p in zip(summary.index, summary["player"]) if k not in in_list}, key=str.casefold)
    if extra:
        st.caption("In the GPS file up to the cut-off but not in your athlete list (so not in the CSV): " + ", ".join(extra))
    if unreadable:
        st.caption(f"{unreadable} GPS row(s) had a date that couldn't be read and were skipped.")

    with st.expander("Preview of the CSV exactly as it will be downloaded"):
        st.code(csv_bytes.decode("utf-8"), language=None)


if __name__ == "__main__":       # Streamlit runs the file this way; importing it (for checks) does not draw the page
    main()
