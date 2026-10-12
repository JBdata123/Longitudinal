"""
Drill Library.

Save a drill's details (pitch size, players, planned minutes, notes, photo),
link it to the names it goes by in Catapult, and see what players actually
produced in it per minute -- by position -- plus what a given number of
minutes would come to.

Needs: migration_add_drill_library.sql run once in Supabase, and
[supabase] db_url in the Streamlit secrets (same as the Minutes Played page).
"""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import drill_db
import drill_logic as dl
from theme import NAVY, GOLD, WHITE, FONT

CACHE_TTL_SECONDS = 60

st.set_page_config(page_title="Drill Library", layout="wide")

st.markdown(f"""
<style>
    .stApp {{ background-color: {WHITE}; }}
    #MainMenu, footer {{visibility: hidden;}}
    h1, h2, h3 {{ color: {NAVY}; }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- are all three files the right ones, same version?
LIBRARY_VERSION = 7          # keep in step with drill_logic.py and drill_db.py

# For each helper file: what it must say it is, and a few things it must contain. Checking the contents as well
# catches the wrong code having been uploaded under the right name, which a version number alone can't.
_EXPECTED = (
    ("drill_logic.py", dl, ("prepare_rows", "rank_drills", "format_metric", "all_types"), "Drill library calculations"),
    ("drill_db.py", drill_db, ("connect", "ensure_schema", "fetch_drills", "save_drill"), "Database access for the drill library"),
)
_wrong = [(name, starts) for name, module, needed, starts in _EXPECTED
          if getattr(module, "LIBRARY_FILE", None) != name
          or getattr(module, "LIBRARY_VERSION", None) != LIBRARY_VERSION
          or any(not hasattr(module, n) for n in needed)]
if _wrong:
    st.error("The Drill Library files in your GitHub repo don't match each other. "
             f"Out of date or wrong file: {', '.join(n for n, _ in _wrong)}.")
    st.info("Upload the latest version of all three files together (Drill_Library.py, drill_logic.py and "
            "drill_db.py), replacing the old ones. Make sure each file goes in under its own name. To check, open "
            "each one on GitHub: " + "; ".join(f"{n} should start with the words '{starts}'" for n, starts in _wrong) +
            ". Then open Manage app and choose Reboot app.")
    st.stop()


# ---------------------------------------------------------------- data
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading drill data...")
def load_rows():
    conn = drill_db.connect()
    try:
        return dl.prepare_rows(drill_db.fetch_training_rows(conn))
    finally:
        conn.close()


@st.cache_data(ttl=30)
def load_library():
    conn = drill_db.connect()
    try:
        return drill_db.fetch_drills(conn), drill_db.fetch_aliases(conn)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def load_photo(drill_id, version):
    """`version` is the drill's updated_at, so a new photo shows straight away."""
    conn = drill_db.connect()
    try:
        return drill_db.fetch_photo(conn, drill_id)
    finally:
        conn.close()


def refresh_everything():
    load_rows.clear()
    load_library.clear()
    load_photo.clear()


@st.cache_resource(show_spinner=False)
def set_up_tables():
    """Creates the drill tables (and adds the tags column) the first time the
    page runs, so nothing has to be done in Supabase. Returns None, or the
    error text if it wasn't allowed to."""
    conn = None
    try:
        conn = drill_db.connect()
        drill_db.ensure_schema(conn)
        return None
    except Exception as exc:
        return str(exc)
    finally:
        if conn is not None:
            conn.close()


setup_error = set_up_tables()

try:
    rows = load_rows()
    drills, aliases = load_library()
except Exception as exc:
    st.error(f"Couldn't load data from Supabase: {exc}")
    if setup_error:
        st.info("The page also couldn't set up its own tables automatically "
                f"({setup_error}). Run migration_add_drill_library.sql once in the Supabase SQL Editor instead.")
    else:
        st.info("Check the [supabase] db_url secret.")
    st.stop()


# ---------------------------------------------------------------- header
st.markdown(
    f"""
    <div style="background-color:{NAVY}; border-bottom:5px solid {GOLD}; padding:16px 24px;
                margin-bottom:20px; color:{WHITE}; display:flex; align-items:center;
                justify-content:space-between;">
        <div style="font-size:28px; font-weight:800; letter-spacing:1px; color:{WHITE};">DRILL LIBRARY</div>
        <div style="font-size:11px; opacity:0.85; text-align:right; color:{WHITE}; white-space:nowrap;">
            last loaded {datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S')} UK
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

btn_col, view_col = st.columns([2, 8])
with btn_col:
    if st.button("Refresh data now"):
        refresh_everything()
        st.rerun()
with view_col:
    view = st.radio("View", ["Library", "Find a drill", "Add or edit a drill"], horizontal=True,
                    label_visibility="collapsed")

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))


# ---------------------------------------------------------------- small helpers
def tile(label, value, unit=""):
    unit_html = f"<span style='font-size:12px;font-weight:400;opacity:.85'> {escape(unit)}</span>" if unit else ""
    return (f"<div style='background:{NAVY};color:{WHITE};border-radius:8px;padding:10px 14px;"
            f"font-family:{FONT}'><div style='font-size:11px;text-transform:uppercase;letter-spacing:.5px;"
            f"opacity:.85'>{escape(label)}</div><div style='font-size:24px;font-weight:700;line-height:1.2'>"
            f"{escape(value)}{unit_html}</div></div>")


def tile_row(items):
    cells = "".join(f"<div style='flex:1;min-width:120px'>{t}</div>" for t in items)
    st.markdown(f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin:8px 0'>{cells}</div>",
                unsafe_allow_html=True)


def chip(text, highlight=False):
    bg = "#fff4d6" if highlight else "#eef2f7"
    return (f"<span style='display:inline-block;background:{bg};color:{NAVY};border-radius:6px;"
            f"padding:3px 10px;margin:0 6px 6px 0;font-size:13px'>{escape(text)}</span>")


def tags_in_use():
    """Tags that at least one saved drill carries."""
    return sorted({t for tags in drills["tags"] for t in tags}, key=str.casefold) if not drills.empty else []


def has_all_tags(drill_tags, wanted):
    return {w.casefold() for w in wanted} <= {t.casefold() for t in drill_tags}




def note_box(kind, text):
    palette = {"ok": ("#e6f4ea", "#1e6b34"), "long": ("#fff4d6", "#7a5600"),
               "short": ("#fff4d6", "#7a5600"), "unknown": ("#eef2f7", NAVY)}
    bg, fg = palette[kind]
    st.markdown(f"<div style='background:{bg};color:{fg};border-radius:8px;padding:8px 12px;"
                f"font-size:14px;margin-top:8px'>{escape(text)}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- library view
def show_library():
    if drills.empty:
        st.info("No drills saved yet. Open **Add or edit a drill** to create the first one.")
        return

    visible = drills
    if tags_in_use():
        tag_filter = st.multiselect("Filter by tag", tags_in_use(), key="library_tag_filter")
        if tag_filter:
            visible = drills[drills["tags"].apply(lambda t: has_all_tags(t, tag_filter))]
            if visible.empty:
                st.info("No saved drill has all of those tags.")
                return
    chosen = st.selectbox("Drill", list(visible["name"]))
    drill = drills[drills["name"] == chosen].iloc[0]
    drill_id = int(drill["drill_id"])
    linked = list(aliases.loc[aliases["drill_id"] == drill_id, "alias"])

    photo_col, info_col = st.columns([1, 2])
    with photo_col:
        photo = load_photo(drill_id, str(drill["updated_at"])) if drill["has_photo"] else None
        if photo:
            st.image(photo[0], width="stretch")
        else:
            st.markdown("<div style='border:1px dashed #9aa5b5;border-radius:8px;height:160px;display:flex;"
                        "align-items:center;justify-content:center;color:#6b7686'>No photo yet</div>",
                        unsafe_allow_html=True)
    with info_col:
        st.subheader(drill["name"])
        chips = [drill["drill_type"]]
        if pd.notna(drill["pitch_length_m"]) and pd.notna(drill["pitch_width_m"]):
            chips.append(f"Pitch {drill['pitch_length_m']:.0f} x {drill['pitch_width_m']:.0f} m")
        if pd.notna(drill["num_players"]):
            chips.append(f"{drill['num_players']:.0f} players")
        area = dl.area_per_player(drill["pitch_length_m"], drill["pitch_width_m"], drill["num_players"])
        if area:
            chips.append(f"{area:,.0f} m2 per player")
        if pd.notna(drill["planned_minutes"]):
            chips.append(f"Planned {drill['planned_minutes']:.0f} min")
        st.markdown("".join(chip(c) for c in chips) + "".join(chip(t, highlight=True) for t in drill["tags"]),
                    unsafe_allow_html=True)
        if drill["notes"]:
            st.write(drill["notes"])
        st.caption(f"Linked to {len(linked)} name(s) in the GPS data" if linked
                   else "Not linked to any GPS drill name yet, so there are no outputs to show.")

    if not linked:
        return

    data = rows[rows["drill_label"].isin(linked)]
    fit_toggle = st.checkbox("Fit players only", value=True,
                             help="Leaves out players recorded as injured, modified or international "
                                  "on the day. Players with no status recorded are kept.")
    if fit_toggle:
        data = dl.fit_only(data)

    summary = dl.per_minute_by_position(data)
    if summary.empty:
        st.info("No GPS rows found for this drill with the current filter.")
        return

    st.markdown("### Output per minute")
    position = st.radio("Position", list(summary["Position"]), horizontal=True, key=f"pos_{drill_id}")
    row = summary[summary["Position"] == position].iloc[0]
    players, sessions = int(row["Players"]), int(row["Sessions"])
    if dl.is_thin(players, sessions):
        st.warning(dl.thin_message(players, sessions))
    else:
        st.caption(f"Based on {players} players across {sessions} sessions, {row['Minutes']:,.0f} player-minutes.")
    tile_row([tile(f"{label} per min", dl.format_metric(k, row[k]), unit) for k, label, unit in dl.METRICS])
    if pd.isna(row["hr90"]):
        st.caption("No heart rate found for this drill. Firstbeat has to record it under the same drill "
                   "name as the GPS for it to link up.")
    else:
        st.caption(f"On average {dl.format_hr_time(row['hr90'])} of every minute was spent above 90% of max HR "
                   f"(about {row['hr90'] * 100:.0f}% of the drill). Heart rate recorded for "
                   f"{int(row['HR players'])} of {players} players.")

    with st.expander("All positions"):
        table = summary[["Position", "Players", "Sessions"]].copy()
        table["Minutes"] = summary["Minutes"].round(0)
        table["Data"] = ["Thin" if dl.is_thin(int(p), int(n)) else "" for p, n in zip(summary["Players"], summary["Sessions"])]
        for k, label, unit in dl.METRICS:
            table[label + (f" ({unit})" if unit else "") + " / min"] = [dl.format_metric(k, v) for v in summary[k]]
        st.dataframe(table, width="stretch", hide_index=True)

    st.markdown("### If we run this drill for...")
    default_minutes = float(drill["planned_minutes"]) if pd.notna(drill["planned_minutes"]) else 10.0
    minutes = st.number_input("Minutes", min_value=1.0, max_value=120.0, value=default_minutes,
                              step=1.0, key=f"mins_{drill_id}")
    projected = dl.project(row, minutes)
    tile_row([tile(label, dl.format_metric(k, projected[k], per_minute=False), unit)
              for k, label, unit in dl.METRICS])
    note_box(*dl.projection_note(minutes, dl.observed_block_minutes(data)))
    st.caption(f"Per player, for the {position.lower()} group. Assumes the per-minute rate holds for the whole time.")


# ---------------------------------------------------------------- find a drill
NEW_TYPE_CHOICE = "New type..."      # only used when this Streamlit version cannot take a typed-in option

FINDER_DEFAULTS = {"distance": (1000.0, 100.0), "hsr": (100.0, 10.0), "sprint": (20.0, 5.0),
                   "accel": (20.0, 5.0), "decel": (20.0, 5.0), "hr90": (2.0, 0.5)}


def show_finder():
    if drills.empty:
        st.info("No drills saved yet, so there is nothing to search. Add some first.")
        return
    st.markdown("Pick one or more measures and a target for each, and it ranks your saved drills by how close each "
                "would get if you ran it for the minutes you have, using what players actually produced in it.")

    by_label = {label: (key, unit) for key, label, unit in dl.METRICS}
    c1, c2 = st.columns([2, 1])
    chosen = c1.multiselect("Measures", list(by_label), default=["Total distance"],
                            help="Pick more than one to filter by several at once. A drill only counts as a match "
                                 "if every chosen measure is close to its target.")
    minutes = c2.number_input("Minutes available", min_value=1.0, max_value=120.0, value=10.0, step=1.0)
    if not chosen:
        st.info("Pick at least one measure.")
        return

    targets = {}
    target_cols = st.columns(min(len(chosen), 3))
    for n, label in enumerate(chosen):
        key, unit = by_label[label]
        default_target, step = FINDER_DEFAULTS[key]
        if key == "hr90":
            target_label = "Target (minutes above 90% HR)" if len(chosen) == 1 else f"{label} target (minutes)"
        else:
            what = unit if unit else "count"
            target_label = f"Target ({what})" if len(chosen) == 1 else f"{label} target ({what})"
        targets[key] = target_cols[n % len(target_cols)].number_input(
            target_label, min_value=0.1, value=default_target, step=step, key=f"finder_target_{key}", format="%.1f")

    c4, c5, c6 = st.columns(3)
    positions = ["All outfield"] + sorted(p for p in rows["position"].dropna().unique())
    position = c4.selectbox("Position", positions)
    wanted_tags = c5.multiselect("Drill must have all of these tags", tags_in_use(),
                                 help="Leave empty to search every drill.")
    tolerance = c6.slider("Counts as a match within (%)", 5, 50, 20, step=5)
    fit = st.checkbox("Fit players only", value=True,
                      help="Leaves out players recorded as injured, modified or international on the day.")

    result = dl.rank_drills(rows, drills, aliases, targets, minutes, position,
                            required_tags=wanted_tags, tolerance_pct=float(tolerance), fit=fit)
    left_out = result.attrs.get("left_out", [])
    many = len(chosen) > 1
    if result.empty:
        st.info(f"No saved drill has recorded data for {'all of those measures' if many else 'that measure'}, "
                "that position and that tag combination.")
        if left_out and many:
            st.caption("Left out because they have no recorded data for one of the chosen measures in this group: "
                       + ", ".join(left_out))
        return

    matches = int(result["Within range"].sum())
    st.markdown(f"### {matches} drill{'s' if matches != 1 else ''} within {tolerance}% of "
                f"{'every target' if many else 'the target'}")

    tail = {"Tags": result["Tags"], "Type": result["Type"], "Players": result["Players"],
            "Sessions": result["Sessions"], "Data": ["Thin" if t else "" for t in result["Thin"]]}
    match_col = ["Yes" if ok else "No" for ok in result["Within range"]]
    if not many:
        key = next(iter(targets))
        shown = pd.DataFrame({
            "Drill": result["Drill"],
            "Match": match_col,
            "Per min": [dl.format_metric(key, v) for v in result[f"{key}_rate"]],
            f"At {minutes:g} min": [dl.format_metric(key, v, per_minute=False) for v in result[f"{key}_projected"]],
            "Difference": [f"{d:+.0f}%" for d in result[f"{key}_diff"]],
            "Minutes needed": [f"{m:.1f} min" if pd.notna(m) else "can't reach it" for m in result[f"{key}_needed"]],
            **tail,
        })
        st.caption(f"Closest first. Per player, for the {position.lower()} group. 'Minutes needed' is how long the "
                   f"drill would have to run to reach the target on its own. 'Thin' means fewer than "
                   f"{dl.MIN_PLAYERS} players or a single session behind the numbers, so treat it as a record of "
                   f"that day, not a benchmark.")
    else:
        columns = {"Drill": result["Drill"], "Match": match_col,
                   "Worst miss": [f"{w:.0f}%" if pd.notna(w) else "n/a" for w in result["Worst miss"]]}
        for key, (label, unit) in {k: (lab, un) for k, lab, un in dl.METRICS if k in targets}.items():
            suffix = f" {unit}" if unit else ""
            columns[f"{label} per min"] = [dl.format_metric(key, v) for v in result[f"{key}_rate"]]
            columns[f"{label} at {minutes:g} min"] = [
                f"{dl.format_metric(key, v, per_minute=False)}{suffix if key != 'hr90' else ''} ({d:+.0f}%)"
                for v, d in zip(result[f"{key}_projected"], result[f"{key}_diff"])]
        shown = pd.DataFrame({**columns, **tail})
        st.caption(f"Ranked by each drill's worst miss across the chosen measures, so one far-off measure can't hide "
                   f"behind another that's on target. It's a match only if every measure is within {tolerance}%. "
                   f"Per player, for the {position.lower()} group. 'Thin' means fewer than {dl.MIN_PLAYERS} players "
                   f"or a single session behind the numbers, so treat it as a record of that day, not a benchmark.")
    st.dataframe(shown, width="stretch", hide_index=True)
    if left_out:
        st.caption("Left out because they have no recorded data for "
                   f"{'one of the chosen measures' if many else 'this measure'} in this group: " + ", ".join(left_out))


# ---------------------------------------------------------------- add / edit view
def show_editor():
    mode = st.radio("What would you like to do?", ["Add a new drill", "Edit an existing drill"], horizontal=True)

    defaults = {"name": "", "drill_type": "Team drill", "pitch_length_m": 0.0, "pitch_width_m": 0.0,
                "num_players": 0, "planned_minutes": 0.0, "notes": ""}
    default_aliases, target_id, target_key = [], None, "new"
    current = None

    all_labels = sorted(rows["drill_label"].dropna().unique()) if not rows.empty else []
    linked_elsewhere = set(aliases["alias"])

    if mode == "Add a new drill":
        suggestions = dl.suggest_groups(rows, linked_elsewhere)
        show_all = st.checkbox("Include warm-ups, tests, goalkeeper and individual sessions", value=False)
        if not show_all and not suggestions.empty:
            suggestions = suggestions[suggestions["type"] == "Team drill"]
        options = ["Start from scratch"] + [
            f"{r.suggested_name}  ({r.sessions} session{'s' if r.sessions != 1 else ''}, "
            f"{len(r.labels)} name{'s' if len(r.labels) != 1 else ''})" for r in suggestions.itertuples()]
        pick = st.selectbox("Start from a drill name found in your data", options,
                            help="Names are grouped when they only differ by block prefix (B1 -), "
                                 "BLOCK number or spacing.")
        if pick != "Start from scratch":
            sugg = suggestions.iloc[options.index(pick) - 1]
            defaults["name"], defaults["drill_type"] = sugg["suggested_name"], sugg["type"]
            default_aliases = list(sugg["labels"])
            target_key = f"new_{sugg['key']}"
    else:
        if drills.empty:
            st.info("There are no drills to edit yet.")
            return
        chosen = st.selectbox("Drill to edit", list(drills["name"]))
        current = drills[drills["name"] == chosen].iloc[0]
        target_id = int(current["drill_id"])
        target_key = f"edit_{target_id}"
        defaults.update({
            "name": current["name"], "drill_type": current["drill_type"],
            "pitch_length_m": 0.0 if pd.isna(current["pitch_length_m"]) else float(current["pitch_length_m"]),
            "pitch_width_m": 0.0 if pd.isna(current["pitch_width_m"]) else float(current["pitch_width_m"]),
            "num_players": 0 if pd.isna(current["num_players"]) else int(current["num_players"]),
            "planned_minutes": 0.0 if pd.isna(current["planned_minutes"]) else float(current["planned_minutes"]),
            "notes": current["notes"] or "",
        })
        default_aliases = list(aliases.loc[aliases["drill_id"] == target_id, "alias"])
        linked_elsewhere -= set(default_aliases)

    type_options = dl.all_types(drills)
    defaults["drill_type"] = dl.canonical_type(defaults["drill_type"], known=type_options)   # 'duels' -> 'Duels'
    if defaults["drill_type"] not in type_options:      # e.g. a type guessed from the data
        type_options = type_options + [defaults["drill_type"]]

    tag_options = dl.all_tags(drills)
    current_tags = list(current["tags"]) if current is not None else []
    tag_options = tag_options + [t for t in current_tags if t not in tag_options]

    available = [a for a in all_labels if a not in linked_elsewhere]
    for a in default_aliases:                     # keep currently-linked names selectable
        if a not in available:
            available.append(a)

    with st.form(f"drill_form_{target_key}"):
        name = st.text_input("Drill name", value=defaults["name"])
        if dl.supports_new_options(st.selectbox):
            typed_type = st.selectbox(
                "Type", type_options, index=type_options.index(defaults["drill_type"]), accept_new_options=True,
                help="Start typing to find a type you've used before, or type a new one. Any new type is "
                     "remembered and offered next time.")
            new_type_text = ""
        else:       # older Streamlit: pick from the list, or choose 'New type...' and type it below
            typed_type = st.selectbox("Type", type_options + [NEW_TYPE_CHOICE],
                                      index=type_options.index(defaults["drill_type"]))
            new_type_text = st.text_input("New type", help="Only used if you chose 'New type...' above. "
                                                           "It's remembered and offered next time.")
        c1, c2, c3, c4 = st.columns(4)
        length = c1.number_input("Pitch length (m)", min_value=0.0, value=defaults["pitch_length_m"], step=1.0,
                                 help="Leave at 0 if not known.")
        width = c2.number_input("Pitch width (m)", min_value=0.0, value=defaults["pitch_width_m"], step=1.0)
        players = c3.number_input("Players", min_value=0, value=defaults["num_players"], step=1)
        planned = c4.number_input("Planned minutes", min_value=0.0, value=defaults["planned_minutes"], step=1.0)
        notes = st.text_area("Notes", value=defaults["notes"])
        if dl.supports_new_options(st.multiselect):
            chosen_tags = st.multiselect(
                "Tags", options=tag_options, default=current_tags, accept_new_options=True,
                help="Tick any that apply, or start typing to find a tag you've used before or add a new one "
                     "(press Enter). New tags are remembered and offered next time.")
            new_tag_text = ""
        else:       # older Streamlit: tick from the list, and type any new ones in a separate box
            chosen_tags = st.multiselect("Tags", options=tag_options, default=current_tags,
                                         help="Tick any that apply, such as In possession or Out of possession.")
            new_tag_text = st.text_input("Add new tags (separate with commas)", value="",
                                         help="Anything not in the list above. It will appear in the list from then on.")
        linked_names = st.multiselect(
            "Names this drill goes by in the GPS data", options=available, default=default_aliases,
            help="Every drill label in Catapult that is this drill (block prefixes, BLOCK 1-4, spelling "
                 "variants). Names already used by another drill aren't listed.")
        upload = st.file_uploader("Photo or diagram", type=["png", "jpg", "jpeg"])
        remove_photo = False
        if current is not None and current["has_photo"]:
            remove_photo = st.checkbox("Remove the current photo")
        submitted = st.form_submit_button("Save drill")

    if submitted:
        entered_type = new_type_text if typed_type == NEW_TYPE_CHOICE else typed_type
        drill_type = dl.canonical_type(entered_type, known=type_options)
        try:
            photo, mime = (drill_db.shrink_photo(upload.getvalue()) if upload is not None else (None, None))
            conn = drill_db.connect()
            try:
                drill_db.save_drill(
                    conn, target_id,
                    {"name": name, "drill_type": drill_type, "pitch_length_m": length, "pitch_width_m": width,
                     "num_players": players, "planned_minutes": planned, "notes": notes,
                     "tags": dl.clean_tags(chosen_tags, new_tag_text, known=tag_options)},
                    linked_names, photo=photo, photo_mime=mime, remove_photo=remove_photo)
            finally:
                conn.close()
        except ValueError as exc:
            st.error(str(exc))
        else:
            refresh_everything()
            st.session_state["flash"] = f"Saved {name.strip()}."
            st.rerun()

    if target_id is not None:
        st.divider()
        confirm = st.checkbox("I want to delete this drill", key=f"del_confirm_{target_id}")
        if st.button("Delete drill", key=f"del_{target_id}"):
            if not confirm:
                st.warning("Tick the box first, then press Delete drill.")
            else:
                conn = drill_db.connect()
                try:
                    drill_db.delete_drill(conn, target_id)
                finally:
                    conn.close()
                refresh_everything()
                st.session_state["flash"] = f"Deleted {current['name']}."
                st.rerun()


if view == "Library":
    show_library()
elif view == "Find a drill":
    show_finder()
else:
    show_editor()
