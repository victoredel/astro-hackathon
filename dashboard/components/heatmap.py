"""
Geomagnetic activity heatmap over prediction horizon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def build_heatmap(predictions_df: pd.DataFrame) -> go.Figure:
    """
    Build a heatmap of storm probability over time.

    Expected columns: generated_at, storm_probability, alert_level
    """
    if predictions_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title="No prediction data yet",
            paper_bgcolor="rgba(13,17,35,0)",
            font={"color": "#e0e8ff"},
            height=200,
        )
        return fig

    df = predictions_df.copy().sort_values("generated_at")
    times = df["generated_at"].tolist()
    probs = df["storm_probability"].tolist()

    # Create 2D matrix: rows = intensity buckets, cols = time
    buckets = ["Kp 0-2\n(Quiet)", "Kp 3-4\n(Unsettled)", "Kp 5-6\n(Storm)", "Kp 7+\n(Severe)"]
    thresholds = [0.15, 0.40, 0.70, 0.90]
    n_buckets = len(buckets)
    n_times = len(times)

    z = np.zeros((n_buckets, n_times))
    for t_idx, prob in enumerate(probs):
        for b_idx, thresh in enumerate(thresholds):
            z[b_idx, t_idx] = max(0.0, prob - thresh) / (1 - thresh + 1e-6)

    fig = go.Figure(go.Heatmap(
        x=times,
        y=buckets,
        z=z,
        colorscale=[
            [0.0, "rgba(0,14,50,0.9)"],
            [0.3, "rgba(0,100,180,0.9)"],
            [0.6, "rgba(255,214,0,0.9)"],
            [0.85, "rgba(255,80,0,0.9)"],
            [1.0, "rgba(255,23,68,1.0)"],
        ],
        showscale=True,
        colorbar={
            "title": "Intensity",
            "titlefont": {"color": "#e0e8ff"},
            "tickfont": {"color": "#8892a4"},
            "bgcolor": "rgba(0,0,0,0)",
            "outlinecolor": "rgba(0,0,0,0)",
        },
        hovertemplate="Time: %{x}<br>Level: %{y}<br>Intensity: %{z:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title={"text": "Geomagnetic Activity Forecast Heatmap", "font": {"color": "#e0e8ff", "size": 14}},
        paper_bgcolor="rgba(13,17,35,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        font={"color": "#e0e8ff", "family": "Inter, sans-serif"},
        margin={"t": 50, "b": 20, "l": 100, "r": 20},
        height=220,
        xaxis={"gridcolor": "rgba(255,255,255,0.05)", "showgrid": True},
        yaxis={"gridcolor": "rgba(255,255,255,0.05)"},
    )
    return fig
