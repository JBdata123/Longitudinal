"""
Builds the plotly figures for the Longitudinal Report page, in the
style of the LCFC mock-up: centred white metric-name title bar + navy chart
panel, bold white values printed directly on/inside the bars, a dedicated
row of small white ACWR/TE boxes floating above the bars, LCFC brand
colours throughout.
"""
import pandas as pd
import plotly.graph_objects as go
from theme import (NAVY, GOLD, RED, GREEN, GREY, DARK_GOLD, WHITE, FONT, base_layout,
                    day_axis_label, value_box_row, headroom_range,
                    three_band_ranges, bold, acwr_box_color, te_box_color,
                    ACWR_ACUTE_SPAN, ACWR_CHRONIC_SPAN)

VALUE_FONT_SIZE = 13  # fixed size for all bar value labels - never auto-shrunk


def _x_labels(df):
    return [day_axis_label(d, t) for d, t in zip(df["Date"], df["Day"])]


def _bargap_for(n):
    """More categories on screen -> bars naturally get thinner already
    (fixed panel width / more categories), but we also want bars generally
    slim per the brief - so use a fairly high, mildly-adaptive bargap."""
    return min(0.75, 0.45 + n * 0.01)


def ewma_acwr(daily_series: pd.Series) -> pd.Series:
    """Exponentially-weighted ACWR: acute = EWMA span 7, chronic = EWMA span 28."""
    acute = daily_series.ewm(span=ACWR_ACUTE_SPAN, adjust=False).mean()
    chronic = daily_series.ewm(span=ACWR_CHRONIC_SPAN, adjust=False).mean()
    return (acute / chronic.replace(0, pd.NA)).fillna(0)


def _acwr_for_dates(full_history: pd.DataFrame, value_col: str, dates_shown):
    """Computes EWMA ACWR over a player's FULL date history (so the 7/28-day
    windows are correct), then returns just the values for the dates on screen."""
    s = full_history.set_index("Date")[value_col].sort_index()
    full_idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
    s = s.reindex(full_idx, fill_value=0)
    acwr = ewma_acwr(s)
    return [round(acwr.loc[d], 2) if d in acwr.index else None for d in dates_shown]


def _apply_value_row(fig, x, values, max_bar_value, fmt="{:.2f}", color_fn=None):
    yaxis_max, row_y = headroom_range(max_bar_value)
    fig.update_layout(yaxis=dict(visible=False, range=[0, yaxis_max]))
    value_box_row(fig, x, values, row_y, fmt=fmt, color_fn=color_fn)
    return fig


def _bold_labels(series, fmt="{:.0f}"):
    return [bold(fmt.format(v)) for v in series]


def _bold_labels_masked(values, has_data, fmt="{:.0f}"):
    """Same as _bold_labels, but blank ("") wherever has_data is False -
    used so rest days show an empty bar with no value printed on it,
    rather than a misleading '0'."""
    return [bold(fmt.format(v)) if had else "" for v, had in zip(values, has_data)]


def _days_since_threshold(full_history: pd.DataFrame, col: str, threshold: float, dates_shown):
    """For each date, counts calendar days since that metric last hit >=
    threshold (0 on the day it's hit, then 1, 2, 3... on every day after,
    including rest days, until it's hit again). Returns None for any date
    before the metric has ever been hit in the player's known history."""
    s = full_history.set_index("Date")[col].sort_index()
    full_idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
    s = s.reindex(full_idx)  # NaN on rest/no-session days
    counter = None
    daily_counts = {}
    for d in full_idx:
        v = s.loc[d]
        if pd.notna(v) and v >= threshold:
            counter = 0
        elif counter is not None:
            counter += 1
        daily_counts[d] = counter
    return [daily_counts.get(d) for d in dates_shown]


def _to_minutes(t):
    """Converts time representations (Timedelta, string, datetime.time) to minutes."""
    if pd.isna(t):
        return 0
    if isinstance(t, pd.Timedelta):
        return t.total_seconds() / 60
    if hasattr(t, "hour"):
        return t.hour * 60 + t.minute + t.second / 60
    s = str(t).strip()
    if "days" in s:  # pandas Timedelta prints as "0 days 00:12:34"
        s = s.split()[-1]
    try:
        h, m, sec = [float(p) for p in s.split(":")]
        return h * 60 + m + sec / 60
    except Exception:
        return 0


