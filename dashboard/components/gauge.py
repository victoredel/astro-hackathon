"""
Plotly gauge component for storm probability display.
"""
from __future__ import annotations

import plotly.graph_objects as go


def build_gauge(probability: float, alert_level: str, confidence: float) -> go.Figure:
    """
    Build a Plotly indicator gauge showing storm probability.

    Args:
        probability:  0.0–1.0 storm probability
        alert_level:  "NORMAL" | "WARNING" | "CRITICAL"
        confidence:   0.0–1.0 model confidence

    Returns:
        Plotly Figure
    """
    pct = probability * 100

    color_map = {
        "NORMAL": "#00e676",
        "WARNING": "#ffd600",
        "CRITICAL": "#ff1744",
    }
    needle_color = color_map.get(alert_level, "#00e676")

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pct,
        number={"suffix": "%", "font": {"size": 48, "color": needle_color}},
        delta={
            "reference": 40,
            "increasing": {"color": "#ff1744"},
            "decreasing": {"color": "#00e676"},
            "font": {"size": 16},
        },
        gauge={
            "axis": {
                "range": [0, 100],
                "tickwidth": 2,
                "tickcolor": "#8892a4",
                "tickfont": {"color": "#8892a4"},
            },
            "bar": {"color": needle_color, "thickness": 0.3},
            "bgcolor": "rgba(255,255,255,0.05)",
            "borderwidth": 2,
            "bordercolor": "#2a3550",
            "steps": [
                {"range": [0, 40], "color": "rgba(0,230,118,0.15)"},
                {"range": [40, 70], "color": "rgba(255,214,0,0.15)"},
                {"range": [70, 100], "color": "rgba(255,23,68,0.15)"},
            ],
            "threshold": {
                "line": {"color": needle_color, "width": 4},
                "thickness": 0.85,
                "value": pct,
            },
        },
        title={
            "text": f"Storm Probability<br><span style='font-size:0.75em;color:#8892a4'>Confidence: {confidence*100:.0f}%</span>",
            "font": {"size": 20, "color": "#e0e8ff"},
        },
    ))

    fig.update_layout(
        paper_bgcolor="rgba(13,17,35,0)",
        font={"color": "#e0e8ff", "family": "Inter, sans-serif"},
        margin={"t": 80, "b": 20, "l": 30, "r": 30},
        height=280,
    )
    return fig
