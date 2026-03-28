import streamlit as st
import pydeck as pdk
import pandas as pd
import requests
import math
import time
from datetime import datetime, timedelta
from sgp4.api import Satrec, WGS72

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Küresel Uzay Çöpü ve Aktif Uydu Monitörü (CANLI)")
st.markdown("Dünya yörüngesindeki nesnelerin WebGL destekli canlı hareketi.")
st.markdown("---")

# 1. Cargar TLEs una sola vez en memoria (Cache global de recursos)
@st.cache_resource(ttl=3600)
def fetch_tles():
    urls = {
        "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
        "debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=tle"
    }
    
    satrecs_active = []
    satrecs_debris = []
    
    for category, url in urls.items():
        try:
            response = requests.get(url, timeout=10)
            lines = response.text.strip().split('\n')
            limit = 400 * 3 # Limitamos a 400 de cada uno para fluidez
            for i in range(0, min(len(lines), limit), 3):
                if i+2 < len(lines):
                    sat = Satrec.twoline2rv(lines[i+1].strip(), lines[i+2].strip())
                    if category == "active":
                        satrecs_active.append(sat)
                    else:
                        satrecs_debris.append(sat)
        except Exception as e:
            pass
    return satrecs_active, satrecs_debris

with st.spinner("📡 TLE verileri indiriliyor..."):
    satrecs_active, satrecs_debris = fetch_tles()

# 2. Función para calcular posiciones en un momento dado
def calculate_positions(satrecs, current_time):
    jd, fr = current_time.toordinal() + 1721424.5, current_time.hour / 24.0 + current_time.minute / 1440.0 + current_time.second / 86400.0
    
    d = jd - 2451545.0 + fr
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    gmst_rad = gmst * 15 * math.pi / 180.0

    lats, lons = [], []
    for sat in satrecs:
        e, r, v = sat.sgp4(jd, fr)
        if e == 0:
            x, y, z = r
            r_norm = math.sqrt(x**2 + y**2 + z**2)
            lat = math.degrees(math.asin(z / r_norm))
            lon = math.degrees(math.atan2(y, x) - gmst_rad)
            lon = (lon + 180) % 360 - 180
            lats.append(lat)
            lons.append(lon)
    return pd.DataFrame({"lat": lats, "lon": lons})

# 3. Interfaz de Control
st.sidebar.header("🌞 Uzay Havası (Space Weather)")
storm_prob = st.sidebar.slider("Güneş Fırtınası Olasılığı (%)", 0, 100, 25)
is_danger = storm_prob > 75
deb_color = [255, 75, 75, 200] if is_danger else [255, 152, 0, 200]

# 4. El bucle de animación (Real-time render)
col_map, col_alerts = st.columns([3, 1])

# st.empty() es el contenedor que vamos a actualizar constantemente
map_placeholder = col_map.empty()

with col_alerts:
    st.subheader("📊 Canlı İstatistikler")
    st.metric("Aktif Uydular", len(satrecs_active))
    st.metric("İzlenen Enkaz", len(satrecs_debris))
    
    if is_danger:
         st.error("🚨 **KRİTİK UYARI**: Atmosferik Drag yüksek.")
    else:
         st.success("✅ Yörünge Güvenli.")

# Bucle infinito para actualizar las coordenadas y redibujar el mapa PyDeck
# NOTA: En un hackathon, este bucle simple impresiona mucho.
time_offset = 0 # Segundos simulados hacia el futuro
while True:
    # Aceleramos el tiempo (ej. 1 segundo real = 30 segundos orbitales) para que el movimiento sea evidente
    simulated_time = datetime.utcnow() + timedelta(seconds=time_offset)
    
    df_active = calculate_positions(satrecs_active, simulated_time)
    df_debris = calculate_positions(satrecs_debris, simulated_time)
    
    # Capa de PyDeck para Satélites
    layer_active = pdk.Layer(
        "ScatterplotLayer",
        df_active,
        get_position="[lon, lat]",
        get_color=[0, 255, 204, 200], # Cyan
        get_radius=10000, # Reducido a 10km
        radius_min_pixels=1, # Evita que desaparezcan al alejar
        radius_max_pixels=3, # Evita que se vuelvan manchas al acercar
        pickable=True
    )

    # Capa de PyDeck para Basura
    layer_debris = pdk.Layer(
        "ScatterplotLayer",
        df_debris,
        get_position="[lon, lat]",
        get_color=deb_color,
        get_radius=15000, # Reducido a 15km
        radius_min_pixels=1.5,
        radius_max_pixels=4,
        pickable=True
    )

    # Vista Inicial centrada en Turquía
    view_state = pdk.ViewState(
        latitude=39.0,
        longitude=35.0,
        zoom=1, # Reducimos un poco el zoom para ver mejor la curvatura
        pitch=45,
    )

    # Activamos explícitamente el motor de Globo 3D
    globe_view = pdk.View(type="_GlobeView", controller=True)

    # Renderizador con la vista esférica activada
    r = pdk.Deck(
        layers=[layer_active, layer_debris],
        initial_view_state=view_state,
        views=[globe_view],   # <-- ¡Esto convierte el mapa plano en una esfera 3D!
        map_provider="carto", 
        map_style="dark",     
        tooltip={"text": "Koordinat: {lat}, {lon}"}
    )

    # Actualizamos el contenedor vacío con el nuevo mapa
    map_placeholder.pydeck_chart(r)
    
    # Avanzamos el reloj de simulación y hacemos una pausa para no quemar la CPU
    time_offset += 60 # Avanza 1 minuto orbital por cada iteración del bucle
    time.sleep(1) # Actualiza el mapa cada 1 segundo real