# ---------------------------------------------------------------- Firstbeat daily aggregation
def aggregate_fb_daily(fb_df: pd.DataFrame) -> pd.DataFrame:
    """Collapses multiple Firstbeat sessions on the same calendar date into a
    single row per date: High-Intensity minutes are SUMMED across sessions,
    while Training Effect takes the day's highest session value (TE is a
    peak-stimulus score, not additive).
    Returns columns: Date, _hi_mins, _te."""
    if fb_df.empty:
        return pd.DataFrame({
            "Date": pd.Series(dtype="datetime64[ns]"),
            "_hi_mins": pd.Series(dtype="float64"),
            "_te": pd.Series(dtype="float64"),
        })
    df = fb_df.copy()
    df["_hi_mins"] = df["High intensity training (hh:mm:ss)"].apply(_to_minutes)
    df["_te"] = df[["Aerobic TE (0.0 - 5.0)", "Anaerobic TE (0.0 - 5.0)"]].max(axis=1)
    grouped = df.groupby("Date", as_index=False).agg(
        _hi_mins=("_hi_mins", "sum"),
        _te=("_te", "max"),
    )
    return grouped[["Date", "_hi_mins", "_te"]]


# ---------------------------------------------------------------- Weekly summary helpers
def _week_sort_key(w):
    """Display order: -1, -2, -3, -4, -5, -6, then 1, 2, 3 ..."""
    return (0, abs(w)) if w < 0 else (1, w)


def _weekly_grouped(gps_full_history: pd.DataFrame, week_col="Week Number", how="sum", **agg_cols):
    """Groups full history by Week Number using `how` (sum by default, or max),
    ordered -1, -2, -3, ... then 1, 2, 3, ... regardless of calendar order."""
    hist = gps_full_history.dropna(subset=[week_col]).copy()
    agg = {name: (col, how) for name, col in agg_cols.items()}
    grouped = hist.groupby(week_col).agg(**agg).reset_index()
    grouped["_sort_key"] = grouped[week_col].apply(_week_sort_key)
    grouped = grouped.sort_values("_sort_key").drop(columns="_sort_key")
    return grouped


def _weekly_labels(grouped, week_col="Week Number"):
    return [f"Week {int(w)}" for w in grouped[week_col]]


def _add_divider(fig):
    fig.add_shape(
        type="line", x0=0.5, x1=0.5, xref="x", y0=0, y1=1, yref="paper",
        line=dict(color=WHITE, width=1.5, dash="dot"),
    )


def chart_weekly_single(gps_full_history: pd.DataFrame, value_col: str, avg_value, bar_color: str,
                         week_col="Week Number", fmt="{:.0f}", bullet_marker=None) -> go.Figure:
    """Weekly summary bar: [Average (grey)] | divider | [Week -1] [Week -2] ...
    If avg_value is None, the average is the mean of the player's weekly totals."""
    grouped = _weekly_grouped(gps_full_history, week_col, total=value_col)
    week_labels = _weekly_labels(grouped, week_col)
    week_values = grouped["total"].round(0)
    if avg_value is None:
        avg_value = week_values.mean() if len(week_values) else 0
    x = ["Average"] + week_labels
    y = [avg_value] + list(week_values)
    colors = [GREY] + [bar_color] * len(week_labels)
    text = [bold(fmt.format(v)) for v in y]
    fig = go.Figure()
    fig.add_bar(
        x=x, y=y, marker_color=colors, text=text, textposition="outside",
        textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip",
    )
    fig.update_layout(bargap=_bargap_for(len(x)))
    fig = base_layout(fig, n_dates=len(x))

    max_y = max(y) if y else 1
    if bullet_marker is not None:
        max_y = max(max_y, bullet_marker)

    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    _add_divider(fig)

    if bullet_marker is not None:
        fig.add_hline(
            y=bullet_marker, line_dash="dash", line_color="rgba(255, 255, 255, 0.85)",
            line_width=1.5, annotation_text=bold(f"Max: {bullet_marker:.0f}"),
            annotation_position="top right",
            annotation_font=dict(family=FONT, size=11, color=WHITE),
        )
    return fig


