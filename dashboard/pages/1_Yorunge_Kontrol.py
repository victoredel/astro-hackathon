import streamlit as st
import streamlit.components.v1 as components
import json
import requests

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Yörünge Kontrol Merkezi - 60 FPS")

# 1. Obtenemos los TLEs en el servidor una sola vez
@st.cache_data(ttl=3600)
def get_space_data():
    urls = {
        "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
        "debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=tle"
    }
    data = []
    for cat, url in urls.items():
        try:
            r = requests.get(url, timeout=5)
            lines = r.text.strip().split('\n')
            # Limitamos para no saturar el navegador del juez
            for i in range(0, min(len(lines), 900), 3): 
                if i+2 < len(lines):
                    data.append({
                        "name": lines[i].strip(),
                        "tle1": lines[i+1].strip(),
                        "tle2": lines[i+2].strip(),
                        "type": cat
                    })
        except: pass
    return data

tle_payload = get_space_data()

# Sidebar para la IA
st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Fırtına Olasılığı (%)", 0, 100, 25)
is_danger = 1 if storm_prob > 75 else 0

# 2. El visualizador que corre en el Navegador (JavaScript)
globe_html = f'''
<!DOCTYPE html>
<html>
<head>
    <script src="https://unpkg.com/globe.gl"></script>
    <script src="https://unpkg.com/satellite.js/dist/satellite.min.js"></script>
    <style>
        body {{ margin: 0; background-color: #000; overflow: hidden; font-family: monospace; }}
        #ui {{ position: absolute; top: 10px; left: 10px; color: #00ffcc; z-index: 10; pointer-events: none; }}
    </style>
</head>
<body>
    <div id="ui">🛰️ SISTEM AKTIF | NESNE: {len(tle_payload)}</div>
    <div id="globeViz"></div>

    <script>
        const rawData = {json.dumps(tle_payload)};
        const isDanger = {is_danger};
        
        // Inicializar satélites con sus parámetros orbitales
        const satData = rawData.map(d => ({{
            ...d,
            satrec: satellite.twoline2rv(d.tle1, d.tle2)
        }}));

        const world = Globe()(document.getElementById('globeViz'))
            .globeImageUrl('//unpkg.com/three-globe/example/img/earth-night.jpg')
            .backgroundColor('#000000')
            .showAtmosphere(true)
            .atmosphereColor('#00ccff')
            .globeColor('#051124') // Respaldo si falla la imagen
            .pointRadius(0.7)
            .pointColor(d => d.type === 'active' ? '#00ffcc' : (isDanger ? '#ff4b4b' : '#ff9900'))
            .pointAltitude(d => d.alt)
            .width(window.innerWidth)
            .height(800);

        function update() {{
            const now = new Date();
            const gmst = satellite.gstime(now);

            const points = satData.map(d => {{
                try {{
                    const posVel = satellite.propagate(d.satrec, now);
                    if (!posVel.position || posVel.position.x === false) return null;
                    
                    const posGeo = satellite.eciToGeodetic(posVel.position, gmst);
                    let alt = posGeo.height / 6371;
                    
                    // Simular caída orbital si hay tormenta solar
                    if (isDanger && d.type === 'debris') alt *= 0.96;

                    return {{
                        lat: satellite.degreesLat(posGeo.latitude),
                        lng: satellite.degreesLong(posGeo.longitude),
                        alt: alt,
                        type: d.type
                    }};
                }} catch (e) {{
                    return null;
                }}
            }}).filter(p => p !== null);

            world.pointsData(points);
            requestAnimationFrame(update); // Animación a 60 FPS
        }}

        world.pointOfView({{ lat: 39, lng: 35, alt: 2.5 }});
        update();

        // Ajustar tamaño si se cambia la ventana
        window.onresize = () => world.width(window.innerWidth).height(800);
    </script>
</body>
</html>
'''

components.html(globe_html, height=800)

if is_danger:
    st.error("🚨 **ALERTA DE YÖRÜNGE:** Yüksek güneş fırtınası aktivitesi. Uzay çöpleri yörüngeden çıkıyor!")
