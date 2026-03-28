import streamlit as st
import streamlit.components.v1 as components
import json
import requests

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Yörünge Kontrol Merkezi - Canlı 60 FPS")

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
            for i in range(0, min(len(lines), 900), 3): 
                if i+2 < len(lines):
                    data.append({"name": lines[i].strip(), "tle1": lines[i+1].strip(), "tle2": lines[i+2].strip(), "type": cat})
        except: pass
    return data

tle_payload = get_space_data()

st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Fırtına Olasılığı (%)", 0, 100, 25)
is_danger = 1 if storm_prob > 75 else 0

# Motor Visual con Respaldo de Color (Solid Backup)
globe_html = f'''
<!DOCTYPE html>
<html>
<head>
    <script src="https://unpkg.com/globe.gl"></script>
    <script src="https://unpkg.com/satellite.js/dist/satellite.min.js"></script>
    <style>
        body {{ margin: 0; background: #000; overflow: hidden; }}
        #info {{ position: absolute; top: 10px; left: 10px; color: #00ffcc; z-index: 10; font-family: monospace; pointer-events: none; }}
        #globeViz {{ width: 100vw; height: 100vh; }}
    </style>
</head>
<body>
    <div id="info">📡 Sistem Hazır | Objetos: {len(tle_payload)}</div>
    <div id="globeViz"></div>

    <script>
        try {{
            const rawData = {json.dumps(tle_payload)};
            const isDanger = {is_danger};
            const satData = rawData.map(d => ({{ ...d, satrec: satellite.twoline2rv(d.tle1, d.tle2) }}));

            const world = Globe()(document.getElementById('globeViz'))
                .backgroundColor('#000000')
                .showAtmosphere(true)
                .atmosphereColor('#00ccff')
                .globeColor('#051124') // Color sólido azul profundo (no depende de imágenes)
                .showGraticules(true)  // Rejilla para ver el mundo girar
                .pointRadius(0.8)
                .pointColor(d => d.type === 'active' ? '#00ffcc' : (isDanger ? '#ff0000' : '#ff9900'))
                .pointAltitude(d => d.alt)
                .width(window.innerWidth)
                .height(800);

            // Intentar cargar la textura, pero si falla el globo ya es azul
            world.globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg');

            function update() {{
                const now = new Date();
                const gmst = satellite.gstime(now);
                const points = satData.map(d => {{
                    const posVel = satellite.propagate(d.satrec, now);
                    if (!posVel.position) return null;
                    const posGeodetic = satellite.eciToGeodetic(posVel.position, gmst);
                    let alt = posGeodetic.height / 6371;
                    if (isDanger && d.type === 'debris') alt *= 0.94;
                    return {{ lat: satellite.degreesLat(posGeodetic.latitude), lng: satellite.degreesLong(posGeodetic.longitude), alt: alt, type: d.type }};
                }}).filter(p => p !== null);
                
                world.pointsData(points);
                requestAnimationFrame(update);
            }}

            world.pointOfView({{ lat: 39, lng: 35, alt: 2.5 }});
            update();
        }} catch(e) {{
            document.getElementById('info').innerHTML = "❌ Error: " + e.message;
        }}
    </script>
</body>
</html>
'''

components.html(globe_html, height=800)