def chart_weekly_hsr_sd(gps_full_history: pd.DataFrame, avg_value, week_col="Week Number", bullet_marker=None) -> go.Figure:
    """Weekly HSR+SD stacked summary: [Average (grey)] | divider |
    [Week -1 (gold HSR + red SD stacked)] ..."""
    hist = gps_full_history.dropna(subset=[week_col]).copy()
    hist["_hsr"] = hist["Velocity Band 4 Total Distance"].fillna(0) + hist["Velocity Band 5 Total Distance"].fillna(0)
    hist["_sd"] = hist["SD"].fillna(0)
    grouped = _weekly_grouped(hist, week_col, hsr="_hsr", sd="_sd")
    week_labels = _weekly_labels(grouped, week_col)
    hsr_week = grouped["hsr"].round(0)
    sd_week = grouped["sd"].round(0)
    if avg_value is None:
        combo_week = hsr_week + sd_week
        avg_value = combo_week.mean() if len(combo_week) else 0
    x = ["Average"] + week_labels
    hsr_y = [avg_value] + list(hsr_week)
    sd_y = [0] + list(sd_week)
    hsr_colors = [GREY] + [GOLD] * len(week_labels)
    sd_colors = [GREY] + [RED] * len(week_labels)
    hsr_text = [bold(f"{avg_value:.0f}")] + [bold(f"{v:.0f}") for v in hsr_week]
    sd_text = [""] + [bold(f"{v:.0f}") for v in sd_week]
    fig = go.Figure()
    fig.add_bar(
        x=x, y=hsr_y, marker_color=hsr_colors, text=hsr_text,
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
        constraintext="none", textangle=0, hoverinfo="skip", name="HSR",
    )
    fig.add_bar(
        x=x, y=sd_y, marker_color=sd_colors, text=sd_text,
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
        constraintext="none", textangle=0, hoverinfo="skip", name="SD",
    )
    fig.update_layout(barmode="stack", bargap=_bargap_for(len(x)))
    fig = base_layout(fig, n_dates=len(x))

    max_y = max(hsr_y[0], max((h + s for h, s in zip(hsr_y[1:], sd_y[1:])), default=0))
    if bullet_marker is not None:
        max_y = max(max_y, bullet_marker)

    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    _add_divider(fig)

    if bullet_marker is not None:
        fig.add_hline(
            y=bullet_marker, line_dash="dash", line_color="rgba(255, 255, 255, 0.85)",
            line_width=1.5, annotation_text=bold(f"Max: {bullet_marker:.0f}"),
            annotation_position="top right",
            annotation_font=dict(family=FONT, size=11, color=WHITE),
        )
    return fig


