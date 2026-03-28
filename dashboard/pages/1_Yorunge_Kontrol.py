import streamlit as st
import plotly.graph_objects as go

# Configuración de página (debe ser lo primero)
st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Yörünge ve Uzay Çöpü Kontrol Merkezi")
st.markdown("Güneş fırtınası kaynaklı atmosferik genleşmenin (Termosferik Isınma) uzay çöpleri ve aktif uydular üzerindeki 'Orbital Decay' (Yörünge Alçalması) etkisini simüle eder.")

st.markdown("---")

# Simulador de entrada de la IA (Para la demo en esta página independiente)
st.sidebar.header("🌞 Uzay Havası (Space Weather)")
st.sidebar.caption("Surya AI modelinin anlık fırtına olasılığını simüle edin:")
storm_prob = st.sidebar.slider("Güneş Fırtınası Olasılığı (%)", 0, 100, 25)

# Lógica de Colisión (Conciencia Situacional Espacial)
is_danger = storm_prob > 75
imece_lat, imece_lon = 39.0, 35.0 # Posición base sobre Turquía

if is_danger:
    # La tormenta frena la basura espacial, haciendo que su órbita decaiga y se cruce con İMECE
    debris_lat, debris_lon = 39.5, 35.5 
    distance = 120 # metros
    status_color = "#FF4B4B" # Rojo
    line_color = "red"
else:
    # Órbita normal y segura
    debris_lat, debris_lon = 45.0, 50.0 
    distance = 54000 # metros
    status_color = "#4CAF50" # Verde
    line_color = "rgba(255, 255, 255, 0.2)" # Blanco transparente

col_map, col_alerts = st.columns([2.5, 1])

with col_map:
    fig = go.Figure()

    # 1. Trazado del Satélite İMECE (Verde/Cian)
    fig.add_trace(go.Scattergeo(
        lon=[imece_lon], lat=[imece_lat],
        mode='markers+text', text=["İMECE Uydusu"], textposition="bottom center",
        textfont=dict(color="cyan", size=12),
        marker=dict(size=12, color='cyan', symbol='square'),
        name="Aktif Uydu"
    ))

    # 2. Trazado de la Basura Espacial (Cambia de color según peligro)
    fig.add_trace(go.Scattergeo(
        lon=[debris_lon], lat=[debris_lat],
        mode='markers+text', text=["KOSMOS Enkazı (Debris)"], textposition="top center",
        textfont=dict(color=status_color, size=12),
        marker=dict(size=10, color=status_color, symbol='circle'),
        name="Uzay Çöpü"
    ))
    
    # 3. Estela/Línea de trayectoria visual
    fig.add_trace(go.Scattergeo(
        lon=[imece_lon, debris_lon], lat=[imece_lat, debris_lat],
        mode='lines',
        line=dict(width=2, color=line_color, dash='dot'),
        name="Yaklaşma Vektörü"
    ))

    # Configuración del Globo 3D
    fig.update_layout(
        geo=dict(
            projection_type='orthographic', # Esto crea la esfera 3D giratoria
            showcoastlines=True, coastlinecolor="rgba(255, 255, 255, 0.3)",
            showland=True, landcolor="#0e1117",
            showocean=True, oceancolor="#000000",
            showlakes=False,
            showcountries=True, countrycolor="rgba(255, 255, 255, 0.1)",
            bgcolor="black"
        ),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

with col_alerts:
    st.subheader("🚨 Çarpışma Uyarı Paneli")
    st.caption("Uzay Çöpleri Takip ve Çarpışma Önleme Sistemi")
    
    if is_danger:
        st.error("⚠️ **KRİTİK UYARI: YÖRÜNGE KESİŞİMİ**")
        st.markdown(f"""
        **Tehdit:** KOSMOS-2251 Enkazı
        **Hedef:** İMECE Gözlem Uydusu
        **Yaklaşma Mesafesi:** `{distance} m`
        """)
        st.warning("""
        **Neden:** Güneş fırtınası (Olasılık > %75) termosferi ısıtarak atmosferik yoğunluğu artırdı. Enkazın yörüngesi beklenenden hızlı alçaldı (Orbital Decay).
        """)
        st.info("⚡ **OTOMATİK EMİR:** İMECE uydusu için Delta-V kaçınma manevrası (Collision Avoidance Burn) hesaplanıyor...")
    else:
        st.success("✅ **YÖRÜNGE GÜVENLİ**")
        st.write("Aktif uydular ve izlenen uzay çöpleri arasında kritik bir kesişim yok.")
        st.metric("En Yakın Enkaz Mesafesi", f"{distance / 1000} km")
        st.info("Termosferik yoğunluk normal seviyelerde. Yörünge sapması (Drag) minimum.")
