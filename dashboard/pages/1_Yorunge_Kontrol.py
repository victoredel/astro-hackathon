import streamlit as st
import streamlit.components.v1 as components
import json
import requests

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

# 1. Obtener datos reales de CelesTrak en el servidor (Python)
@st.cache_data(ttl=3600)
def get_raw_tle_data():
    urls = {
        "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
        "debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=tle"
    }
    combined_data = []
    for cat, url in urls.items():
        try:
            r = requests.get(url, timeout=5)
            lines = r.text.strip().split('\n')
            # Tomamos una muestra representativa para no saturar el navegador
            for i in range(0, min(len(lines), 900), 3):
                if i+2 < len(lines):
                    combined_data.append({
                        "name": lines[i].strip(),
                        "tle_l1": lines[i+1].strip(),
                        "tle_l2": lines[i+2].strip(),
                        "type": cat
                    })
        except: pass
    return combined_data

tle_json = json.dumps(get_raw_tle_data())

# 2. El "Motor Visual" en JavaScript (Globe.gl)
globe_html = f'''
<div id="globeViz"></div>
<script src="//unpkg.com/globe.gl"></script>
<script src="//unpkg.com/satellite.js/dist/satellite.min.js"></script>

<script>
    const tleData = {tle_json};
    const satData = tleData.map(d => ({{
        ...d,
        satrec: satellite.twoline2rv(d.tle_l1, d.tle_l2)
    }}));

    const world = Globe()
        (document.getElementById('globeViz'))
        .globeImageUrl('//unpkg.com/three-globe/example/img/earth-night.jpg')
        .bumpImageUrl('//unpkg.com/three-globe/example/img/earth-topology.png')
        .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
        .showAtmosphere(true)
        .atmosphereColor('lightskyblue')
        .atmosphereDaylightAlpha(0.1);

    // Función para actualizar posiciones a 60fps
    function updatePositions() {{
        const now = new Date();
        const gmst = satellite.gstime(now);

        const points = [];
        satData.forEach(d => {{
            try {{
                const positionAndVelocity = satellite.propagate(d.satrec, now);
                if (positionAndVelocity && positionAndVelocity.position && positionAndVelocity.position.x !== false) {{
                    const positionEcf = satellite.eciToGeodetic(positionAndVelocity.position, gmst);
                    points.push({{
                        lat: satellite.degreesLat(positionEcf.latitude),
                        lng: satellite.degreesLong(positionEcf.longitude),
                        alt: positionEcf.height / 6371, // Normalizado al radio terrestre
                        type: d.type
                    }});
                }}
            }} catch (e) {{
                // Skip invalid propagation
            }}
        }});

        world.pointsData(points)
            .pointColor(d => d.type === 'active' ? '#00ffcc' : '#ff4b4b')
            .pointRadius(0.5)
            .pointAltitude(d => d.alt);
            
        requestAnimationFrame(updatePositions);
    }}

    updatePositions();
    world.controls().autoRotate = true;
    world.controls().autoRotateSpeed = 0.5;
</script>
<style> body {{ margin: 0; background: black; }} </style>
'''

# 3. Renderizar en Streamlit
components.html(globe_html, height=800)