def chart_weekly_accel_decel(gps_full_history: pd.DataFrame, accel_col: str, decel_col: str,
                              avg_accel=None, avg_decel=None, week_col="Week Number",
                              bullet_marker_accel=None, bullet_marker_decel=None,
                              auto_max=False) -> go.Figure:
    """Weekly Accelerations + Decelerations clustered per week (green/red), with
    a grey Average pair left of the divider. If avg_* is None the average is the
    mean of the player's weekly totals. If auto_max is True and no max is given,
    the max line is the player's highest recorded week."""
    grouped = _weekly_grouped(gps_full_history, week_col, accel=accel_col, decel=decel_col)
    week_labels = _weekly_labels(grouped, week_col)
    accel_week = grouped["accel"].round(0)
    decel_week = grouped["decel"].round(0)

    if avg_accel is None:
        avg_accel = accel_week.mean() if len(accel_week) else 0
    if avg_decel is None:
        avg_decel = decel_week.mean() if len(decel_week) else 0

    if auto_max:
        if bullet_marker_accel is None and len(accel_week):
            bullet_marker_accel = accel_week.max()
        if bullet_marker_decel is None and len(decel_week):
            bullet_marker_decel = decel_week.max()

    x = ["Average"] + week_labels
    accel_y = [avg_accel] + list(accel_week)
    decel_y = [avg_decel] + list(decel_week)
    accel_colors = [GREY] + [GREEN] * len(week_labels)
    decel_colors = [GREY] + [RED] * len(week_labels)
    accel_text = [bold(f"{v:.0f}") for v in accel_y]
    decel_text = [bold(f"{v:.0f}") for v in decel_y]

    fig = go.Figure()
    fig.add_bar(
        x=x, y=accel_y, marker_color=accel_colors, text=accel_text,
        textposition="outside", cliponaxis=False,
        textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
        constraintext="none", textangle=0, hoverinfo="skip", name="Accelerations",
    )
    fig.add_bar(
        x=x, y=decel_y, marker_color=decel_colors, text=decel_text,
        textposition="outside", cliponaxis=False,
        textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
        constraintext="none", textangle=0, hoverinfo="skip", name="Decelerations",
    )
    fig.update_layout(barmode="group", bargap=_bargap_for(len(x)), bargroupgap=0)
    fig = base_layout(fig, n_dates=len(x))

    max_y = max(max(accel_y, default=0), max(decel_y, default=0)) or 1
    if bullet_marker_accel is not None:
        max_y = max(max_y, bullet_marker_accel)
    if bullet_marker_decel is not None:
        max_y = max(max_y, bullet_marker_decel)

    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    _add_divider(fig)

    if bullet_marker_accel is not None:
        fig.add_hline(
            y=bullet_marker_accel, line_dash="dash", line_color=GREEN, line_width=1.5,
            annotation_text=bold(f"Accel Max: {bullet_marker_accel:.0f}"),
            annotation_position="top right",
            annotation_font=dict(family=FONT, size=11, color=WHITE),
        )
    if bullet_marker_decel is not None:
        fig.add_hline(
            y=bullet_marker_decel, line_dash="dash", line_color=RED, line_width=1.5,
            annotation_text=bold(f"Decel Max: {bullet_marker_decel:.0f}"),
            annotation_position="bottom right",
            annotation_font=dict(family=FONT, size=11, color=WHITE),
        )
    return fig


def chart_weekly_hr_hi(fb_daily_full: pd.DataFrame, avg_value=None, week_col="Week Number", bullet_marker=None) -> go.Figure:
    """Weekly minutes above 90% HR Max. Expects one row per date (from
    aggregate_fb_daily) with a Week Number column merged in. Multi-session days
    are summed per day, then all days summed per week."""
    hist = fb_daily_full.dropna(subset=[week_col]).copy()
    grouped = _weekly_grouped(hist, week_col, total="_hi_mins")
    week_labels = _weekly_labels(grouped, week_col)
    week_values = grouped["total"].round(0)

    if avg_value is None:
        avg_value = week_values.mean() if len(week_values) else 0

    x = ["Average"] + week_labels
    y = [avg_value] + list(week_values)
    colors = [GREY] + [RED] * len(week_labels)
    text = [bold(f"{v:.0f}m") for v in y]

    fig = go.Figure()
    fig.add_bar(
        x=x, y=y, marker_color=colors, text=text, textposition="outside",
        textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip",
    )
    fig.update_layout(bargap=_bargap_for(len(x)))
    fig = base_layout(fig, n_dates=len(x))

    max_y = max(y) if y else 1
    if bullet_marker is not None:
        max_y = max(max_y, bullet_marker)

    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    _add_divider(fig)

    if bullet_marker is not None:
        fig.add_hline(
            y=bullet_marker, line_dash="dash", line_color="rgba(255, 255, 255, 0.85)",
            line_width=1.5, annotation_text=bold(f"Max: {bullet_marker:.0f}m"),
            annotation_position="top right",
            annotation_font=dict(family=FONT, size=11, color=WHITE),
        )
    return fig


