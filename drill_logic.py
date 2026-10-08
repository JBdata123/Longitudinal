"""
Drill library calculations -- no Streamlit, no database, so everything here
can be tested on its own (see tests/test_drill_logic.py).

Rules that matter:
  * Output per minute is TOTAL metric / TOTAL minutes across every record,
    never an average of each player's own rate. (Averaging rates lets a
    player with 40 seconds in a drill count as much as one who did the whole
    block -- the same mistake that distorted the MPM-per-quarter chart.)
  * Every figure comes with how many players and sessions are behind it, and
    thin ones are flagged. Most drills have only been run once.
"""
import re

import pandas as pd

# (column key, label, unit) -- the six measures shown for every drill
METRICS = [
    ("distance", "Total distance", "m"),
    ("hsr", "HSR (bands 4+5)", "m"),
    ("sprint", "Sprint distance", "m"),
    ("accel", "Accelerations 1-3", ""),
    ("decel", "Decelerations 1-3", ""),
    ("hr90", "Minutes above 90% HR", "min"),
]

DRILL_TYPES = ["Team drill", "Warm-up", "Test / conditioning", "Individual", "GK", "Rehab", "Other"]

# A figure built from fewer than this is a record of what happened on the
# day, not a benchmark.
MIN_PLAYERS = 5
MIN_SESSIONS = 2

# Labels in master_data that are not drills at all.
NON_DRILL_LABELS = ("SESSION", "TEAM SESSION", "1ST HALF", "2ND HALF", "WARM UP", "EXTRAS")


def parse_minutes(duration_text):
    """HH:MM:SS text -> minutes. Anything unusable is 0."""
    if duration_text is None or (isinstance(duration_text, float) and pd.isna(duration_text)):
        return 0.0
    text = str(duration_text).strip()
    if len(text) < 8:
        return 0.0
    try:
        return int(text[0:2]) * 60 + int(text[3:5]) + int(text[6:8]) / 60
    except ValueError:
        return 0.0


def normalise_drill_key(label):
    """What two labels have in common when they are the same drill.
    Removes the session-block prefix (B1 -, B3 -), the BLOCK n suffix and any
    spacing/punctuation, so '11 V 11' = '11V11' and 'WALK THROUGH' =
    'WALKTHROUGH'. Genuine wording differences (THROUGH vs WITH, SET PLAYS vs
    SET PIECES) are deliberately NOT merged -- those need a human."""
    text = str(label or "").upper().strip()
    text = re.sub(r"^B\d+(\s*-\s*|\s+)", "", text)      # "B1 - 5V3 ..." and "B4 3V2"
    text = re.sub(r"\s+BLOCK\s+\d+$", "", text)
    return re.sub(r"[^A-Z0-9+]", "", text)


