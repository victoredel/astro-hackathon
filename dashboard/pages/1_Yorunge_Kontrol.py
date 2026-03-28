import streamlit as st
import streamlit.components.v1 as components
import json
import requests

st.set_page_config(page_title="Yörünge Kontrol", page_icon="🛰️", layout="wide")

st.title("🛰️ TUA Küresel Yörünge Takip - Canlı 60 FPS")

# 1. Descargador Múltiple (Intenta varias fuentes hasta lograrlo)
@st.cache_resource
def load_assets():
    assets = {"globe": "", "satellite": "", "geojson": "{}"}
    
    # Intentar descargar Globe.gl
    for url in ["https://cdn.jsdelivr.net/npm/globe.gl", "https://unpkg.com/globe.gl"]:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and not r.text.strip().startswith("<"):
                assets["globe"] = r.text
                break
        except: pass
        
    # Intentar descargar Satellite.js
    for url in ["https://cdn.jsdelivr.net/npm/satellite.js/dist/satellite.min.js", "https://unpkg.com/satellite.js/dist/satellite.min.js"]:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200 and not r.text.strip().startswith("<"):
                assets["satellite"] = r.text
                break
        except: pass
        
    # Descargar Divisiones Políticas (GeoJSON) en el servidor para evitar bloqueos en el navegador
    try:
        r = requests.get("https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json", timeout=5)
        if r.status_code == 200:
            assets["geojson"] = r.text
    except: pass

    return assets

assets = load_assets()

# Validar que el contenedor Docker tenga internet
if not assets["globe"] or not assets["satellite"]:
    st.error("❌ HATA: Docker sunucusu kütüphaneleri indiremedi. Lütfen sunucunun internet erişimini kontrol edin.")
    st.stop()

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
                    data.append({"n": lines[i].strip(), "l1": lines[i+1].strip(), "l2": lines[i+2].strip(), "t": cat})
        except: pass
    return data

tle_payload = get_space_data()

st.sidebar.header("🌞 Uzay Havası")
storm_prob = st.sidebar.slider("Fırtına Olasılığı (%)", 0, 100, 25)
is_danger = 1 if storm_prob > 75 else 0

# --- ESTRUCTURA HTML (MODO RADAR NEGRO) ---
# Pure string — NO f-string. All dynamic values injected via .replace()
template_html = '''
<!DOCTYPE html>
<html>
<head>
    <style> body { margin: 0; background: #000; overflow: hidden; font-family: monospace; } #ui { position: absolute; top: 10px; left: 10px; color: #0ff; z-index: 10; } </style>
    <script>__SATELLITE_JS__</script>
    <script>__GLOBE_JS__</script>
</head>
<body>
    <div id="ui">🛰️ AKTIF | NESNE: __COUNT__</div>
    <div id="globeViz"></div>

    <script>
        try {
            if (typeof Globe === 'undefined') throw new Error("Globe kütüphanesi başlatılamadı.");

            const rawData = __DATA__;
            const isDanger = __DANGER__;
            const geoJsonData = __GEOJSON__;
            const satLib = satellite;
            
            const timeMultiplier = 60; // 1 segundo real = 1 min orbital
            const startTime = Date.now();

            // Configuración del Globo: NEGRO ABSOLUTO
            const world = Globe()(document.getElementById('globeViz'))
                .backgroundColor('#000000')
                .showAtmosphere(true)
                .atmosphereColor('#00ccff')
                .pointRadius(0.8)
                .pointColor(d => d.t === 'active' ? '#00ffcc' : (isDanger ? '#ff0000' : '#ff9900'))
                .pointAltitude(d => d.alt || 0.1)
                .width(window.innerWidth)
                .height(800);

            // Aplicar globeColor separado para no romper chain si falla
            try { world.globeColor('#000000'); } catch(e) { console.warn('globeColor no soportado:', e); }

            // Renderizar divisiones políticas si se descargaron correctamente
            if (geoJsonData && geoJsonData.features) {
                try {
                    world.hexPolygonsData(geoJsonData.features)
                         .hexPolygonResolution(3)
                         .hexPolygonMargin(0.1)
                         .hexPolygonColor(() => 'rgba(0, 255, 204, 0.3)');
                } catch(e) { console.warn('hexPolygons error:', e); }
            }

            const satData = rawData.map(d => {
                try {
                    return { ...d, satrec: satLib.twoline2satrec(d.l1, d.l2) };
                } catch(e) { return null; }
            }).filter(s => s !== null);

            document.getElementById('ui').innerHTML = '🛰️ AKTIF | NESNE: ' + satData.length;

            function update() {
                try {
                    const elapsed = Date.now() - startTime;
                    const simTime = new Date(startTime + elapsed * timeMultiplier);
                    const gmst = satLib.gstime(simTime);
                    
                    const points = satData.map(d => {
                        try {
                            const posVel = satLib.propagate(d.satrec, simTime);
                            if (!posVel.position || posVel.position.x === false) return null;
                            const posGeo = satLib.eciToGeodetic(posVel.position, gmst);
                            let alt = (posGeo.height / 6371) || 0.1;
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
                } catch(e) { console.error("Update error:", e); }
                requestAnimationFrame(update);
            }

            world.pointOfView({ lat: 39, lng: 35, alt: 2.5 });
            update();
            window.onresize = () => world.width(window.innerWidth).height(800);
        } catch(e) {
            document.getElementById('ui').style.color = "red";
            document.getElementById('ui').innerHTML = "❌ HATA: " + e.message;
        }
    </script>
</body>
</html>
'''

# Reemplazo seguro de variables — sin f-strings
final_html = template_html.replace("__SATELLITE_JS__", assets['satellite'])
final_html = final_html.replace("__GLOBE_JS__", assets['globe'])
final_html = final_html.replace("__GEOJSON__", assets['geojson'])
final_html = final_html.replace("__COUNT__", str(len(tle_payload)))
final_html = final_html.replace("__DANGER__", str(is_danger))
final_html = final_html.replace("__DATA__", json.dumps(tle_payload))

components.html(final_html, height=800)
