"""
Solar Storm Early Warning — Time-Lapse AI Dashboard
TUA Astro Hackathon 2026

Main Streamlit application. Polls the FastAPI backend every 5 seconds
and renders a live dashboard showing storm probability, solar wind
parameters, heatmaps, and an uncertainty cone chart.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import random
import time
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd
import streamlit as st

from pipeline.cognitive_ldpc import simulate_deep_space_transmission
from pipeline.terrestrial_impact import calculate_terrestrial_impact

# ── Page configuration ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="☀ Solar Storm Early Warning",
    page_icon="🌩",
    layout="wide",
    initial_sidebar_state="expanded",
)

if 'ldpc_sim_result' not in st.session_state:
    st.session_state.ldpc_sim_result = None
if 'terrestrial_sim_result' not in st.session_state:
    st.session_state.terrestrial_sim_result = None

# ── Dark space theme CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: radial-gradient(ellipse at top left, #0a1628 0%, #060d1f 50%, #03070f 100%);
    min-height: 100vh;
}

/* Header */
.solar-header {
    background: linear-gradient(135deg, rgba(255,100,0,0.1), rgba(100,0,255,0.1));
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 20px 30px;
    margin-bottom: 20px;
    backdrop-filter: blur(10px);
}

/* Metric cards */
.metric-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    transition: all 0.3s ease;
}

/* Alert banners */
.alert-normal {
    background: linear-gradient(135deg, rgba(0,230,118,0.1), rgba(0,200,100,0.05));
    border: 1px solid rgba(0,230,118,0.3);
    border-radius: 12px;
    padding: 12px 20px;
    color: #00e676;
    font-weight: 600;
    font-size: 1.2rem;
    text-align: center;
}

.alert-warning {
    background: linear-gradient(135deg, rgba(255,214,0,0.15), rgba(255,160,0,0.05));
    border: 1px solid rgba(255,214,0,0.4);
    border-radius: 12px;
    padding: 12px 20px;
    color: #ffd600;
    font-weight: 700;
    font-size: 1.2rem;
    text-align: center;
    animation: pulse-warn 1.5s ease-in-out infinite;
}

.alert-critical {
    background: linear-gradient(135deg, rgba(255,23,68,0.2), rgba(200,0,50,0.1));
    border: 2px solid rgba(255,23,68,0.6);
    border-radius: 12px;
    padding: 12px 20px;
    color: #ff1744;
    font-weight: 700;
    font-size: 1.3rem;
    text-align: center;
    animation: pulse-crit 0.8s ease-in-out infinite;
    box-shadow: 0 0 20px rgba(255,23,68,0.3);
}

@keyframes pulse-warn {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

@keyframes pulse-crit {
    0%, 100% { opacity: 1; box-shadow: 0 0 20px rgba(255,23,68,0.3); }
    50% { opacity: 0.85; box-shadow: 0 0 40px rgba(255,23,68,0.6); }
}

/* Section labels */
.section-label {
    color: #8892a4;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 8px;
}

/* Streamlit element overrides */
[data-testid="metric-container"] {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 12px;
}

div[data-testid="stMetricValue"] {
    font-family: 'Space Mono', monospace !important;
    font-size: 1.8rem !important;
}

.stSidebar [data-testid="stSidebarContent"] {
    background: rgba(6,14,32,0.95);
}
</style>
""", unsafe_allow_html=True)

# ── Configuration ──────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
REFRESH_SECS = 5
HISTORY_LIMIT = 120  # last 2 hours of predictions


# ── Data fetching ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=REFRESH_SECS)
def fetch_latest() -> dict:
    try:
        r = httpx.get(f"{API_BASE}/predict/latest", timeout=5.0)
        r.raise_for_status()
        return r.json()
    except Exception:  # noqa: BLE001
        return {
            "storm_probability": 0.0,
            "confidence_score": 0.0,
            "alert_level": "NORMAL",
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "target_timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "kp_index_estimate": None,
            "horizon_minutes": 30,
        }


