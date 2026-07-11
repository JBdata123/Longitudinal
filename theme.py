"""
LCFC brand palette + small shared helpers used across the dashboard.
"""
import pandas as pd

# ---- Brand colours ----
NAVY = "#003090"          # LCFC blue - panel backgrounds
NAVY_DARK = "#001F5C"     # header bar / darker navy
GOLD = "#FDBE11"          # LCFC gold - dots, headline accents
WHITE = "#FFFFFF"
RED = "#FF0000"           # accent red (HSR / decel / high intensity)
GREEN = "#35AC35"         # accent green (accel)
GREY = "#BFBFBF"          # Total Distance bars
DARK_GOLD = "#9C7A0A"     # darker gold for Aerobic Zone 2

FONT = "'Segoe UI', Arial, sans-serif"

PLOTLY_TRANSPARENT = "rgba(0,0,0,0)"

# ACWR windows: acute (short-term) vs chronic (long-term), exponentially weighted
ACWR_ACUTE_SPAN = 7
ACWR_CHRONIC_SPAN = 28


def day_axis_label(date, day_type):
    """Two-line, centred x-axis label: date on top, day type underneath
    (Plotly renders '<br>' as a real line break in tick labels, and
    category-axis ticks are centre-anchored by default). Rest days with no
    day type just show the bare date on its own."""
    date_str = date.strftime('%d/%m')
    if day_type is None or (isinstance(day_type, float) and pd.isna(day_type)) or day_type == "":
        return date_str
    return f"{date_str}<br>{day_type}"


def base_layout(fig, height=340, n_dates=None):
    """Apply the shared LCFC look to a plotly figure: navy panel, white text,
    no gridlines, Arial font, white x-axis labels sized to fit - smaller as
    more dates are on screen so long date ranges don't get jumbled."""
    if n_dates:
        tick_size = max(7, min(11, 11 - (n_dates - 8) * 0.2))
    else:
        tick_size = 10
    fig.update_layout(
        plot_bgcolor=NAVY,
        paper_bgcolor=NAVY,
        font=dict(family=FONT, color=WHITE, size=12),
        margin=dict(l=30, r=30, t=50, b=42),
        height=height,
        showlegend=False,
        xaxis=dict(showgrid=False, color=WHITE, tickfont=dict(size=tick_size, color=WHITE), tickangle=0),
        yaxis=dict(showgrid=False, color=WHITE, zeroline=False, visible=False),
        hovermode=False,
    )
    return fig


def metric_title_bar(title):
    """White title bar sitting above each navy chart panel - centred text."""
    return f"""
    <div style="
        background-color:{WHITE};
        border:2px solid {NAVY};
        border-radius:4px;
        padding:8px 14px;
        margin-bottom:0px;
        font-family:{FONT};
        font-weight:700;
        color:{NAVY};
        font-size:16px;
        text-align:center;">
        {title}
    </div>
    """


def acwr_box_color(v):
    """Green if within the healthy 0.8-1.3 band, red otherwise."""
    if v is None:
        return WHITE, NAVY
    return (GREEN, WHITE) if 0.8 <= v <= 1.3 else (RED, WHITE)


def te_box_color(v):
    """Training Effect colour bands: <2.0 red, 2.0-2.9 gold, 3.0+ green.
    Text is always white, whatever the box colour."""
    if v is None:
        return WHITE, WHITE
    if v < 2.0:
        return RED, WHITE
    if v < 3.0:
        return GOLD, WHITE
    return GREEN, WHITE


