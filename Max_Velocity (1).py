"""
Max Velocity (sprint exposure) -- ONE file. GPS comes from Dropbox, the squad list from Supabase.

For every player on your squad list: days since they last reached 90% of their
max speed, how many times in the last 7 days, and a status (Hasn't been exposed /
Optimal / High volume). It follows the Power BI "Squad Sprint Exposure Table".

  * Days are counted from TODAY'S DATE on the computer (UK time), every time the
    page loads. There is nothing to pick or update.
  * The squad list is the `players` table in Supabase, and ONLY those players appear,
    outfield players only: anyone whose position is "Goalkeeper" is left out. Anyone in
    the GPS file who isn't on the list is left out too (and named at the bottom of the
    page, so a misspelt name can't hide a squad member).
  * A "hit" is a SESSION where the player's top speed was 90%+ of their profile
    max velocity (Maximum Velocity / Profile Max Velocity).

Needs the secrets your other pages already use:
    [dropbox]   refresh_token, app_key, app_secret, and  gps_path = "/Club Data/GPS_Data.xlsx"
    [supabase]  db_url
"""
import datetime as dt
import io
import re
import unicodedata
from html import escape
from zoneinfo import ZoneInfo

import dropbox
import pandas as pd
import psycopg2
import streamlit as st

try:
    from theme import NAVY, GOLD, WHITE          # your app's colours, if theme.py is next to this file
except ImportError:
    NAVY, GOLD, WHITE = "#0a2540", "#fdbe11", "#ffffff"

# ============================================================================
# SETTINGS -- the only things you'd ever want to change
# ============================================================================
THRESHOLD_PCT = 90.0        # % of profile max velocity that counts as a hit
WINDOW_DAYS = 7             # "last 7 days" = today and the six days before it
STALE_DAYS = 7              # this many days since (or more) = "Hasn't been exposed"
HIGH_VOLUME_COUNT = 7       # this many hits (or more) in the window = "High volume"
CACHE_TTL_SECONDS = 60      # how often the page re-reads Dropbox and Supabase

# status: (label, background, text colour) -- the colours from the Power BI measure
STATUS = {
    "nodata": ("No data", "#888780", "#2C2C2A"),
    "under": ("Hasn't been exposed", "#378ADD", "#042C53"),
    "optimal": ("Optimal", "#639922", "#173404"),
    "high": ("High volume", "#E24B4A", "#501313"),
}
BRAND = "#0053a0"
SORT_OPTIONS = ["Player A to Z", "Longest since 90% first", "Most times in the last 7 days"]
TABLE_COLUMNS = ["player", "state", "last_date", "days_since", "pct_reached", "times_in_window", "status"]
GPS_COLUMNS = ["Player Name", "Date", "Period Name", "Maximum Velocity", "Profile Max Velocity"]


# ============================================================================
# DATES AND NAMES
# ============================================================================
def today_uk():
    """Today's date from the computer's clock, in UK time."""
    return dt.datetime.now(ZoneInfo("Europe/London")).date()


def clean_name(name):
    """Tidy a name so the two files match: trim spaces, repair garbled accents, normalise Unicode."""
    text = str(name).strip()
    try:
        text = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return unicodedata.normalize("NFC", text)


