import streamlit as st
import streamlit.components.v1 as components
import json
import requests

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Yörünge Kontrol Merkezi - 60 FPS")

@st.cache_resource
def load_js_libs():
    # Usamos jsDelivr que es más estable
    libs = {
        "globe": "https://cdn.jsdelivr.net/npm/globe.gl/dist/globe.gl.min.js",
        "satellite": "https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js"
    }
    content = {}
    for name, url in libs.items():
        try:
            r = requests.get(url, timeout=10)
            content[name] = r.text if r.ok else ""
        except:
            content[name] = ""
    return content

js_libs = load_js_libs()

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
            lines = r.text.strip().splitlines()
            for i in range(0, min(len(lines), 900), 3): 
                if i+2 < len(lines):
                    data.append({"name": lines[i].strip(), "tle1": lines[i+1].strip(), "tle2": lines[i+2].strip(), "type": cat})
        except: pass
    return data

tle_payload = get_space_data()

st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Fırtına Olasılığı (%)", 0, 100, 25)
is_danger = 1 if storm_prob > 75 else 0

# --- ESTRUCTURA HTML LIMPIA (SIN F-STRINGS) ---
template_html = '''
<!DOCTYPE html>
<html>
<head>
    <style> body { margin: 0; background: #000; overflow: hidden; color: #00ffcc; font-family: monospace; } </style>
    <script>__SATELLITE_JS__</script>
    <script>__GLOBE_JS__</script>
</head>
<body>
    <div id="ui" style="position: absolute; top: 10px; left: 10px; z-index: 10;">📡 SISTEM AKTIF | NESNE: __COUNT__</div>
    <div id="globeViz"></div>
    <script>
        try {
            const rawData = __DATA__;
            const isDanger = __DANGER__;
            
            const satData = rawData.map(d => ({
                ...d,
                satrec: satellite.twoline2rv(d.tle1.trim(), d.tle2.trim())
            }));

            const world = Globe()(document.getElementById('globeViz'))
                .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg')
                .backgroundColor('#000000')
                .showAtmosphere(true)
                .atmosphereColor('#00ccff')
                .globeColor('#051124')
                .pointRadius(0.8)
                .pointColor(d => d.type === 'active' ? '#00ffcc' : (isDanger ? '#ff4b4b' : '#ff9900'))
                .pointAltitude(d => d.alt)
                .width(window.innerWidth)
                .height(800);

            function update() {
                const now = new Date();
                const gmst = satellite.gstime(now);
                const points = satData.map(d => {
                    try {
                        const posVel = satellite.propagate(d.satrec, now);
                        if (!posVel.position || posVel.position.x === false) return null;
                        const posGeo = satellite.eciToGeodetic(posVel.position, gmst);
                        let alt = posGeo.height / 6371;
                        if (isDanger && d.type === 'debris') alt *= 0.95;
                        return { lat: satellite.degreesLat(posGeo.latitude), lng: satellite.degreesLong(posGeo.longitude), alt: alt, type: d.type };
                    } catch(e) { return null; }
                }).filter(p => p !== null);
                world.pointsData(points);
                requestAnimationFrame(update);
            }

            world.pointOfView({ lat: 39, lng: 35, alt: 2.5 });
            update();
            window.onresize = () => world.width(window.innerWidth).height(800);
        } catch(e) {
            document.getElementById('ui').innerHTML = "❌ HATA: " + e.message;
        }
    </script>
</body>
</html>
'''

# Reemplazamos los marcadores manualmente para evitar conflictos con llaves {}
final_html = template_html.replace("__SATELLITE_JS__", js_libs['satellite'])
final_html = final_html.replace("__GLOBE_JS__", js_libs['globe'])
final_html = final_html.replace("__COUNT__", str(len(tle_payload)))
final_html = final_html.replace("__DANGER__", str(is_danger).lower())
final_html = final_html.replace("__DATA__", json.dumps(tle_payload))

components.html(final_html, height=800)
