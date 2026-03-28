import streamlit as st
import streamlit.components.v1 as components
import json
import requests
import os

# Configuración de página
st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Küresel Yörünge Takip ve Çarpışma Tahmini (Canlı)")

# 1. Recuperar Librerías JS (Air-Gapped Fallback)
@st.cache_resource
def load_js_libs():
    libs = {
        "globe": "https://cdn.jsdelivr.net/npm/globe.gl/dist/globe.gl.min.js",
        "satellite": "https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js"
    }
    # Fallback URLs
    fallback = {
        "globe": "https://unpkg.com/globe.gl",
        "satellite": "https://unpkg.com/satellite.js/dist/satellite.min.js"
    }
    content = {}
    for name, url in libs.items():
        content[name] = ""
        for attempt_url in [url, fallback[name]]:
            try:
                r = requests.get(attempt_url, timeout=8)
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
    data = {"active": [], "debris": []}
    for cat, url in urls.items():
        try:
            r = requests.get(url, timeout=5)
            lines = r.text.strip().splitlines()
            for i in range(0, min(len(lines), 900), 3):
                if i + 2 < len(lines):
                    data[cat].append({
                        "n": lines[i].strip(),
                        "l1": lines[i+1].strip(),
                        "l2": lines[i+2].strip()
                    })
        except:
            pass
    return data

tle_payload = get_raw_tles()

# 2. Sidebar + Llamada al Backend
st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Güneş Fırtınası Olasılığı (%)", 0, 100, 25)

API_URL = os.getenv("API_URL", "http://astroapi:8000/api/v1")
risk_level = "LOW"
risk_recommendation = ""

try:
    with st.spinner("🧠 Arka planda çarpışma riski hesaplanıyor..."):
        r = requests.post(f"{API_URL}/orbital/collision-risk", json={"storm_prob": storm_prob}, timeout=3)
        if r.ok:
            risk_data = r.json()
            risk_level = risk_data.get("risk_level", "LOW")
            risk_recommendation = (
                "ACİL: 'MERSİN uydusuna #54312' Delta-V kaçınma manevrası gerekiyor!"
                if risk_level == "HIGH" else ""
            )
except:
    risk_level = "ERROR"

# 3. Alerta Streamlit
if risk_level == "HIGH":
    st.error(f"🚨 **KRİTİK ÇARPIŞMA RİSKİ (APİ'den Alındı):** {risk_recommendation}")
elif risk_level == "ERROR":
    st.warning("📡 API Bağlantı Hatası: Backend'e ulaşılamadı — görselleştirme devam ediyor.")
else:
    st.success("✅ Yörünge Güvenli: Olası çarpışma riski düşük.")

# Parámetros para el JS
is_danger = 1 if storm_prob > 75 else 0

# 4. Motor Visual 3D — usando .replace() para inyectar todo de forma segura
template_html = '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; background: #000; overflow: hidden; color: #00ffcc; font-family: monospace; }
        #ui { position: absolute; top: 10px; left: 10px; z-index: 10; font-size: 13px; }
    </style>
    <script>__SATELLITE_JS__</script>
    <script>__GLOBE_JS__</script>
</head>
<body>
    <div id="ui">🛰️ SISTEM CANLI | AKTIF: __ACTIVE_COUNT__ / ENKAZ: __DEBRIS_COUNT__</div>
    <div id="globeViz"></div>

    <script>
        try {
            if (typeof Globe === 'undefined') throw new Error("Globe.gl kütüphanesi yüklenemedi.");
            if (typeof satellite === 'undefined') throw new Error("satellite.js kütüphanesi yüklenemedi.");

            const activeTles = __ACTIVE_DATA__;
            const debrisTles = __DEBRIS_DATA__;
            const isDanger = __DANGER__;

            // --- NAMESPACE RESOLVER (twoline2satrec is the correct modern name) ---
            const satLib = satellite;
            const parseTLE = (l1, l2) => satLib.twoline2satrec(l1.trim(), l2.trim());
            // -----------------------------------------------------------------------

            const world = Globe()(document.getElementById('globeViz'))
                .backgroundColor('#000000')
                .showAtmosphere(true)
                .atmosphereColor('#00ccff')
                .pointRadius(0.7)
                .pointAltitude(d => d.alt || 0.1)
                .pointColor(d => d.type === 'active' ? '#00ffcc' : (isDanger ? '#ff4b4b' : '#ff9900'))
                .width(window.innerWidth)
                .height(800);

            // Intentar color de globo de forma segura
            try { world.globeColor('#051124'); } catch(e) {}

            // Intentar cargar textura de la Tierra (puede fallar sin conexión, no bloquea)
            try { world.globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg'); } catch(e) {}

            // Procesar TLEs
            const active_satData = activeTles.map(d => {
                try { return { ...d, satrec: parseTLE(d.l1, d.l2), type: 'active' }; }
                catch(e) { return null; }
            }).filter(s => s !== null);

            const debris_satData = debrisTles.map(d => {
                try { return { ...d, satrec: parseTLE(d.l1, d.l2), type: 'debris' }; }
                catch(e) { return null; }
            }).filter(s => s !== null);

            document.getElementById('ui').innerHTML =
                '🛰️ SISTEM CANLI | AKTIF: ' + active_satData.length + ' / ENKAZ: ' + debris_satData.length;

            const allSats = [...active_satData, ...debris_satData];

            const timeMultiplier = 60; // 1 real sec = 1 orbital min
            const startTime = Date.now();

            function update() {
                try {
                    const elapsed = Date.now() - startTime;
                    const simTime = new Date(startTime + elapsed * timeMultiplier);
                    const gmst = satLib.gstime(simTime);

                    const points = allSats.map(d => {
                        try {
                            const posVel = satLib.propagate(d.satrec, simTime);
                            if (!posVel.position || posVel.position.x === false) return null;
                            const posGeo = satLib.eciToGeodetic(posVel.position, gmst);
                            let alt = (posGeo.height / 6371) || 0.1;
                            if (isDanger && d.type === 'debris') alt *= 0.95;
                            return {
                                lat: satLib.degreesLat(posGeo.latitude),
                                lng: satLib.degreesLong(posGeo.longitude),
                                alt: alt,
                                type: d.type
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
            document.getElementById('ui').style.color = 'red';
            document.getElementById('ui').innerHTML = '❌ HATA: ' + e.message;
        }
    </script>
</body>
</html>
'''

# Reemplazo seguro — NUNCA usamos f-strings para inyectar librerías JS
final_html = template_html.replace("__SATELLITE_JS__", js_libs['satellite'])
final_html = final_html.replace("__GLOBE_JS__", js_libs['globe'])
final_html = final_html.replace("__ACTIVE_DATA__", json.dumps(tle_payload['active']))
final_html = final_html.replace("__DEBRIS_DATA__", json.dumps(tle_payload['debris']))
final_html = final_html.replace("__ACTIVE_COUNT__", str(len(tle_payload['active'])))
final_html = final_html.replace("__DEBRIS_COUNT__", str(len(tle_payload['debris'])))
final_html = final_html.replace("__DANGER__", str(is_danger))

components.html(final_html, height=800)