@st.cache_data(ttl=REFRESH_SECS)
def fetch_history() -> pd.DataFrame:
    try:
        r = httpx.get(f"{API_BASE}/predict/history", params={"limit": HISTORY_LIMIT}, timeout=5.0)
        r.raise_for_status()
        preds = r.json().get("predictions", [])
        if not preds:
            return pd.DataFrame()
        df = pd.DataFrame(preds)
        df["generated_at"] = pd.to_datetime(df["generated_at"])
        df["target_timestamp"] = pd.to_datetime(df["target_timestamp"])
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=REFRESH_SECS)
def fetch_telemetry_history() -> pd.DataFrame:
    """Fetch telemetry records from DB via a helper endpoint (or return synthetic demo data)."""
    try:
        r = httpx.get(f"{API_BASE}/telemetry/history", params={"limit": HISTORY_LIMIT}, timeout=5.0)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data.get("records", []))
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    except Exception:  # noqa: BLE001
        # Return synthetic demo data for standalone dashboard display
        import numpy as np
        rng = np.random.default_rng(int(time.time()) % 1000)
        n = 60
        times = pd.date_range(end=datetime.now(tz=timezone.utc), periods=n, freq="1min")
        return pd.DataFrame({
            "timestamp": times,
            "bz_gse": rng.normal(-8, 5, n),
            "speed": rng.normal(550, 80, n),
            "density": rng.normal(12, 4, n),
        })


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controls")
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_rate = st.slider("Refresh interval (s)", 2, 30, REFRESH_SECS)
    st.divider()
    st.markdown("### 🛰 Data Sources")
    st.markdown("- **DSCOVR L1** (primary)\n- **ACE** (secondary)\n- **NOAA SWPC** real-time JSON")
    st.markdown("""
<div style="margin-top:10px;font-size:0.82rem;font-family:'Space Mono',monospace;line-height:1.9;">
🟢 DSCOVR Link: <b>ACTIVE</b> | Ping: 45ms<br>
🟢 ACE Fallback: <b>STANDBY</b> | Ping: 61ms<br>
🟡 GOES-18 Aux: <b>DEGRADED</b> | Ping: 120ms<br>
🟢 NOAA API: <b>ACTIVE</b> | Latency: 38ms
</div>
""", unsafe_allow_html=True)
    st.divider()
    st.markdown("### 🤖 Model")
    st.markdown("- SolarTransformer (6L/8H/512d)\n- LoRA fine-tuning (r=16)\n- WGAN-GP augmentation")
    st.divider()
    if st.button("🔴 Simulate CRITICAL Storm"):
        try:
            import requests; requests.delete("http://api:8000/ingest/window?minutes=60")
            now = datetime.now(tz=timezone.utc)
            for i in range(60):
                record = {
                    "timestamp": (now - timedelta(minutes=i)).isoformat(),
                    "source": "DSCOVR",
                    "bx_gse": 3.2,
                    "by_gse": -5.1,
                    "bz_gse": random.uniform(-60.0, -45.0),
                    "speed": random.uniform(800.0, 1100.0),
                    "density": random.uniform(30.0, 50.0),
                    "temperature": 250000.0,
                }
                httpx.post(f"{API_BASE}/ingest", json=record, timeout=8.0)
            
            st.success("Storm injected! ⚡")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Could not reach API: {e}")

    if st.button("🟢 Simulate QUIET Period"):
        try:
            import requests; requests.delete("http://api:8000/ingest/window?minutes=60")
            now = datetime.now(tz=timezone.utc)
            for i in range(60):
                record = {
                    "timestamp": (now - timedelta(minutes=i)).isoformat(),
                    "source": "DSCOVR",
                    "bx_gse": 0.5,
                    "by_gse": 1.2,
                    "bz_gse": random.uniform(0.5, 3.5),
                    "speed": random.uniform(300.0, 400.0),
                    "density": random.uniform(2.0, 8.0),
                    "temperature": 90000.0,
                }
                httpx.post(f"{API_BASE}/ingest", json=record, timeout=8.0)
                
            st.success("Quiet period simulated 🌙")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Could not reach API: {e}")

    st.divider()
    st.caption(f"TUA Astro Hackathon 2026 | {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}")


# ── Fetch data ─────────────────────────────────────────────────────────────────
latest = fetch_latest()
history_df = fetch_history()
telemetry_df = fetch_telemetry_history()