def name_key(name):
    """What two spellings of a name have in common: same letters, ignoring capitals and extra spaces."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(name or ""))).strip().casefold()


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


# ============================================================================
# DROPBOX (same connection as your other pages)
# ============================================================================
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


def download_excel(dbx, path):
    _, response = dbx.files_download(path)
    return pd.read_excel(io.BytesIO(response.content))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading GPS data from Dropbox...")
def load_gps():
    dbx = dropbox_client()
    gps = download_excel(dbx, st.secrets["dropbox"]["gps_path"])
    missing = [c for c in GPS_COLUMNS if c not in gps.columns]
    if missing:
        raise ValueError("the GPS file is missing these columns: " + ", ".join(missing))
    return gps[GPS_COLUMNS]


# ============================================================================
# SUPABASE (the squad list: the same `players` table that gives each player a position)
# ============================================================================
SQUAD_SQL = "select player_name, position from players order by player_name"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading the squad list from Supabase...")
def load_squad():
    conn = psycopg2.connect(st.secrets["supabase"]["db_url"])
    try:
        with conn.cursor() as cur:
            cur.execute(SQUAD_SQL)
            return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
    finally:
        conn.close()



# ============================================================================
# THE CALCULATIONS
# ============================================================================
def _listed(squad):
    """Everyone on the players table, with names tidied: the name and position, one row per player."""
    sq = squad[squad["player_name"].notna()].copy()
    sq["player"] = sq["player_name"].map(clean_name)
    sq = sq[~sq["player"].str.casefold().isin(["", "nan", "none"])]
    sq["is_gk"] = sq["position"].fillna("").astype(str).str.strip().str.casefold() == "goalkeeper"
    return sq


def _names(sq):
    names = {}
    for name in sq["player"]:
        names.setdefault(name_key(name), name)
    return sorted(names.values(), key=str.casefold)


def listed_names(squad):
    """Everyone on the players table, goalkeepers included. Used only to tell who is NOT on the list at all."""
    return _names(_listed(squad))


def squad_names(squad):
    """The squad list shown on the page: the players table, outfield players only. A goalkeeper is anyone whose
    position is "Goalkeeper"."""
    sq = _listed(squad)
    return _names(sq[~sq["is_gk"]])


def session_rows(gps):
    """One row per player per SESSION row, with pct = Maximum Velocity / Profile Max Velocity x 100.
    A match day with no Session row (only 1st and 2nd half) gets one row: the higher of the two halves.
    Rows with no speed, or no (or zero) profile max, can't be judged and are left out.
    Returns (rows, number of rows whose date couldn't be read)."""
    d = gps.copy()
    d["player"] = d["Player Name"].map(lambda n: clean_name(n) if pd.notna(n) else None)
    parsed = read_dates(d["Date"])
    unreadable = int(parsed.isna().sum() - d["Date"].isna().sum())
    d["session_date"] = [x.date() if pd.notna(x) else None for x in parsed]
    speed = pd.to_numeric(d["Maximum Velocity"], errors="coerce")
    profile = pd.to_numeric(d["Profile Max Velocity"], errors="coerce")
    d["pct"] = (speed / profile * 100).where(profile > 0)
    d["period"] = d["Period Name"].astype(str).str.strip().str.lower()
    d = d.dropna(subset=["player", "session_date", "pct"])
    d["key"] = d["player"].map(name_key)

    sessions = d[d["period"] == "session"]
    halves = d[d["period"].isin(["1st half", "2nd half"])]
    have = set(zip(sessions["key"], sessions["session_date"]))
    if halves.empty:
        from_halves = pd.DataFrame(columns=["key", "session_date", "player", "pct"])
    else:
        from_halves = halves.groupby(["key", "session_date"], as_index=False).agg(player=("player", "first"), pct=("pct", "max"))
        keep = [(k, day) not in have for k, day in zip(from_halves["key"], from_halves["session_date"])]
        from_halves = from_halves[pd.Series(keep, index=from_halves.index, dtype=bool)]
    rows = pd.concat([sessions[["player", "session_date", "pct"]], from_halves[["player", "session_date", "pct"]]],
                     ignore_index=True)
    return rows, unreadable


def exposure_status(state, days_since, hits_in_window):
    """Which status a player gets. The order matters, as in the Power BI measure: 'never' and 7+ days since come
    before 'high volume', so someone who hasn't sprinted for a week is never called high volume."""
    if state == "nodata":
        return "nodata"
    if state == "never" or days_since >= STALE_DAYS:
        return "under"
    if hits_in_window >= HIGH_VOLUME_COUNT:
        return "high"
    return "optimal"


def build_table(names, rows, today):
    """One row per squad player. state: 'hit' (has reached the threshold), 'never' (has speed data but never
    reached it), 'nodata' (no usable speed data at all)."""
    d = rows.copy()
    days = [x.date() if pd.notna(x) else None for x in pd.to_datetime(d["session_date"])]
    d["session_date"] = days
    d = d[pd.Series([x is not None and x <= today for x in days], index=d.index, dtype=bool)]   # not future-dated
    d["key"] = d["player"].map(name_key)
    has_data = set(d["key"])
    hits = d[d["pct"] >= THRESHOLD_PCT]
    window_start = today - dt.timedelta(days=WINDOW_DAYS - 1)
    in_window = hits[hits["session_date"] >= window_start].groupby("key").size()     # hit ROWS, as the Power BI count does
    last_date = hits.groupby("key")["session_date"].max()

    out = []
    for name in names:
        key = name_key(name)
        if key in last_date.index:
            last = last_date[key]
            best = hits[(hits["key"] == key) & (hits["session_date"] == last)]["pct"].max()
            days, count = (today - last).days, int(in_window.get(key, 0))
            out.append({"player": name, "state": "hit", "last_date": last, "days_since": days, "pct_reached": float(best),
                        "times_in_window": count, "status": exposure_status("hit", days, count)})
        else:
            state = "never" if key in has_data else "nodata"
            out.append({"player": name, "state": state, "last_date": None, "days_since": None, "pct_reached": None,
                        "times_in_window": 0, "status": exposure_status(state, None, 0)})
    return pd.DataFrame(out, columns=TABLE_COLUMNS)


def players_not_on_squad(names, rows):
    """Names in the speed data that aren't on the squad list at all, so a spelling mismatch can't hide anyone."""
    on_list = {name_key(n) for n in names}
    found = {name_key(n): n for n in rows["player"].dropna().unique() if name_key(n) not in on_list}
    return sorted(found.values(), key=str.casefold)


def sort_table(table, how):
    t = table.copy()
    if how == "Longest since 90% first":     # never reached leads, no data last
        t["_rank"] = t.apply(lambda r: r["days_since"] if r["state"] == "hit" else (10 ** 6 if r["state"] == "never" else -1), axis=1)
        return t.sort_values(["_rank", "player"], ascending=[False, True]).drop(columns="_rank").reset_index(drop=True)
    if how == "Most times in the last 7 days":
        t["_days"] = t["days_since"].fillna(10 ** 6)
        return t.sort_values(["times_in_window", "_days", "player"], ascending=[False, True, True]) \
                .drop(columns="_days").reset_index(drop=True)
    return t.sort_values("player", key=lambda s: s.str.casefold()).reset_index(drop=True)


def exposure_html(table, today):
    """The table laid out like the Power BI visual. One unbroken string, because Streamlit's markdown turns
    indented or blank-line-separated HTML into a code block."""
    def pill(key):
        label, background, text = STATUS[key]
        return (f"<span style='background:{background};color:{text};padding:2px 10px;border-radius:9px;"
                f"font-weight:700;font-size:12px'>{escape(label, quote=False)}</span>")

    cell = "padding:7px 6px;text-align:center"
    rows = []
    for r in table.itertuples():
        days = "&mdash;" if r.days_since is None or pd.isna(r.days_since) else str(int(r.days_since))
        count = str(int(r.times_in_window)) if r.state != "nodata" else "&mdash;"
        last = r.last_date.strftime("%d/%m/%Y") if r.state == "hit" else "&mdash;"
        pct = f"{r.pct_reached:.1f}%" if r.state == "hit" else "&mdash;"
        rows.append(
            "<tr style='border-top:1px solid rgba(255,255,255,0.15)'>"
            f"<td style='{cell};font-weight:600'>{escape(str(r.player), quote=False)}</td>"
            f"<td style='{cell};font-weight:700'>{days}</td><td style='{cell};font-weight:700'>{count}</td>"
            f"<td style='{cell}'>{pill(r.status)}</td><td style='{cell}'>{last}</td><td style='{cell}'>{pct}</td></tr>")

    def swatch(key, note=""):
        label, background, _ = STATUS[key]
        return (f"<span><span style='display:inline-block;width:10px;height:10px;background:{background};"
                f"border-radius:2px;margin-right:5px'></span>{escape(label, quote=False)}{note}</span>")

    legend = (swatch("under", f" ({STALE_DAYS}+ days since)") + swatch("optimal") +
              swatch("high", f" ({HIGH_VOLUME_COUNT}+ this wk)") + (swatch("nodata") if (table["status"] == "nodata").any() else ""))
    head = "".join(f"<th style='{cell}'>{h}</th>" for h in
                   ["Player", "Days since", f"Last {WINDOW_DAYS} days", "Status", "Last reached", "% reached"])
    return (
        f"<div style='font-family:sans-serif;box-sizing:border-box;width:100%;border:2px solid {BRAND}'>"
        f"<div style='background:#ffffff;border-bottom:2px solid {BRAND};text-align:center;font-size:20px;"
        f"font-weight:600;color:{BRAND};padding:12px 0 8px'>Sprint Exposure &mdash; {THRESHOLD_PCT:g}%+ Max Velocity"
        f"<div style='font-size:12px;font-weight:400;margin-top:3px'>As of {today.strftime('%d/%m/%Y')}</div></div>"
        f"<div style='background:{BRAND};padding:14px 18px'>"
        f"<div style='display:flex;justify-content:center;align-items:center;gap:16px;margin-bottom:12px;"
        f"font-size:12px;color:#ffffff;flex-wrap:wrap'>{legend}</div>"
        f"<table style='width:100%;border-collapse:collapse;color:#ffffff;font-size:14px'>"
        f"<tr>{head}</tr>{''.join(rows)}</table></div></div>"
    )


# ============================================================================
# THE PAGE
# ============================================================================
def main():
    st.set_page_config(page_title="Max Velocity", layout="wide")
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
            <div style="font-size:28px; font-weight:800; letter-spacing:1px; color:{WHITE};">MAX VELOCITY</div>
            <div style="font-size:11px; opacity:0.85; text-align:right; color:{WHITE}; white-space:nowrap;">
                last loaded {dt.datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([2, 5])
    with c1:
        if st.button("Refresh data now"):
            load_gps.clear()
            load_squad.clear()
            st.rerun()
    with c2:
        sort_by = st.selectbox("Sort by", SORT_OPTIONS, label_visibility="collapsed")

    try:
        gps = load_gps()
    except Exception as exc:
        st.error(f"Couldn't load the GPS file from Dropbox: {exc}")
        st.info("Check the [dropbox] section of your secrets has gps_path, and that the GPS file is where that path says.")
        st.stop()
    try:
        squad = load_squad()
    except Exception as exc:
        st.error(f"Couldn't load the squad list from Supabase: {exc}")
        st.info("Check the [supabase] db_url secret, and that the players table exists.")
        st.stop()

    today = today_uk()                                   # the computer's date, UK time, on every load
    all_names = listed_names(squad)
    if not all_names:
        st.info("The squad list is empty. Add players to the players table in Supabase and they'll appear here.")
        st.stop()
    names = squad_names(squad)
    if not names:
        st.info("Everyone on the squad list is a goalkeeper, so there are no outfield players to show.")
        st.stop()
    rows, unreadable = session_rows(gps)
    table = sort_table(build_table(names, rows, today), sort_by)

    st.markdown(exposure_html(table, today), unsafe_allow_html=True)

    counts = {key: int((table["status"] == key).sum()) for key in STATUS}
    st.caption("  |  ".join(f"{STATUS[key][0]}: {counts[key]}" for key in ("under", "optimal", "high", "nodata")))
    st.caption(
        f"Counted from today ({today.strftime('%d/%m/%Y')}), updating by itself. Only the {len(names)} outfield players "
        f"on your squad list (the players table in Supabase) are shown; goalkeepers are left out. A hit is a SESSION where the player's top speed "
        f"reached {THRESHOLD_PCT:g}% or more of their profile max velocity. Days since is today minus the last hit. "
        f"Last {WINDOW_DAYS} days counts the hits from the past {WINDOW_DAYS} days, today included. Hasn't been exposed "
        f"means never, or {STALE_DAYS}+ days since. High volume is {HIGH_VOLUME_COUNT}+ hits in the window. Last reached "
        f"and % reached show the most recent hit and the highest % that day.")
    no_data = [p for p, s in zip(table["player"], table["state"]) if s == "nodata"]
    if no_data:
        st.caption("No usable max speed data found for: " + ", ".join(no_data) +
                   ". If that's unexpected, the name may be spelled differently in the GPS file.")
    if unreadable:
        st.caption(f"{unreadable} GPS row(s) had a date that couldn't be read and were skipped.")
    with st.expander("Players in the GPS file who aren't on your squad list (left out)"):
        outside = players_not_on_squad(all_names, rows)
        st.write(", ".join(outside) if outside else "None. Everyone in the GPS file is on your squad list.")


if __name__ == "__main__":       # Streamlit runs the file this way; importing it (for checks) does not draw the page
    main()