def value_box_row(fig, x, values, y_pos, fmt="{:.2f}", color_fn=None):
    """Adds a row of small boxes sitting in their own strip above the bars -
    one per x category - showing ACWR / TE values. `y_pos` is a single fixed
    y (data units) so the whole row sits dead level regardless of each bar's
    own height. `color_fn(value) -> (bg_color, text_color)` colour-codes each
    box (e.g. green/red for ACWR); omit for the plain white/navy look."""
    for xi, v in zip(x, values):
        if v is None:
            continue
        if color_fn:
            bg, txt = color_fn(v)
        else:
            bg, txt = WHITE, NAVY
        fig.add_annotation(
            x=xi, y=y_pos, text=bold(fmt.format(v)), showarrow=False,
            font=dict(family=FONT, size=13, color=txt),
            bgcolor=bg, bordercolor=NAVY, borderwidth=1.5, borderpad=4,
            yanchor="middle",
        )
    return fig


def three_band_ranges(max_dist, max_mpm):
    """For Chart 1 (Total Distance bars + Metres/Min dots + ACWR row) - returns
    (dist_yaxis_range, mpm_yaxis2_range, acwr_paper_y) so the three sit in
    clearly separated vertical bands with real gaps between them:
      - bars + their value labels sit in the bottom ~0-40% band
      - metres/min dots + labels sit in the middle ~50-80% band
      - the ACWR box row floats in its own strip near the very top
    """
    if max_dist <= 0:
        max_dist = 1
    if max_mpm <= 0:
        max_mpm = 1
    dist_range = [0, max_dist / 0.35]          # bars occupy bottom ~35-40% incl. label
    mpm_range = [-1.667 * max_mpm, 1.667 * max_mpm]  # dots+labels occupy ~50-80%
    acwr_paper_y = 0.97
    return dist_range, mpm_range, acwr_paper_y


def bold(text):
    """Wrap a value in Plotly's supported <b> markup so it renders bold
    reliably regardless of Plotly/browser font-weight support."""
    return f"<b>{text}</b>"


def headroom_range(max_value, value_row_frac=0.80, top_pad_frac=1.22):
    """Given the tallest bar value, returns (yaxis_max, value_row_y) so that:
    - bars occupy roughly the bottom `value_row_frac` of the plot
    - the ACWR/TE box row sits above that, with clear air beneath it
    - nothing (labels or boxes) touches the very top of the panel."""
    if max_value <= 0:
        max_value = 1
    yaxis_max = max_value * top_pad_frac / value_row_frac
    value_row_y = yaxis_max * (value_row_frac + (1 - value_row_frac) * 0.5)
    return yaxis_max, value_row_y


def legend_row(items, box_note=None):
    """Small colour-key row: a coloured dot + label per series, e.g.
    items = [(GREEN, "Accelerations (1-3)"), (RED, "Decelerations (1-3)")].
    Sits between the white title bar and the navy chart panel.
    `box_note` (e.g. "ACWR" or "Training Effect") adds an extra swatch
    showing what the small floating box above the bars represents."""
    dots = "".join(
        f'<span style="display:inline-flex; align-items:center; margin:0 12px;">'
        f'<span style="width:10px; height:10px; border-radius:50%; '
        f'background:{color}; display:inline-block; margin-right:6px; '
        f'border:1px solid {WHITE};"></span>'
        f'<span style="color:{WHITE}; font-family:{FONT}; font-size:12px; '
        f'font-weight:600;">{label}</span></span>'
        for color, label in items
    )
    box_html = ""
    if box_note:
        box_html = (
            f'<span style="display:inline-flex; align-items:center; margin:0 12px; '
            f'padding-left:12px; border-left:1px solid rgba(255,255,255,0.35);">'
            f'<span style="width:16px; height:11px; background:{WHITE}; '
            f'border:1.5px solid {NAVY}; border-radius:2px; display:inline-block; '
            f'margin-right:6px;"></span>'
            f'<span style="color:{WHITE}; font-family:{FONT}; font-size:12px; '
            f'font-weight:600;">Box = {box_note}</span></span>'
        )
    return f"""
    <div style="background-color:{NAVY}; padding:6px 10px 4px 10px;
                text-align:center;">
        {dots}{box_html}
    </div>
    """