def player_max_velocity(gps_full_history: pd.DataFrame):
    """A player's true top speed, derived from Max Vel (% Max): if they hit
    7.0 and that was 91% of their max, their max is 7.0 / 0.91. Uses the
    session with the highest % (least rounding error). Falls back to the
    highest recorded velocity if no % data exists."""
    v = pd.to_numeric(gps_full_history["Maximum Velocity"], errors="coerce")
    p = pd.to_numeric(gps_full_history["Max Vel (% Max)"], errors="coerce")
    valid = (v > 0) & (p > 0)
    if valid.any():
        idx = p[valid].idxmax()
        return float(v.loc[idx] * 100 / p.loc[idx])
    return float(v.max()) if v.notna().any() else None


def chart_weekly_max_velocity(gps_full_history: pd.DataFrame, avg_value=None,
                               week_col="Week Number", bullet_marker=None) -> go.Figure:
    """Highest max velocity reached in each week, with a grey Average bar
    (mean of the weekly highs) and a dashed line at the player's true max."""
    grouped = _weekly_grouped(gps_full_history, week_col, how="max", top="Maximum Velocity")
    week_labels = _weekly_labels(grouped, week_col)
    week_values = grouped["top"].round(1)

    if avg_value is None:
        avg_value = round(week_values.mean(), 1) if len(week_values) else 0

    x = ["Average"] + week_labels
    y = [avg_value] + list(week_values)
    colors = [GREY] + [GOLD] * len(week_labels)
    text = [bold(f"{v:.1f}") for v in y]

    fig = go.Figure()
    fig.add_bar(
        x=x, y=y, marker_color=colors, text=text, textposition="outside",
        textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip",
    )
    fig.update_layout(bargap=_bargap_for(len(x)))
    fig = base_layout(fig, n_dates=len(x))

    max_y = max(y) if y else 1
    if bullet_marker is not None:
        max_y = max(max_y, bullet_marker)

    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    _add_divider(fig)

    if bullet_marker is not None:
        fig.add_hline(
            y=bullet_marker, line_dash="dash", line_color="rgba(255, 255, 255, 0.85)",
            line_width=1.5, annotation_text=bold(f"Max: {bullet_marker:.1f}"),
            annotation_position="top right",
            annotation_font=dict(family=FONT, size=11, color=WHITE),
        )
    return fig


# ---------------------------------------------------------------- Chart 1
def chart_total_distance(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame) -> go.Figure:
    x = _x_labels(gps_player)
    has_dist = gps_player["Total Distance"].notna()
    has_mpm = gps_player["Meterage Per Minute"].notna()
    dist = gps_player["Total Distance"].fillna(0).round(0)
    mpm = gps_player["Meterage Per Minute"]  # keep raw NaN - Plotly skips NaN points entirely
    bargap = _bargap_for(len(x))
    fig = go.Figure()
    fig.add_bar(
        x=x, y=dist, marker_color=GREY, text=_bold_labels_masked(dist, has_dist, "{:.0f}"),
        textposition="outside", textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Total Distance",
    )
    fig.add_trace(go.Scatter(
        x=x, y=mpm, mode="markers+text", marker=dict(color=GOLD, size=9, symbol="circle"),
        text=_bold_labels_masked(mpm.fillna(0).round(1), has_mpm, "{:.1f}"), textposition="top center",
        textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        name="Metres / Min", yaxis="y2", cliponaxis=False, hoverinfo="skip",
    ))
    fig.update_layout(bargap=bargap)
    fig = base_layout(fig, n_dates=len(x))
    max_dist = dist.max() if len(dist) else 0
    max_mpm = mpm.max() if len(mpm) else 0
    if pd.isna(max_mpm):
        max_mpm = 0
    dist_range, mpm_range, acwr_y = three_band_ranges(max_dist, max_mpm)
    fig.update_layout(
        yaxis=dict(visible=False, range=dist_range),
        yaxis2=dict(overlaying="y", side="right", visible=False, range=mpm_range),
    )
    hist = gps_full_history.copy()
    acwr_vals = _acwr_for_dates(hist, "Total Distance", gps_player["Date"])
    for xi, v in zip(x, acwr_vals):
        if v is None:
            continue
        bg, txt = acwr_box_color(v)
        fig.add_annotation(
            x=xi, y=acwr_y, xref="x", yref="paper", text=bold(f"{v:.2f}"),
            showarrow=False, font=dict(family=FONT, size=13, color=txt),
            bgcolor=bg, bordercolor=NAVY, borderwidth=1.5, borderpad=4,
            yanchor="middle",
        )
    return fig


