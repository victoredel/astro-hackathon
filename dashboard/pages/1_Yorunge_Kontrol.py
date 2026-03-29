import streamlit as st
import streamlit.components.v1 as components
import json
import requests
import os

try:
    from pipeline.orbital_collision import calculate_orbital_risk
except ImportError:
    calculate_orbital_risk = None

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")
st.title("🛰️ TUA Küresel Yörünge Takip ve Çarpışma Tahmini")

@st.cache_resource
def load_assets():
    assets = {"globe": "", "satellite": "", "geojson": "{}"}
    
    # 1. Librerías JS
    for url in ["https://cdn.jsdelivr.net/npm/globe.gl/dist/globe.gl.min.js", "https://unpkg.com/globe.gl"]:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and not r.text.strip().startswith("<"):
                assets["globe"] = r.text
                break
        except: pass
        
    for url in ["https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js", "https://unpkg.com/satellite.js/dist/satellite.min.js"]:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and not r.text.strip().startswith("<"):
                assets["satellite"] = r.text
                break
        except: pass

    # 2. Mapa de Países 
    try:
        r = requests.get("https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json", timeout=5)
        if r.status_code == 200:
            assets["geojson"] = r.text
    except: pass

    return assets

assets = load_assets()

# --- NUEVAS FUENTES ABIERTAS (SIN AUTORIZACIÓN) ---
@st.cache_data(ttl=3600)
def get_space_data():
    data = []
    error_log = ""
    
    api_key = os.getenv("SATNOGS_API_KEY")
    if not api_key:
        error_log = "Falta SATNOGS_API_KEY en el .env"
        st.error(error_log)
        return data, error_log
        
    headers = {"Authorization": f"Token {api_key}"}
    
    try:
        r = requests.get("https://db.satnogs.org/api/tle/?format=json", headers=headers, timeout=10)
        if r.status_code == 200:
            payload = r.json()
            if isinstance(payload, list) and len(payload) > 0:
                # Tomar los primeros 300 como 'active'
                for item in payload[:300]:
                    n = item.get("tle0", "UNKNOWN").replace("0 ", "")
                    l1 = item.get("tle1", "")
                    l2 = item.get("tle2", "")
                    if l1 and l2:
                        data.append({"n": n, "l1": l1, "l2": l2, "t": "active"})
                
                # Tomar los últimos 300 como 'debris' simulado (satélites inactivos antiguos)
                for item in payload[-300:]:
                    n = item.get("tle0", "UNKNOWN").replace("0 ", "")
                    l1 = item.get("tle1", "")
                    l2 = item.get("tle2", "")
                    if l1 and l2:
                        data.append({"n": "DEB_SIM_" + n, "l1": l1, "l2": l2, "t": "debris"})
            else:
                error_log += "SatNOGS devolvió un JSON vacío o no válido.\n"
        else:
            error_log += f"SatNOGS falló [{r.status_code}]: {r.text[:150]}\n"
    except Exception as e:
        error_log += f"SatNOGS EXC: {str(e)[:150]}\n"

    if error_log:
        st.error(error_log)

    return data, error_log

tle_payload, telemetry_errors = get_space_data()

st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Güneş Fırtınası Olasılığı (%)", 0, 100, 25)

# Diagnóstico local
active_count = len([d for d in tle_payload if d["t"] == "active"])
debris_count = len([d for d in tle_payload if d["t"] == "debris"])

st.sidebar.markdown("### 📡 Telemetría de Navegación")
st.sidebar.info(f"✅ Satélites Activos: {active_count}")
if debris_count > 0:
    st.sidebar.info(f"☄️ Basura Orbital: {debris_count}")
else:
    st.sidebar.error("⚠️ Cero Basura Orbital descargada.")

if telemetry_errors:
    st.sidebar.error(f"🛑 Error Log HTTP:\\n{telemetry_errors}")

is_danger = False
radar_message = "SCANNING: ORBIT CLEAR"

# --- CÁLCULO DE COLISIÓN LOCAL (0 Latencia) ---
if calculate_orbital_risk:
    with st.spinner("🧠 Radar Taraması Aktif..."):
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
        except Exception as e:
            st.error(f"Hesaplama hatası: {e}")

# --- HTML DEL GLOBO (Aislado de internet en el cliente) ---
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
            const rawData = __DATA__;
            console.log("Datos totales:", rawData.length);
            console.log("Debris vivos en front:", rawData.filter(d => d.t === 'debris').length);
            let firstDebrisLogged = false;
            const isDanger = __IS_DANGER__;
            const geoJsonData = __GEOJSON__;
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
                .pointsTransitionDuration(0)
                .width(window.innerWidth)
                .height(800);

            if (geoJsonData && geoJsonData.features) {
                world.hexPolygonsData(geoJsonData.features)
                     .hexPolygonResolution(3)
                     .hexPolygonMargin(0.1)
                     .hexPolygonColor(() => 'rgba(0, 255, 204, 0.3)');
            }

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

                            if (d.t === 'debris' && !firstDebrisLogged) {
                                console.log(`Primer debris prop. -> alt=${alt.toFixed(4)}, lat=${satLib.degreesLat(posGeo.latitude).toFixed(4)}, lng=${satLib.degreesLong(posGeo.longitude).toFixed(4)}`);
                                firstDebrisLogged = true;
                            }

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
            document.getElementById('ui').innerHTML = "❌ JS ERROR: " + e.message;
        }
    </script>
</body>
</html>
'''

html_final = template_html.replace("__SATELLITE_JS__", assets['satellite'])
html_final = html_final.replace("__GLOBE_JS__", assets['globe'])
html_final = html_final.replace("__GEOJSON__", assets['geojson'])
html_final = html_final.replace("__DATA__", json.dumps(tle_payload))
html_final = html_final.replace("__IS_DANGER__", str(is_danger).lower())
html_final = html_final.replace("__DANGER_CLASS__", "danger" if is_danger else "")
html_final = html_final.replace("__RADAR_MSG__", radar_message)
html_final = html_final.replace("__COUNT__", str(len(tle_payload)))

components.html(html_final, height=800)
