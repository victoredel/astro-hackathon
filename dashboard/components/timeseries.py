"""
Multi-line time-series chart for solar wind parameters.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_timeseries(df: pd.DataFrame) -> go.Figure:
    """
    Güneş rüzgarı parametreleri için çok panelli zaman serisi grafiği oluşturur.
    """
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=["Bz GSE (nT)", "Güneş Rüzgarı Hızı (km/s)", "Proton Yoğunluğu (p/cc)"],
    )

    # ── Bz ─────────────────
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["bz_gse"],
        name="Bz GSE",
        line={"color": "#4dd0e1", "width": 2},
        fill="tozeroy",
        fillcolor="rgba(77,208,225,0.08)",
    ), row=1, col=1)

    # Fırtına eşiği çizgisi
    fig.add_hline(y=-10, line_dash="dash", line_color="#ff1744", opacity=0.5, row=1, col=1)
    fig.add_annotation(
        text="Fırtına eşiği (−10 nT)", x=df["timestamp"].iloc[-1],
        y=-10, showarrow=False, font={"color": "#ff1744", "size": 10},
        xanchor="right", row=1, col=1,
    )

    # ── Hız ──────────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["speed"],
        name="Hız",
        line={"color": "#ffb300", "width": 2},
    ), row=2, col=1)

    # ── Yoğunluk ────────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["density"],
        name="Yoğunluk",
        line={"color": "#ab47bc", "width": 2},
        fill="tozeroy",
        fillcolor="rgba(171,71,188,0.08)",
    ), row=3, col=1)

    fig.update_layout(
        paper_bgcolor="rgba(13,17,35,0)",
        plot_bgcolor="rgba(255,255,255,0.03)",
        font={"color": "#e0e8ff", "family": "Inter, sans-serif", "size": 11},
        legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#e0e8ff"}},
        margin={"t": 40, "b": 20, "l": 60, "r": 20},
        height=400,
        hovermode="x unified",
    )
    fig.update_xaxes(
        tickformat="%H:%M",
        nticks=8,
        showgrid=True,
        gridcolor="rgba(255,255,255,0.05)",
        zeroline=False,
    )
    fig.update_yaxes(
        gridcolor="rgba(255,255,255,0.05)",
        showgrid=True,
        zeroline=True,
        zerolinecolor="rgba(255,255,255,0.15)",
    )
    return fig