# ---------------------------------------------------------------- Chart 1b (Max Speed + Max Speed %)
def chart_max_speed(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame) -> go.Figure:
    x = _x_labels(gps_player)
    has_speed = gps_player["Maximum Velocity"].notna()
    has_pct = gps_player["Max Vel (% Max)"].notna()
    speed = gps_player["Maximum Velocity"].fillna(0).round(1)
    pct = gps_player["Max Vel (% Max)"]  # keep raw NaN - Plotly skips NaN points entirely
    bargap = _bargap_for(len(x))
    fig = go.Figure()
    fig.add_bar(
        x=x, y=speed, marker_color=GREY, text=_bold_labels_masked(speed, has_speed, "{:.1f}"),
        textposition="outside", textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Max Speed",
    )
    fig.add_trace(go.Scatter(
        x=x, y=pct, mode="markers+text", marker=dict(color=GOLD, size=9, symbol="circle"),
        text=_bold_labels_masked(pct.fillna(0).round(0), has_pct, "{:.0f}%"), textposition="top center",
        textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        name="Max Speed %", yaxis="y2", cliponaxis=False, hoverinfo="skip",
    ))
    fig.update_layout(bargap=bargap)
    fig = base_layout(fig, n_dates=len(x))
    max_speed = speed.max() if len(speed) else 0
    max_pct = pct.max() if len(pct) else 0
    if pd.isna(max_pct):
        max_pct = 0
    speed_range, pct_range, box_y = three_band_ranges(max_speed, max_pct)
    fig.update_layout(
        yaxis=dict(visible=False, range=speed_range),
        yaxis2=dict(overlaying="y", side="right", visible=False, range=pct_range),
    )
    hist = gps_full_history.copy()
    streak_vals = _days_since_threshold(hist, "Max Vel (% Max)", 90, gps_player["Date"])
    for xi, v in zip(x, streak_vals):
        if v is None:
            continue
        fig.add_annotation(
            x=xi, y=box_y, xref="x", yref="paper", text=bold(str(v)),
            showarrow=False, font=dict(family=FONT, size=13, color=NAVY),
            bgcolor=WHITE, bordercolor=NAVY, borderwidth=1.5, borderpad=4,
            yanchor="middle",
        )
    return fig