prob = latest.get("storm_probability", 0.0)
conf = latest.get("confidence_score", 0.0)
alert = latest.get("alert_level", "NORMAL")
kp = latest.get("kp_index_estimate")
horizon = latest.get("horizon_minutes", 30)
gen_at = latest.get("generated_at", "")
target_ts = latest.get("target_timestamp", "")
primary_driver = latest.get("primary_driver") or "Stable solar wind parameters."

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="solar-header">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
    <div>
      <h1 style="margin:0;font-size:1.8rem;font-weight:700;color:#e0e8ff;">
        ☀️ Solar Storm Early Warning Network
      </h1>
      <p style="margin:0;color:#8892a4;font-size:0.85rem;margin-top:4px;">
        TUA Astro Hackathon 2026 · Real-Time Geomagnetic Threat Assessment
      </p>
    </div>
    <div style="text-align:right;">
      <div style="color:#8892a4;font-size:0.75rem;">Last updated</div>
      <div style="font-family:'Space Mono',monospace;color:#64b5f6;font-size:0.9rem;">
        {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
      </div>
      <div style="color:#8892a4;font-size:0.75rem;margin-top:4px;">Forecast horizon: +{horizon} min</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Alert banner ───────────────────────────────────────────────────────────────
alert_icons = {"NORMAL": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}
alert_msgs = {
    "NORMAL": "All Clear — Solar activity within normal parameters",
    "WARNING": "⚠️ ELEVATED ACTIVITY — Monitor closely. Storm possible within forecast window.",
    "CRITICAL": "🚨 GEOMAGNETIC STORM ALERT — Severe space weather event imminent! Take protective measures.",
}
alert_class = alert.lower()
st.markdown(
    f'<div class="alert-{alert_class}">{alert_icons.get(alert,"●")} {alert_msgs.get(alert,"Status unknown")}</div>',
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ROW 1 — THE VERDICT                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
col_gauge, col_insights = st.columns([1, 1])

with col_gauge:
    from dashboard.components.gauge import build_gauge
    st.plotly_chart(build_gauge(prob, alert, conf), use_container_width=True, config={"displayModeBar": False})

with col_insights:
    # Add vertical spacing to align with the visual center of the Plotly gauge
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    st.markdown('<p class="section-label">🧠 Model Insights</p>', unsafe_allow_html=True)
    driver_text = f"**{primary_driver}**\n\n*Heuristic XAI · Based on latest L1 telemetry reading*"
    if alert == "CRITICAL":
        st.error(driver_text, icon="🔴")
    elif alert == "WARNING":
        st.warning(driver_text, icon="🟡")
    else:
        st.info(driver_text, icon="🟢")
        
    st.markdown("<br>", unsafe_allow_html=True)
    st.metric(
        label="🧲 Est. Kp Index",
        value=f"{kp:.1f}" if kp is not None else "—",
        help="Estimated planetary K-index (0=quiet, 9=extreme storm)",
    )
    st.metric(
        label="⏱ Forecast Window",
        value=f"+{horizon} min",
    )

st.divider()

# ── Deep Space LDPC Challenge ──────────────────────────────────────────────────
current_prob = prob * 100 if prob else 0.0

st.markdown("---")
st.subheader("🪐 Derin Uzay İletişim Protokolü (Deep Space LDPC)")
st.caption("Yapay zeka tahminlerine dayalı otonom veri sıkıştırma ve hata düzeltme (FEC) simülasyonu.")

if st.button("🚀 Mars Yüzeyinden Veri İletimini Simüle Et"):
    # Limpiamos el estado anterior
    st.session_state.ldpc_sim_result = None
    
    # Elementos visuales para la animación
    anim_text = st.empty()
    progress_bar = st.progress(0)
    
    # Animación Paso 1: Transmisión
    anim_text.info("🛰️ **Adım 1:** Mars Rover verisi hazırlanıyor... (Veri boyutu: 240 bit / 1.0 MB Payload)")
    for percent in range(1, 35):
        progress_bar.progress(percent)
        time.sleep(0.02)
        
    # Animación Paso 2: Interferencia de Tormenta
    anim_text.warning("⚠️ **Adım 2: UYARI!** Güneş radyasyonu sinyale çarptı. İyonosferik parazit nedeniyle bitler bozuluyor (Bit-Flipping)...")
    for percent in range(35, 75):
        progress_bar.progress(percent)
        time.sleep(0.04) # Más lento para generar tensión
        
    # Animación Paso 3: Matemáticas al rescate
    anim_text.error("🧮 **Adım 3:** Sinyal kritik hasar aldı! Bilişsel LDPC onarım algoritması devreye giriyor...")
    
    # Ejecutamos la función real pesada
    st.session_state.ldpc_sim_result = simulate_deep_space_transmission(current_prob)
    
    for percent in range(75, 101):
        progress_bar.progress(percent)
        time.sleep(0.02)
        
    # Limpiamos los placeholders de animación una vez terminado
    anim_text.empty()
    progress_bar.empty()

# Renderizamos el resultado guardado en memoria (resiste los auto-refresh)
if st.session_state.ldpc_sim_result:
    result = st.session_state.ldpc_sim_result
    
    if 'error' in result:
        st.error(f"Simülasyon Hatası: {result['error']}")
    else:
        st.markdown("#### 📡 **İletim Raporu (Transmission Report)**")
        cols = st.columns(4)
        cols[0].metric("İletim Modu (Mode)", result['mode'])
        cols[1].metric("Kanal Gürültüsü (SNR)", f"{result['snr']} dB")
        cols[2].metric("Radyasyon Hasarı", f"{result['corrupted_bits']} bit")
        cols[3].metric("Kurtarma Oranı", f"%{result['success_rate']:.1f}")
        
        if result['recovered_100_percent']:
            st.success(f"✅ **GÖREV BAŞARILI:** Yapay zeka modülasyonu radyasyon gürültüsünü yendi. Bozulan **{result['corrupted_bits']} bit** LDPC matrisi ile %100 oranında kurtarıldı.")
        else:
            st.warning(f"⚠️ **KISMİ KAYIP:** Fırtına çok şiddetliydi, ancak LDPC algoritması **{result['corrupted_bits']} hatalı bitin** büyük kısmını onarmayı başardı.")

import streamlit.components.v1 as components

# ── TEİAŞ GIC Risk Engine ──────────────────────────────────────────────────────
st.markdown("---")
st.subheader("⚡ TEİAŞ Kritik Altyapı Koruma (Terrestrial GIC Risk Engine)")
st.caption("Türkiye'nin enlemine ve Bz yönelimine göre otomatik şebeke manevra simülasyonu.")

terrestrial_data = calculate_terrestrial_impact(current_prob)
storm_severe = terrestrial_data['terrestrial_risk'] > 80

col_data, col_anim = st.columns([1, 2])

with col_data:
    st.metric("GIC Hasar Skoru", f"%{terrestrial_data['terrestrial_risk']:.1f}")
    st.metric("Kp İndeksi", f"{terrestrial_data['kp_index']}/9")
    st.write(f"**Manyetik Yönelim:** {terrestrial_data['bz_component']} nT")

with col_anim:
    if storm_severe:
        st.error("🚨 **KRİTİK UYARI:** Şebeke ayırma protokolü devrede. (Protocolo de Desconexión)")
        
        # SVG sin espacios a la izquierda para evitar el bug de Markdown
        svg_animation = """
<div style="display: flex; justify-content: center; align-items: center; padding: 20px; background-color: #1E1E1E; border-radius: 10px; border: 2px solid #FF4B4B;">
    <svg width="350" height="120" viewBox="0 0 350 120">
        <rect x="20" y="20" width="60" height="80" rx="8" fill="#333" stroke="#555" stroke-width="2"/>
        <rect x="40" y="40" width="12" height="8" rx="2" fill="#111"/>
        <rect x="40" y="70" width="12" height="8" rx="2" fill="#111"/>
        <g>
            <animateTransform attributeName="transform" type="translate" values="0,0; 100,0" begin="0.2s" dur="0.6s" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1"/>
            <rect x="35" y="41" width="20" height="6" rx="1" fill="#ddd"/>
            <rect x="35" y="71" width="20" height="6" rx="1" fill="#ddd"/>
            <rect x="55" y="30" width="50" height="60" rx="10" fill="#4CAF50">
                <animate attributeName="fill" values="#4CAF50;#FF4B4B" begin="0.4s" dur="0.2s" fill="freeze"/>
            </rect>
            <path d="M 105 60 C 150 60, 180 90, 250 90" fill="none" stroke="#222" stroke-width="12" stroke-linecap="round"/>
        </g>
        <g opacity="0">
            <animate attributeName="opacity" values="0;1;0;1;0" begin="0.8s" dur="1s" repeatCount="indefinite"/>
            <circle cx="50" cy="44" r="4" fill="#FFD700"/>
            <circle cx="50" cy="74" r="4" fill="#FFD700"/>
            <path d="M 45 35 L 55 25 L 50 40 Z" fill="#FFD700"/>
        </g>
    </svg>
</div>
"""
        st.markdown(svg_animation, unsafe_allow_html=True)
        st.info("⚡ Akkuyu ve Atatürk trafoları fiziksel olarak şebekeden ayrıldı.")
        
    else:
        st.success("✅ **DURUM NORMAL:** Şebeke bağlı ve operasyonel.")
        
        svg_connected = """
<div style="display: flex; justify-content: center; align-items: center; padding: 20px; background-color: #1E1E1E; border-radius: 10px; border: 2px solid #4CAF50;">
    <svg width="350" height="120" viewBox="0 0 350 120">
        <rect x="20" y="20" width="60" height="80" rx="8" fill="#333" stroke="#555" stroke-width="2"/>
        <rect x="40" y="40" width="12" height="8" rx="2" fill="#111"/>
        <rect x="40" y="70" width="12" height="8" rx="2" fill="#111"/>
        <g transform="translate(0,0)">
            <rect x="35" y="41" width="20" height="6" rx="1" fill="#ddd"/>
            <rect x="35" y="71" width="20" height="6" rx="1" fill="#ddd"/>
            <rect x="55" y="30" width="50" height="60" rx="10" fill="#4CAF50"/>
            <path d="M 105 60 C 150 60, 180 90, 250 90" fill="none" stroke="#222" stroke-width="12" stroke-linecap="round"/>
        </g>
    </svg>
</div>
"""
        st.markdown(svg_connected, unsafe_allow_html=True)

st.divider()

# ── TUA Yörünge ve Uzay Çöpü Kontrol Merkezi ──────────────────────────────────
st.subheader("🛰️ TUA Yörünge ve Uzay Çöpü Kontrol Merkezi")
st.caption("Uzay çöpleri (Space Debris) takip ve çarpışma önleme simülatörü. Fırtına kaynaklı atmosferik sürüklenme (Drag) etkilerini 3 boyutlu küre üzerinde analiz edin.")

# Un mensaje llamativo y un botón que redirige a la otra página
col_info, col_btn = st.columns([3, 1])
with col_info:
    st.info("💡 **YENİ MODÜL:** İMECE uydusu ve uzay çöpleri arasındaki yörünge kesişimlerini canlı 3D haritada izlemek için Kontrol Merkezine geçiş yapın.")
with col_btn:
    # Botón HTML puro inyectado en Markdown. Es infalible.
    # El href apunta al nombre del archivo de la página (sin el .py)
    html_button = '''
    <a href="1_Yorunge_Kontrol" target="_self" style="text-decoration: none;">
        <div style="background-color: #2b2b36; border: 2px solid #4CAF50; padding: 12px; border-radius: 8px; text-align: center; color: white; font-weight: bold; transition: 0.3s; cursor: pointer;">
            🚀 Kontrol Merkezini Aç
        </div>
    </a>
    '''
    st.markdown(html_button, unsafe_allow_html=True)

st.divider()

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ROW 2 — THE FORECAST (Cone left · Heatmap right)                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
col_cone, col_heat = st.columns([1, 1])

with col_cone:
    st.markdown('<p class="section-label">🌀 Uncertainty Cone</p>', unsafe_allow_html=True)
    from dashboard.components.cone import build_cone
    st.plotly_chart(
        build_cone(history_df if not history_df.empty else pd.DataFrame(), horizon),
        use_container_width=True,
        config={"displayModeBar": False},
    )

with col_heat:
    st.markdown('<p class="section-label">🌐 Activity Forecast Heatmap</p>', unsafe_allow_html=True)
    from dashboard.components.heatmap import build_heatmap
    st.plotly_chart(
        build_heatmap(history_df if not history_df.empty else pd.DataFrame()),
        use_container_width=True,
        config={"displayModeBar": False},
    )

st.divider()

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ROW 3 — THE EVIDENCE (Full-width time-series)                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
st.markdown('<p class="section-label">📡 Real-Time Solar Wind Parameters</p>', unsafe_allow_html=True)
if not telemetry_df.empty:
    from dashboard.components.timeseries import build_timeseries
    st.plotly_chart(build_timeseries(telemetry_df), use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Waiting for telemetry data from NOAA SWPC...")

# ── Recent predictions table ───────────────────────────────────────────────────
if not history_df.empty:
    st.divider()
    st.markdown('<p class="section-label">📋 Prediction Log (last 10)</p>', unsafe_allow_html=True)
    display_cols = ["generated_at", "storm_probability", "confidence_score", "alert_level", "kp_index_estimate"]
    available = [c for c in display_cols if c in history_df.columns]
    display_df = history_df[available].tail(10).copy()
    display_df["storm_probability"] = (display_df["storm_probability"] * 100).round(1).astype(str) + "%"
    display_df["confidence_score"] = (display_df["confidence_score"] * 100).round(1).astype(str) + "%"
    st.dataframe(
        display_df.sort_values("generated_at", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

# ── Auto-refresh ───────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
