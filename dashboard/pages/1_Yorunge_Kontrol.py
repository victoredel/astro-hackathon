import streamlit as st
import streamlit.components.v1 as components
import json
import requests
import os

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")
st.title("🛰️ TUA Küresel Yörünge Takip ve Çarpışma Tahmini")

@st.cache_resource
def load_js_libs():
    # Dual-CDN with fallback to avoid case-sensitivity 404s on cdnjs
    sources = {
        "globe": [
            "https://cdn.jsdelivr.net/npm/globe.gl/dist/globe.gl.min.js",
            "https://unpkg.com/globe.gl",
        ],
        "satellite": [
            "https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js",
            "https://unpkg.com/satellite.js/dist/satellite.min.js",
        ]
    }
    content = {}
    for name, urls in sources.items():
        content[name] = ""
        for url in urls:
            try:
                r = requests.get(url, timeout=8)
                if r.status_code == 200 and not r.text.strip().startswith("<"):
                    content[name] = r.text
                    break
            except:
                pass
    return content

js_libs = load_js_libs()

@st.cache_data(ttl=3600)
def get_raw_tles():
    urls = {
        "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
        "debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=tle"
    }
    data = []
    # Simular User-Agent de navegador para evitar bloqueos anti-bot de CelesTrak
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for cat, url in urls.items():
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                lines = r.text.strip().splitlines()
                for i in range(0, min(len(lines), 900), 3):
                    if i+2 < len(lines):
                        data.append({"n": lines[i].strip(), "l1": lines[i+1].strip(), "l2": lines[i+2].strip(), "t": cat})
        except Exception as e:
            print(f"Error cargando {cat}: {e}")
    return data

tle_payload = get_raw_tles()

st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Güneş Fırtınası Olasılığı (%)", 0, 100, 25)

# --- LLAMADA AL BACKEND (GET con query params) ---
API_BASE = os.getenv("API_BASE_URL", "http://api:8000")
API_URL = f"{API_BASE}/api/v1"
is_danger = False
radar_message = "SCANNING: ORBIT CLEAR"

try:
    with st.spinner("📡 Radar Taraması Aktif (Backend hesaplıyor)..."):
        # Timeout aumentado a 20s para dar tiempo al backend de procesar
        r = requests.get(f"{API_URL}/orbital/collision-risk", params={"storm_prob": storm_prob}, timeout=20)
        if r.status_code == 200:
            data = r.json()
            is_danger = data.get("is_danger", False)
            dist_m = data.get("distance_m", 0)
            rec = data.get("recommendation", "")

            if is_danger:
                st.error(f"🚨 **ÇARPIŞMA ALARMI!** Mesafe: {dist_m}m. {rec}")
                radar_message = f"DANGER: IMPACT DETECTED IN {dist_m}m!"
            else:
                st.success(f"✅ GÜVENLİ: Minimum yaklaşma mesafesi {dist_m}m.")
                radar_message = "SCANNING: ORBIT CLEAR"
        else:
            st.sidebar.warning(f"Backend devolvió error: {r.status_code}")
except requests.exceptions.Timeout:
    st.sidebar.warning("⏱️ Backend zaman aşımına uğradı (Timeout). Hesaplama çok uzun sürdü.")
except Exception as e:
    st.sidebar.warning(f"Backend API kapalı. Hata: {e}")

# --- HTML BLINDADO ---
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

            const timeMultiplier = 60; // 1 real sec = 1 orbital min
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

            // Aplicar opcional sin romper chain
            try { world.globeColor('#051124'); } catch(e) {}
            try {
                world.globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg');
            } catch(e) {}

            // Cargar países (opcional, si no hay red, sigue)
            fetch('https://unpkg.com/three-globe/example/img/world-110m.geojson')
                .then(res => res.json())
                .then(countries => {
                    world.hexPolygonsData(countries.features)
                         .hexPolygonResolution(3)
                         .hexPolygonMargin(0.1)
                         .hexPolygonColor(() => 'rgba(0, 255, 204, 0.3)');
                }).catch(() => {});

            // Parsear TLEs con twoline2satrec (nombre correcto en satellite.js v4+)
            const satData = rawData.map(d => {
                try { return { ...d, satrec: satLib.twoline2satrec(d.l1, d.l2) }; } 
                catch(e) { return null; }
            }).filter(s => s !== null);

            document.getElementById('ui').innerHTML =
                '📡 RADAR: __RADAR_MSG__ | OBJELER: ' + satData.length;

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
                            if (isDanger && d.t === 'debris') alt *= 0.95; // Simula decaimiento

                            return {
                                lat: satLib.degreesLat(posGeo.latitude),
                                lng: satLib.degreesLong(posGeo.longitude),
                                alt: alt,
                                t: d.t
                            };
                        } catch(e) { return null; }
                    }).filter(p => p !== null);

                    world.pointsData(points);
                } catch(e) { console.error("Update error:", e); }
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

# Reemplazos limpios — sin f-strings para las librerías JS
html_final = template_html.replace("__SATELLITE_JS__", js_libs['satellite'])
html_final = html_final.replace("__GLOBE_JS__", js_libs['globe'])
html_final = html_final.replace("__DATA__", json.dumps(tle_payload))
html_final = html_final.replace("__IS_DANGER__", str(is_danger).lower())
html_final = html_final.replace("__DANGER_CLASS__", "danger" if is_danger else "")
html_final = html_final.replace("__RADAR_MSG__", radar_message)
html_final = html_final.replace("__COUNT__", str(len(tle_payload)))

components.html(html_final, height=800)
