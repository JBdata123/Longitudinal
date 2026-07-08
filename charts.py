"""
Builds the 5 plotly figures for the Longitudinal Report page, in the
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


# ---------------------------------------------------------------- Chart 1
def chart_total_distance(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame) -> go.Figure:
    x = _x_labels(gps_player)
    has_data = gps_player["Total Distance"].notna()
    dist = gps_player["Total Distance"].fillna(0).round(0)
    mpm = gps_player["Meterage Per Minute"]  # keep raw NaN - Plotly skips NaN points entirely
    bargap = _bargap_for(len(x))

    fig = go.Figure()
    fig.add_bar(
        x=x, y=dist, marker_color=GREY, text=_bold_labels_masked(dist, has_data, "{:.0f}"),
        textposition="outside", textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Total Distance",
    )
    fig.add_trace(go.Scatter(
        x=x, y=mpm, mode="markers+text", marker=dict(color=GOLD, size=9, symbol="circle"),
        text=_bold_labels_masked(mpm.fillna(0).round(1), has_data, "{:.1f}"), textposition="top center",
        textfont=dict(color=WHITE, size=VALUE_FONT_SIZE, family=FONT),
        name="Metres / Min", yaxis="y2", cliponaxis=False, hoverinfo="skip",
    ))
    fig.update_layout(bargap=bargap)
    fig = base_layout(fig)

    max_dist = dist.max() if len(dist) else 0
    max_mpm = mpm.max() if len(mpm) else 0
    if pd.isna(max_mpm):
        max_mpm = 0
    dist_range, mpm_range, acwr_y = three_band_ranges(max_dist, max_mpm)
    fig.update_layout(
        yaxis=dict(visible=False, range=dist_range),
        yaxis2=dict(overlaying="y", side="right", visible=False, range=mpm_range),
    )

    # ACWR row for Total Distance, same box formatting as the other charts,
    # sitting in its own strip at a fixed height (paper-relative) above both
    # the bars and the metres/min dots.
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


# ---------------------------------------------------------------- Chart 2 (HSR + SD, stacked)
def chart_hsr_sd(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame) -> go.Figure:
    x = _x_labels(gps_player)
    has_data = gps_player["Total Distance"].notna()
    hsr = (gps_player["Velocity Band 4 Total Distance"].fillna(0)
           + gps_player["Velocity Band 5 Total Distance"].fillna(0)).round(0)
    sd = gps_player["SD"].fillna(0).round(0)
    bargap = _bargap_for(len(x))

    fig = go.Figure()
    fig.add_bar(x=x, y=hsr, marker_color=GOLD, text=_bold_labels_masked(hsr, has_data, "{:.0f}"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="HSR")
    fig.add_bar(x=x, y=sd, marker_color=RED, text=_bold_labels_masked(sd, has_data, "{:.0f}"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="SD")
    fig.update_layout(barmode="stack", bargap=bargap)

    hist = gps_full_history.copy()
    hist["combo"] = (hist["Velocity Band 4 Total Distance"].fillna(0)
                      + hist["Velocity Band 5 Total Distance"].fillna(0)
                      + hist["SD"].fillna(0))
    acwr_vals = _acwr_for_dates(hist, "combo", gps_player["Date"])

    fig = base_layout(fig)
    top = (hsr + sd)
    fig = _apply_value_row(fig, x, acwr_vals, top.max() if len(top) else 0, color_fn=acwr_box_color)
    return fig


# ---------------------------------------------------------------- Chart 3 / 4 (Accel / Decel, clustered)
def chart_accel_decel(gps_player: pd.DataFrame, gps_full_history: pd.DataFrame,
                       accel_col: str, decel_col: str) -> go.Figure:
    x = _x_labels(gps_player)
    has_data = gps_player["Total Distance"].notna()
    accel = gps_player[accel_col].fillna(0).round(0)
    decel = gps_player[decel_col].fillna(0).round(0)
    bargap = _bargap_for(len(x))

    fig = go.Figure()
    fig.add_bar(x=x, y=accel, marker_color=GREEN, text=_bold_labels_masked(accel, has_data, "{:.0f}"),
                textposition="outside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Accelerations")
    fig.add_bar(x=x, y=decel, marker_color=RED, text=_bold_labels_masked(decel, has_data, "{:.0f}"),
                textposition="outside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", cliponaxis=False, textangle=0, hoverinfo="skip", name="Decelerations")
    # barmode group + bargroupgap=0 -> the two bars in each date-pair sit flush together
    fig.update_layout(barmode="group", bargap=bargap, bargroupgap=0)

    hist = gps_full_history.copy()
    hist["combo"] = hist[accel_col].fillna(0) + hist[decel_col].fillna(0)
    acwr_vals = _acwr_for_dates(hist, "combo", gps_player["Date"])

    fig = base_layout(fig)
    top = pd.concat([accel, decel], axis=1).max(axis=1)
    fig = _apply_value_row(fig, x, acwr_vals, top.max() if len(top) else 0, color_fn=acwr_box_color)
    return fig


# ---------------------------------------------------------------- Chart 5 (HR zones, stacked)
def chart_hr_zones(fb_player: pd.DataFrame) -> go.Figure:
    x = _x_labels(fb_player)
    bargap = _bargap_for(len(x))

    def _to_minutes(t):
        if pd.isna(t):
            return 0
        if isinstance(t, pd.Timedelta):
            return t.total_seconds() / 60
        if hasattr(t, "hour"):
            return t.hour * 60 + t.minute + t.second / 60
        s = str(t).strip()
        if "days" in s:  # pandas Timedelta prints as "0 days 00:12:34"
            s = s.split()[-1]
        h, m, sec = [float(p) for p in s.split(":")]
        return h * 60 + m + sec / 60

    def to_min(col):
        return fb_player[col].apply(_to_minutes).round(1)

    aer2 = to_min("Aerobic zone 2 (hh:mm:ss)")     # 70-79% HR Max
    anth = to_min("Anaerobic threshold zone (hh:mm:ss)")  # 80-89% HR Max
    hi = to_min("High intensity training (hh:mm:ss)")     # 90%+ HR Max
    has_data = fb_player["Aerobic zone 2 (hh:mm:ss)"].notna()

    fig = go.Figure()
    fig.add_bar(x=x, y=aer2, marker_color=DARK_GOLD, text=_bold_labels_masked(aer2, has_data, "{:.0f}m"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="70-79% HR Max")
    fig.add_bar(x=x, y=anth, marker_color=GOLD, text=_bold_labels_masked(anth, has_data, "{:.0f}m"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="80-89% HR Max")
    fig.add_bar(x=x, y=hi, marker_color=RED, text=_bold_labels_masked(hi, has_data, "{:.0f}m"),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=VALUE_FONT_SIZE, color=WHITE, family=FONT),
                constraintext="none", textangle=0, hoverinfo="skip", name="90%+ HR Max")
    fig.update_layout(barmode="stack", bargap=bargap)

    top = aer2 + anth + hi
    te_max = fb_player[["Aerobic TE (0.0 - 5.0)", "Anaerobic TE (0.0 - 5.0)"]].max(axis=1)
    te_vals = [round(v, 1) if pd.notna(v) else None for v in te_max]

    fig = base_layout(fig)
    fig = _apply_value_row(fig, x, te_vals, top.max() if len(top) else 0, fmt="{:.1f}", color_fn=te_box_color)
    return fig


# ---------------------------------------------------------------- Legend (colour key) definitions
LEGEND_TOTAL_DISTANCE = [(GREY, "Total Distance"), (GOLD, "Metres per Minute")]
LEGEND_HSR_SD = [(GOLD, "HSR"), (RED, "Sprint Distance")]
LEGEND_HR_ZONES = [(DARK_GOLD, "70-79% HR Max"), (GOLD, "80-89% HR Max"), (RED, "90%+ HR Max")]


def legend_accel_decel(label_suffix):
    return [(GREEN, f"Accelerations ({label_suffix})"), (RED, f"Decelerations ({label_suffix})")]