# ---------------------------------------------------------------- Chart 2 (HSR + SD, stacked)
def chart_hsr_sd(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame) -> go.Figure:
    x = _x_labels(gps_player)
    has_hsr = gps_player["Velocity Band 4 Total Distance"].notna() | gps_player["Velocity Band 5 Total Distance"].notna()
    has_sd = gps_player["SD"].notna()
    hsr = (gps_player["Velocity Band 4 Total Distance"].fillna(0)
           + gps_player["Velocity Band 5 Total Distance"].fillna(0)).round(0)
    sd = gps_player["SD"].fillna(0).round(0)
    bargap = _bargap_for(len(x))
    fig = go.Figure()
    fig.add_bar(x=x, y=hsr, marker_color=GOLD, text=_bold_labels_masked(hsr, has_hsr, "{:.0f}"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="HSR")
    fig.add_bar(x=x, y=sd, marker_color=RED, text=_bold_labels_masked(sd, has_sd, "{:.0f}"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="SD")
    fig.update_layout(barmode="stack", bargap=bargap)
    hist = gps_full_history.copy()
    hist["combo"] = (hist["Velocity Band 4 Total Distance"].fillna(0)
                      + hist["Velocity Band 5 Total Distance"].fillna(0)
                      + hist["SD"].fillna(0))
    acwr_vals = _acwr_for_dates(hist, "combo", gps_player["Date"])
    fig = base_layout(fig, n_dates=len(x))
    top = (hsr + sd)
    fig = _apply_value_row(fig, x, acwr_vals, top.max() if len(top) else 0, color_fn=acwr_box_color)
    return fig


# ---------------------------------------------------------------- Chart 3 / 4 (Accel / Decel, clustered)
def chart_accel_decel(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame,
                       accel_col: str, decel_col: str) -> go.Figure:
    x = _x_labels(gps_player)
    has_accel = gps_player[accel_col].notna()
    has_decel = gps_player[decel_col].notna()
    accel = gps_player[accel_col].fillna(0).round(0)
    decel = gps_player[decel_col].fillna(0).round(0)
    bargap = _bargap_for(len(x))
    fig = go.Figure()
    fig.add_bar(x=x, y=accel, marker_color=GREEN, text=_bold_labels_masked(accel, has_accel, "{:.0f}"),
                textposition="outside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Accelerations")
    fig.add_bar(x=x, y=decel, marker_color=RED, text=_bold_labels_masked(decel, has_decel, "{:.0f}"),
                textposition="outside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Decelerations")
    fig.update_layout(barmode="group", bargap=bargap, bargroupgap=0)
    hist = gps_full_history.copy()
    hist["combo"] = hist[accel_col].fillna(0) + hist[decel_col].fillna(0)
    acwr_vals = _acwr_for_dates(hist, "combo", gps_player["Date"])
    fig = base_layout(fig, n_dates=len(x))
    top = pd.concat([accel, decel], axis=1).max(axis=1)
    fig = _apply_value_row(fig, x, acwr_vals, top.max() if len(top) else 0, color_fn=acwr_box_color)
    return fig


# ---------------------------------------------------------------- Chart 5 (High Intensity Minutes - HR > 90% Max)
def chart_hr_zones(fb_player: pd.DataFrame) -> go.Figure:
    """Expects fb_player to be one row per calendar date (built from
    aggregate_fb_daily then merged onto the full calendar), with columns
    Date, Day, _hi_mins, _te - so multi-session days are already summed."""
    x = _x_labels(fb_player)
    bargap = _bargap_for(len(x))

    hi = fb_player["_hi_mins"].fillna(0).round(1)
    has_hi = fb_player["_hi_mins"].notna()

    fig = go.Figure()
    fig.add_bar(
        x=x, y=hi, marker_color=RED,
        text=_bold_labels_masked(hi, has_hi, "{:.0f}m"),
        textposition="outside", cliponaxis=False,
        textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
        constraintext="none", textangle=0, hoverinfo="skip", name=">90% HR Max",
    )
    fig.update_layout(bargap=bargap)

    te_vals = [round(v, 1) if pd.notna(v) else None for v in fb_player["_te"]]

    fig = base_layout(fig, n_dates=len(x))
    fig = _apply_value_row(
        fig, x, te_vals, hi.max() if len(hi) else 0, fmt="{:.1f}", color_fn=te_box_color
    )
    return fig


# ---------------------------------------------------------------- Legend (colour key) definitions
LEGEND_TOTAL_DISTANCE = [(GREY, "Total Distance"), (GOLD, "Metres per Minute")]
LEGEND_MAX_SPEED = [(GREY, "Max Speed"), (GOLD, "Max Speed %")]
LEGEND_HSR_SD = [(GOLD, "HSR"), (RED, "Sprint Distance")]
LEGEND_HR_ZONES = [(RED, ">90% HR Max (High Intensity)")]


def legend_accel_decel(label_suffix):
    return [(GREEN, f"Accelerations ({label_suffix})"), (RED, f"Decelerations ({label_suffix})")]


# ---------------------------------------------------------------- Weekly legends
LEGEND_WEEKLY_TOTAL_DISTANCE = [(GREY, "Average"), (GOLD, "Weekly Total Distance")]
LEGEND_WEEKLY_HSR_SD = [(GREY, "Average"), (GOLD, "HSR"), (RED, "Sprint Distance")]
LEGEND_WEEKLY_ACCEL_DECEL = [(GREY, "Average"), (GREEN, "Weekly Accelerations"), (RED, "Weekly Decelerations")]
LEGEND_WEEKLY_HR_HI = [(GREY, "Average"), (RED, "Weekly High Intensity HR (>90%)")]
LEGEND_WEEKLY_MAX_VEL = [(GREY, "Average"), (GOLD, "Weekly Max Velocity")]
