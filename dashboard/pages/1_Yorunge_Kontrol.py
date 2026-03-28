import streamlit as st
import streamlit.components.v1 as components
import json
import requests
import os

# --- Importamos la predicción directamente desde el Backend ---
try:
    from pipeline.orbital_collision import calculate_orbital_risk
except ImportError:
    calculate_orbital_risk = None

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")
st.title("🛰️ TUA Küresel Yörünge Takip ve Çarpışma Tahmini (Canlı Veri)")

@st.cache_resource
def load_js_libs():
    sources = {
        "globe": ["https://cdn.jsdelivr.net/npm/globe.gl/dist/globe.gl.min.js", "https://unpkg.com/globe.gl"],
        "satellite": ["https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js", "https://unpkg.com/satellite.js/dist/satellite.min.js"]
    }
    content = {}
    for name, urls in sources.items():
        content[name] = ""
        for url in urls:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200 and not r.text.strip().startswith("<"):
                    content[name] = r.text
                    break
            except: pass
    return content

js_libs = load_js_libs()

# --- NUEVAS FUENTES DE DATOS (SIN AUTORIZACIÓN NI BLOQUEOS) ---
@st.cache_data(ttl=3600)
def get_raw_tles():
    urls = {
        # AMSAT: Servidor libre de radioaficionados (Satélites activos)
        "active": "https://www.amsat.org/tle/current/nasabare.txt",
        # CELESTRAK (.com y .txt): Archivo de texto estático, evade el firewall del .org/php
        "debris": "https://celestrak.com/NORAD/elements/cosmos-2251-debris.txt"
    }
    data = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for cat, url in urls.items():
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                lines = r.text.strip().splitlines()
                # Extraemos un máximo de 300 objetos por categoría para mantener los 60 FPS
                for i in range(0, min(len(lines), 900), 3):
                    if i+2 < len(lines):
                        data.append({"n": lines[i].strip(), "l1": lines[i+1].strip(), "l2": lines[i+2].strip(), "t": cat})
        except: pass
    
    return data

tle_payload = get_raw_tles()

st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Güneş Fırtınası Olasılığı (%)", 0, 100, 25)

# --- EJECUCIÓN DEL CEREBRO DE COLISIÓN (INSTANTÁNEO, SIN TIMEOUT) ---
is_danger = False
radar_message = "SCANNING: ORBIT CLEAR"

if calculate_orbital_risk:
    with st.spinner("🧠 Radar Taraması Aktif (Backend hesaplıyor)..."):
        try:
            risk_data = calculate_orbital_risk(storm_prob=storm_prob)
            is_danger = risk_data.get("is_danger", False)
            dist_m = risk_data.get("distance_m", 0)
            rec = risk_data.get("recommendation", "")

            if is_danger:
                st.error(f"🚨 **ÇARPIŞMA ALARMI!** Mesafe: {dist_m}m. {rec}")
                radar_message = f"DANGER: IMPACT DETECTED IN {dist_m}m!"
            else:
                st.success(f"✅ GÜVENLİ: Minimum yaklaşma mesafesi {dist_m}m.")
                radar_message = "SCANNING: ORBIT CLEAR"
        except Exception as e:
            st.error(f"Hesaplama hatası: {e}")
else:
    st.warning("⚠️ API modülü bulunamadı. Lütfen backend dosyalarını kontrol edin.")

# --- HTML DEL GLOBO ---
template_html = '''
<!DOCTYPE html>
<html>
<head>
    <style> 
        body { margin: 0; background: #000; overflow: hidden; font-family: monospace; } 
        #ui { position: absolute; top: 15px; left: 15px; color: #00ffcc; z-index: 10; font-size: 16px; font-weight: bold; text-shadow: 0 0 5px #00ffcc; }
        .danger { color: #ff0000 !important; text-shadow: 0 0 10px #ff0000 !important; animation: blink 1s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    </style>
    <script>__SATELLITE_JS__</script>
    <script>__GLOBE_JS__</script>
</head>
<body>
    <div id="ui" class="__DANGER_CLASS__">📡 RADAR: __RADAR_MSG__ | OBJELER: __COUNT__</div>
    <div id="globeViz"></div>

    <script>
        try {
            if (typeof Globe === 'undefined') throw new Error("Globe.gl kütüphanesi yüklenemedi.");
            if (typeof satellite === 'undefined') throw new Error("satellite.js kütüphanesi yüklenemedi.");

            const rawData = __DATA__;
            const isDanger = __IS_DANGER__;
            const satLib = satellite;

            const timeMultiplier = 60; 
            const startTime = Date.now();

            const world = Globe()(document.getElementById('globeViz'))
                .backgroundColor('#000000')
                .showAtmosphere(true)
                .atmosphereColor('#00ccff')
                .pointRadius(0.8)
                .pointColor(d => d.t === 'active' ? '#00ffcc' : (isDanger ? '#ff0000' : '#ff9900'))
                .pointAltitude(d => d.alt || 0.1)
                .width(window.innerWidth)
                .height(800);

            try { world.globeColor('#051124'); } catch(e) {}

            fetch('https://unpkg.com/three-globe/example/img/world-110m.geojson')
                .then(res => res.json())
                .then(countries => {
                    world.hexPolygonsData(countries.features)
                         .hexPolygonResolution(3)
                         .hexPolygonMargin(0.1)
                         .hexPolygonColor(() => 'rgba(0, 255, 204, 0.3)');
                }).catch(() => {});

            const satData = rawData.map(d => {
                try { return { ...d, satrec: satLib.twoline2satrec(d.l1, d.l2) }; } 
                catch(e) { return null; }
            }).filter(s => s !== null);

            function update() {
                try {
                    const elapsed = Date.now() - startTime;
                    const simTime = new Date(startTime + elapsed * timeMultiplier);
                    const gmst = satLib.gstime(simTime);

                    const points = satData.map(d => {
                        try {
                            const posVel = satLib.propagate(d.satrec, simTime);
                            if (!posVel.position || !posVel.position.x) return null;
                            
                            const posGeo = satLib.eciToGeodetic(posVel.position, gmst);
                            let alt = posGeo.height / 6371;
                            if (isDanger && d.t === 'debris') alt *= 0.95; 

                            return {
                                lat: satLib.degreesLat(posGeo.latitude),
                                lng: satLib.degreesLong(posGeo.longitude),
                                alt: alt,
                                t: d.t
                            };
                        } catch(e) { return null; }
                    }).filter(p => p !== null);

                    world.pointsData(points);
                } catch(e) {}
                requestAnimationFrame(update);
            }

            world.pointOfView({ lat: 39, lng: 35, alt: 2.5 });
            update();
            window.onresize = () => world.width(window.innerWidth).height(800);

        } catch(e) {
            document.getElementById('ui').classList.add('danger');
            document.getElementById('ui').innerHTML = "❌ JS ERROR: " + e.message;
        }
    </script>
</body>
</html>
'''

# Reemplazos limpios
html_final = template_html.replace("__SATELLITE_JS__", js_libs['satellite'])
html_final = html_final.replace("__GLOBE_JS__", js_libs['globe'])
html_final = html_final.replace("__DATA__", json.dumps(tle_payload))
html_final = html_final.replace("__IS_DANGER__", str(is_danger).lower())
html_final = html_final.replace("__DANGER_CLASS__", "danger" if is_danger else "")
html_final = html_final.replace("__RADAR_MSG__", radar_message)
html_final = html_final.replace("__COUNT__", str(len(tle_payload)))

components.html(html_final, height=800)
