"""
Uncertainty cone / fan chart showing prediction confidence bounds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta


def build_cone(predictions_df: pd.DataFrame, horizon_minutes: int = 30) -> go.Figure:
    """
    Koni çizimi için tahmin belirsizliğini görselleştirir.
    """
    if predictions_df.empty or len(predictions_df) < 2:
        fig = go.Figure()
        fig.update_layout(
            title="Koni çizimi için yetersiz veri",
            paper_bgcolor="rgba(13,17,35,0)",
            font={"color": "#e0e8ff"},
            height=200,
        )
        return fig

    df = predictions_df.copy().sort_values("generated_at").tail(60)
    times = pd.to_datetime(df["generated_at"])
    probs = df["storm_probability"].values
    confs = df["confidence_score"].values

    last_time = times.iloc[-1]
    future_time = last_time + timedelta(minutes=horizon_minutes)

    upper = np.minimum(probs + (1.0 - confs) * probs, 1.0)
    lower = np.maximum(probs - (1.0 - confs) * probs, 0.0)

    slope = (probs[-1] - probs[-2]) if len(probs) >= 2 else 0
    future_prob = float(np.clip(probs[-1] + slope * horizon_minutes / len(probs), 0, 1))
    future_conf = float(confs[-1])

    ext_times = list(times) + [future_time]
    ext_probs = list(probs) + [future_prob]
    ext_upper = list(upper) + [min(future_prob + (1 - future_conf) * future_prob, 1.0)]
    ext_lower = list(lower) + [max(future_prob - (1 - future_conf) * future_prob, 0.0)]

    fig = go.Figure()

    # Güven Bandı
    fig.add_trace(go.Scatter(
        x=ext_times + ext_times[::-1],
        y=ext_upper + ext_lower[::-1],
        fill="toself",
        fillcolor="rgba(100,181,246,0.12)",
        line={"color": "rgba(0,0,0,0)"},
        name="Güven Bandı",
        hoverinfo="skip",
    ))

    # Fırtına Olasılığı
    fig.add_trace(go.Scatter(
        x=ext_times,
        y=ext_probs,
        name="Fırtına Olasılığı",
        line={"color": "#64b5f6", "width": 2.5, "dash": "solid"},
        mode="lines+markers",
        marker={"size": 4},
    ))

    last_date = pd.to_datetime(last_time)
    v_line_pos = last_date.timestamp() * 1000

    fig.add_vline(
        x=v_line_pos, 
        line_dash="dash", 
        line_color="rgba(255,255,255,0.5)",
        annotation_text="TAHMİN UFUK ÇİZGİSİ"
    )

    fig.add_hline(y=0.7, line_dash="dash", line_color="rgba(255,23,68,0.4)", opacity=0.7)

    fig.update_layout(
        title={"text": "Tahmin Belirsizlik Konisi", "font": {"color": "#e0e8ff", "size": 14}},
        paper_bgcolor="rgba(13,17,35,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        font={"color": "#e0e8ff", "family": "Inter, sans-serif"},
        legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#e0e8ff"}},
        margin={"t": 50, "b": 40, "l": 60, "r": 20},
        height=250,
        xaxis={"title": "Zaman (UTC)", "gridcolor": "rgba(255,255,255,0.05)"},
        yaxis={"title": "Olasılık", "range": [0, 1.05], "gridcolor": "rgba(255,255,255,0.05)"},
        hovermode="x unified",
    )
    return fig