def clean_display_name(label):
    """Same clean-up as the key, but keeps the readable text."""
    text = str(label or "").strip()
    text = re.sub(r"^B\d+(\s*-\s*|\s+)", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+BLOCK\s+\d+$", "", text, flags=re.IGNORECASE).strip()


def guess_drill_type(label, avg_players_per_session):
    """Best guess at what a label is, so the library can hide the things that
    aren't team drills. Only a suggestion -- the user can change it."""
    name = str(label or "").upper().strip()
    if name.startswith(("GOALKEEPER", "GK ")) or name == "GK":
        return "GK"
    if name == "REHAB":
        return "Rehab"
    if name.startswith("WARM UP"):
        return "Warm-up"
    if "TEST" in name or "ENDURANCE" in name:
        return "Test / conditioning"
    if name == "UNKNOWN DRILL" or name.startswith("ACADEMY"):
        return "Other"
    if re.search(r"\bTRAINING( \d+)?$", name) and avg_players_per_session < 5:
        return "Individual"
    return "Team drill"


def parse_minutes_or_nan(duration_text):
    """Like parse_minutes, but a missing value stays missing (NaN) instead of
    becoming 0. Needed for heart rate: 'no Firstbeat data for this drill' is
    not the same as '0 minutes above 90%'."""
    if duration_text is None or (isinstance(duration_text, float) and pd.isna(duration_text)):
        return float("nan")
    text = str(duration_text).strip()
    if len(text) < 8:
        return float("nan")
    try:
        return int(text[0:2]) * 60 + int(text[3:5]) + int(text[6:8]) / 60
    except ValueError:
        return float("nan")


def prepare_rows(df):
    """Adds the numeric columns the library needs to the raw master_data rows."""
    d = df.copy()
    num = lambda col: pd.to_numeric(d[col], errors="coerce").fillna(0) if col in d else 0.0
    d["minutes"] = d["gps_total_duration"].apply(parse_minutes)
    d["distance"] = num("gps_total_distance")
    d["hsr"] = num("gps_velocity_band_4_total_distance") + num("gps_velocity_band_5_total_distance")
    d["sprint"] = num("gps_sd")
    d["accel"] = num("gps_acceleration_b1_3_total_efforts_gen_2")
    d["decel"] = num("gps_deceleration_b1_3_total_efforts_gen_2")
    if "fb_high_intensity_training_hh_mm_ss" in d:
        d["hr90"] = d["fb_high_intensity_training_hh_mm_ss"].apply(parse_minutes_or_nan)
    else:
        d["hr90"] = float("nan")
    d["position"] = d["position"].fillna("Unknown").replace("", "Unknown")
    return d


def fit_only(df):
    """Drop rows where the player's recorded status is anything other than
    Fit (Injured, Modified, International...). Rows with no status recorded
    are kept -- older dates predate the squad status file."""
    status = df["player_status"].astype("string").str.strip().str.lower()
    return df[status.isna() | (status == "fit")]


def suggest_groups(rows, linked_aliases):
    """Groups the drill names in the data that aren't in the library yet by
    what they have in common, ready to be turned into library drills."""
    cols = ["key", "suggested_name", "labels", "sessions", "players", "type"]
    if rows.empty:
        return pd.DataFrame(columns=cols)
    per_label = rows.groupby("drill_label").agg(
        sessions=("session_date", "nunique"), player_rows=("player", "size")
    )
    per_label = per_label[~per_label.index.isin(set(linked_aliases))]
    if per_label.empty:
        return pd.DataFrame(columns=cols)
    per_label["avg_players"] = per_label["player_rows"] / per_label["sessions"]
    per_label["key"] = [normalise_drill_key(x) for x in per_label.index]
    out = []
    for key, grp in per_label.groupby("key"):
        labels = sorted(grp.index)
        in_group = rows[rows["drill_label"].isin(labels)]
        # name & type come from the most-used label in the group
        lead = grp.sort_values(["sessions", "player_rows"], ascending=False).index[0]
        out.append({
            "key": key,
            "suggested_name": clean_display_name(lead),
            "labels": labels,
            "sessions": in_group["session_date"].nunique(),
            "players": in_group["player"].nunique(),
            "type": guess_drill_type(lead, grp.loc[lead, "avg_players"]),
        })
    return pd.DataFrame(out, columns=cols).sort_values(
        ["sessions", "suggested_name"], ascending=[False, True]
    ).reset_index(drop=True)


def per_minute_by_position(df):
    """One row per position group plus 'All outfield'. Output per minute is
    total / total minutes, with the players and sessions behind it.

    Heart rate is worked out only from rows that actually have Firstbeat
    data (and only against the minutes of those same rows), so a player with
    no heart rate recorded can't drag the figure down. If nobody has any,
    it's NaN -- shown as n/a, never as 0."""
    keys = [k for k, _, _ in METRICS]
    cols = ["Position", "Players", "Sessions", "Minutes", "HR players"] + keys
    d = df[df["minutes"] > 0]
    if d.empty:
        return pd.DataFrame(columns=cols)

    def build(label, g):
        mins = g["minutes"].sum()
        with_hr = g[g["hr90"].notna()]
        row = {"Position": label, "Players": g["player"].nunique(),
               "Sessions": g["session_date"].nunique(), "Minutes": mins,
               "HR players": with_hr["player"].nunique()}
        for k in keys:
            if k == "hr90":
                hr_minutes = with_hr["minutes"].sum()
                row[k] = with_hr["hr90"].sum() / hr_minutes if hr_minutes > 0 else float("nan")
            else:
                row[k] = g[k].sum() / mins
        return row

    rows = [build("All outfield", d)]
    for pos, g in d.groupby("position"):
        rows.append(build(pos, g))
    return pd.DataFrame(rows, columns=cols)


def is_thin(players, sessions):
    return players < MIN_PLAYERS or sessions < MIN_SESSIONS


def thin_message(players, sessions):
    return (f"Based on {players} player(s) in {sessions} session(s). "
            "That's a record of what happened on the day, not a benchmark.")


def observed_block_minutes(df):
    """(shortest, longest) block this drill has been logged at: for every
    time it was run, the longest any player did. Using the longest keeps a
    substitute's 40 seconds from looking like a 40-second drill."""
    d = df[df["minutes"] > 0]
    if d.empty:
        return None
    per_run = d.groupby(["session_date", "drill_label"])["minutes"].max()
    return float(per_run.min()), float(per_run.max())


def project(per_minute_row, minutes):
    """If the drill ran for `minutes`, what each metric comes to."""
    return {k: float(per_minute_row[k]) * minutes for k, _, _ in METRICS}


def projection_note(minutes, observed):
    """('ok'|'long'|'short'|'unknown', text) -- how far to trust a projection.
    Output per minute usually falls as a block gets longer, so going beyond
    what has been logged is an upper estimate; well below it, a lower one."""
    if observed is None:
        return "unknown", "No block length is logged for this drill yet."
    lo, hi = observed
    span = f"{lo:.0f} to {hi:.0f} min" if round(lo) != round(hi) else f"{hi:.0f} min"
    if minutes > hi * 1.25:
        return "long", (f"Longer than any logged block ({span}). Intensity usually drops over "
                        "longer blocks, so treat this as an upper estimate.")
    if minutes < lo * 0.5:
        return "short", (f"Shorter than any logged block ({span}). Short bursts are usually "
                         "more intense, so treat this as a lower estimate.")
    return "ok", f"Inside the range this drill has been logged at ({span})."


def area_per_player(length_m, width_m, players):
    """Pitch area per player in m2, or None if anything is missing."""
    try:
        if not (length_m and width_m and players):
            return None
        return float(length_m) * float(width_m) / float(players)
    except (TypeError, ValueError):
        return None
