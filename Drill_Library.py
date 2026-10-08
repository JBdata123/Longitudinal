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
    div.block-container {{ padding-top: 0rem; }}
    h1, h2, h3 {{ color: {NAVY}; }}
</style>
""", unsafe_allow_html=True)


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


try:
    rows = load_rows()
    drills, aliases = load_library()
except Exception as exc:
    st.error(f"Couldn't load data from Supabase: {exc}")
    st.info("Check the [supabase] db_url secret, and that migration_add_drill_library.sql has been run.")
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
    view = st.radio("View", ["Library", "Add or edit a drill"], horizontal=True, label_visibility="collapsed")

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


def chip(text):
    return (f"<span style='display:inline-block;background:#eef2f7;color:{NAVY};border-radius:6px;"
            f"padding:3px 10px;margin:0 6px 6px 0;font-size:13px'>{escape(text)}</span>")


def fmt_metric(key, value):
    return f"{value:,.0f}" if key == "distance" else f"{value:,.1f}"


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

    names = list(drills["name"])
    chosen = st.selectbox("Drill", names)
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
        st.markdown("".join(chip(c) for c in chips), unsafe_allow_html=True)
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
    tile_row([tile(f"{label} per min", fmt_metric(k, row[k]), unit) for k, label, unit in dl.METRICS])

    with st.expander("All positions"):
        table = summary.copy()
        table["Minutes"] = table["Minutes"].round(0)
        table["Note"] = ["Thin" if dl.is_thin(int(p), int(s)) else "" for p, s in zip(table["Players"], table["Sessions"])]
        for k, label, unit in dl.METRICS:
            table[label + (f" ({unit})" if unit else "") + " / min"] = table[k].round(0 if k == "distance" else 1)
        st.dataframe(table.drop(columns=[k for k, _, _ in dl.METRICS]), width="stretch", hide_index=True)

    st.markdown("### If we run this drill for...")
    default_minutes = float(drill["planned_minutes"]) if pd.notna(drill["planned_minutes"]) else 10.0
    minutes = st.number_input("Minutes", min_value=1.0, max_value=120.0, value=default_minutes,
                              step=1.0, key=f"mins_{drill_id}")
    projected = dl.project(row, minutes)
    tile_row([tile(label, fmt_metric(k, projected[k]), unit) for k, label, unit in dl.METRICS])
    note_box(*dl.projection_note(minutes, dl.observed_block_minutes(data)))
    st.caption(f"Per player, for the {position.lower()} group. Assumes the per-minute rate holds for the whole time.")


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

    available = [a for a in all_labels if a not in linked_elsewhere]
    for a in default_aliases:                     # keep currently-linked names selectable
        if a not in available:
            available.append(a)

    with st.form(f"drill_form_{target_key}"):
        name = st.text_input("Drill name", value=defaults["name"])
        drill_type = st.selectbox("Type", dl.DRILL_TYPES, index=dl.DRILL_TYPES.index(defaults["drill_type"])
                                  if defaults["drill_type"] in dl.DRILL_TYPES else 0)
        c1, c2, c3, c4 = st.columns(4)
        length = c1.number_input("Pitch length (m)", min_value=0.0, value=defaults["pitch_length_m"], step=1.0,
                                 help="Leave at 0 if not known.")
        width = c2.number_input("Pitch width (m)", min_value=0.0, value=defaults["pitch_width_m"], step=1.0)
        players = c3.number_input("Players", min_value=0, value=defaults["num_players"], step=1)
        planned = c4.number_input("Planned minutes", min_value=0.0, value=defaults["planned_minutes"], step=1.0)
        notes = st.text_area("Notes", value=defaults["notes"])
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
        try:
            photo, mime = (drill_db.shrink_photo(upload.getvalue()) if upload is not None else (None, None))
            conn = drill_db.connect()
            try:
                drill_db.save_drill(
                    conn, target_id,
                    {"name": name, "drill_type": drill_type, "pitch_length_m": length, "pitch_width_m": width,
                     "num_players": players, "planned_minutes": planned, "notes": notes},
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
else:
    show_editor()
