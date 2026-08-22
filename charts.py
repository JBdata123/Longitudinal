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
    before the metric has ever been hit in the player's known history, since
    we can't truthfully claim a 'days since' figure without a real reference
    point."""
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


# ---------------------------------------------------------------- Weekly summary helpers
def _weekly_grouped(gps_full_history: pd.DataFrame, week_col="Week Number", **agg_cols):
    """Groups full history by Week Number, sums the requested value column(s),
    and orders weeks chronologically by each week's earliest date (not by the
    raw week number, since preseason numbering counts down as time moves
    forward: -1, -2, -3...)."""
    hist = gps_full_history.dropna(subset=[week_col]).copy()
    agg = {name: (col, "sum") for name, col in agg_cols.items()}
    agg["first_date"] = ("Date", "min")
    grouped = hist.groupby(week_col).agg(**agg).reset_index()
    return grouped.sort_values("first_date")


def _weekly_labels(grouped, week_col="Week Number"):
    return [f"Week {int(w)}" for w in grouped[week_col]]


def chart_weekly_single(gps_full_history: pd.DataFrame, value_col: str, avg_value, bar_color: str,
                         week_col="Week Number", fmt="{:.0f}") -> go.Figure:
    """Weekly summary bar: [Average (grey)] | divider | [Week -1] [Week -2] ...
    If avg_value is None, the average is computed live as the mean of this
    player's own weekly totals so far, rather than a fixed hardcoded value."""
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
    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    fig.add_shape(
        type="line", x0=0.5, x1=0.5, xref="x", y0=0, y1=1, yref="paper",
        line=dict(color=WHITE, width=1.5, dash="dot"),
    )
    return fig


def chart_weekly_hsr_sd(gps_full_history: pd.DataFrame, avg_value, week_col="Week Number") -> go.Figure:
    """Weekly HSR+SD stacked summary: [Average (grey, single block)] | divider |
    [Week -1 (gold HSR + red SD stacked)] [Week -2] ...
    If avg_value is None, the average is computed live as the mean of this
    player's own weekly (HSR+SD) totals so far, rather than a fixed value."""
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
    fig.update_layout(yaxis=dict(visible=False, range=[0, max_y / 0.75]))
    fig.add_shape(
        type="line", x0=0.5, x1=0.5, xref="x", y0=0, y1=1, yref="paper",
        line=dict(color=WHITE, width=1.5, dash="dot"),
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
