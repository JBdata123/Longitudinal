"""
Database access for the drill library (Supabase / Postgres).

Reads training rows from master_data; reads and writes the `drills` and
`drill_aliases` tables created by migration_add_drill_library.sql. Those two
tables are never touched by ingest.py, so what's typed here survives every
sync.
"""
import io

import pandas as pd
import psycopg2

TRAINING_ROWS_SQL = """
    select
        player, position, session_date, drill_label, player_status,
        gps_total_duration, gps_total_distance,
        gps_velocity_band_4_total_distance, gps_velocity_band_5_total_distance,
        gps_sd,
        gps_acceleration_b1_3_total_efforts_gen_2,
        gps_deceleration_b1_3_total_efforts_gen_2,
        fb_high_intensity_training_hh_mm_ss
    from master_data
    where gps_interval_scheme is null
      and drill_label is not null
      and upper(trim(drill_label)) not in
          ('SESSION', 'TEAM SESSION', '1ST HALF', '2ND HALF', 'WARM UP', 'EXTRAS')
      and (position is null or position <> 'Goalkeeper')
      and session_date is not null
      and gps_total_duration is not null
"""

_DRILL_NUMERIC = ["pitch_length_m", "pitch_width_m", "num_players", "planned_minutes"]


def connect():
    import streamlit as st
    return psycopg2.connect(st.secrets["supabase"]["db_url"])


def _frame(cur):
    return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


def fetch_training_rows(conn):
    with conn.cursor() as cur:
        cur.execute(TRAINING_ROWS_SQL)
        df = _frame(cur)
    df["session_date"] = pd.to_datetime(df["session_date"])
    return df


def fetch_drills(conn):
    with conn.cursor() as cur:
        cur.execute("""
            select drill_id, name, drill_type, pitch_length_m, pitch_width_m,
                   num_players, planned_minutes, notes,
                   (photo is not null) as has_photo, updated_at
            from drills order by name
        """)
        df = _frame(cur)
    for col in _DRILL_NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")   # Decimal -> float
    return df


def fetch_aliases(conn):
    with conn.cursor() as cur:
        cur.execute("select alias, drill_id from drill_aliases order by alias")
        return _frame(cur)


def fetch_photo(conn, drill_id):
    """(bytes, mime) or None."""
    with conn.cursor() as cur:
        cur.execute("select photo, photo_mime from drills where drill_id = %s", (int(drill_id),))
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return bytes(row[0]), row[1] or "image/jpeg"


def shrink_photo(raw_bytes, max_px=1200, quality=85):
    """Resize and recompress an uploaded image so the photos stay small
    (a few hundred KB each) in the database. Returns (bytes, mime)."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.load()
    except Exception as exc:
        raise ValueError("That file doesn't look like an image.") from exc
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))   # transparency -> white
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")
    img.thumbnail((max_px, max_px))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def _none_if_blank(value):
    """Number inputs use 0 for 'not known'."""
    try:
        return None if value is None or float(value) == 0 else float(value)
    except (TypeError, ValueError):
        return None


def save_drill(conn, drill_id, fields, aliases, photo=None, photo_mime=None, remove_photo=False):
    """Create (drill_id=None) or update a drill and replace the set of GPS
    names linked to it. Returns the drill_id. Raises ValueError with a
    plain-English message for the problems a user can fix."""
    name = (fields.get("name") or "").strip()
    if not name:
        raise ValueError("Give the drill a name.")
    aliases = sorted({a for a in aliases if a and a.strip()})
    values = (
        name,
        fields.get("drill_type") or "Team drill",
        _none_if_blank(fields.get("pitch_length_m")),
        _none_if_blank(fields.get("pitch_width_m")),
        None if _none_if_blank(fields.get("num_players")) is None else int(fields["num_players"]),
        _none_if_blank(fields.get("planned_minutes")),
        (fields.get("notes") or "").strip() or None,
    )
    try:
        with conn:                                   # one transaction: commit or roll back together
            with conn.cursor() as cur:
                if aliases:
                    cur.execute(
                        "select alias, drill_id from drill_aliases where alias = any(%s)", (aliases,))
                    taken = [a for a, d in cur.fetchall() if d != drill_id]
                    if taken:
                        raise ValueError(
                            "These names already belong to another drill: " + ", ".join(sorted(taken)))
                if drill_id is None:
                    cur.execute("""
                        insert into drills (name, drill_type, pitch_length_m, pitch_width_m,
                                            num_players, planned_minutes, notes)
                        values (%s,%s,%s,%s,%s,%s,%s) returning drill_id
                    """, values)
                    drill_id = cur.fetchone()[0]
                else:
                    cur.execute("""
                        update drills set name=%s, drill_type=%s, pitch_length_m=%s,
                               pitch_width_m=%s, num_players=%s, planned_minutes=%s,
                               notes=%s, updated_at=now()
                        where drill_id=%s
                    """, values + (int(drill_id),))
                if photo is not None:
                    cur.execute("update drills set photo=%s, photo_mime=%s, updated_at=now() "
                                "where drill_id=%s", (psycopg2.Binary(photo), photo_mime, int(drill_id)))
                elif remove_photo:
                    cur.execute("update drills set photo=null, photo_mime=null, updated_at=now() "
                                "where drill_id=%s", (int(drill_id),))
                cur.execute("delete from drill_aliases where drill_id=%s and not (alias = any(%s))",
                            (int(drill_id), aliases))
                for alias in aliases:
                    cur.execute("insert into drill_aliases (alias, drill_id) values (%s,%s) "
                                "on conflict (alias) do nothing", (alias, int(drill_id)))
    except psycopg2.errors.UniqueViolation as exc:
        raise ValueError("A drill with that name already exists.") from exc
    return drill_id


def delete_drill(conn, drill_id):
    with conn:
        with conn.cursor() as cur:
            cur.execute("delete from drills where drill_id=%s", (int(drill_id),))   # aliases cascade
