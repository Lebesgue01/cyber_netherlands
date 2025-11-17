"""
Generate a Leaflet HTML map from a CSV (English UI + immediate filters).

- Edit csv_path to point to your CSV file.
- Caches geocoding results to geo_cache.json (Nominatim).
- Filters (date range, attack_type, state_related) are applied immediately on change.
- No Apply/Reset buttons.
"""

import pandas as pd
import json
import os
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from dateutil import parser as dateparser

# ---------- CONFIG ----------
csv_path = r"C:/Users/bengu/Documents/cyber_ndl.csv"  # <-- set your CSV path
out_html = "C:/Users/bengu/Documents/cyberattacks_nl_2024_map.html"
geo_cache_file = "geo_cache.json"
DEFAULT_YEAR = 2024
NL_CENTER = {"lat": 52.132633, "lon": 5.291266}  # fallback coords

# ---------- UTIL ----------
def load_geo_cache(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_geo_cache(cache, path):
    with open(path, "w", encoding="utf8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def normalize_bool(x):
    if pd.isna(x): return False
    s = str(x).strip().lower()
    return s in ("true", "1", "yes", "y", "t")

def parse_date_cell(v):
    """Try to parse values like 'Jan 17' (assume DEFAULT_YEAR) or full dates. Return ISO date or None."""
    if pd.isna(v) or str(v).strip() == "":
        return None
    s = str(v).strip()
    try:
        if str(DEFAULT_YEAR) in s:
            dt = dateparser.parse(s, dayfirst=False)
        else:
            dt = dateparser.parse(f"{s} {DEFAULT_YEAR}", dayfirst=False)
        return dt.date().isoformat()
    except Exception:
        return None

# ---------- READ CSV ----------
df = pd.read_csv(csv_path, dtype=str).fillna("")

# Ensure expected columns exist
expected_cols = ["date","place","company","company_domain","attack_type","consequence","perpetrator","Addcom_related","state_related"]
for c in expected_cols:
    if c not in df.columns:
        df[c] = ""

# Normalize important columns
df["place"] = df["place"].astype(str).str.strip().str.strip("'\"")
df["company"] = df["company"].astype(str).str.strip()
df["attack_type"] = df["attack_type"].astype(str).str.strip()
df["perpetrator"] = df["perpetrator"].astype(str).str.strip()
df["consequence"] = df["consequence"].astype(str).str.strip()
df["_date_iso"] = df["date"].apply(parse_date_cell)
df["Addcom_related_bool"] = df["Addcom_related"].apply(normalize_bool)
df["state_related_bool"] = df["state_related"].apply(normalize_bool)

# ---------- GEOCODING (Nominatim) with cache ----------
cache = load_geo_cache(geo_cache_file)
geolocator = Nominatim(user_agent="cyberattacks-nl-map-script")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, max_retries=2, error_wait_seconds=2)

unique_places = df["place"].unique().tolist()
for place in unique_places:
    if not place:
        continue
    key = place.lower()
    if key in cache:
        continue
    query = f"{place}, Netherlands"
    try:
        loc = geocode(query, addressdetails=False, exactly_one=True, timeout=10)
        if loc:
            cache[key] = {"lat": loc.latitude, "lon": loc.longitude}
        else:
            cache[key] = None
    except Exception:
        cache[key] = None
    # save incrementally
    save_geo_cache(cache, geo_cache_file)

save_geo_cache(cache, geo_cache_file)

# ---------- BUILD ROWS ----------

rows = []
for _, row in df.iterrows():
    place = row["place"]
    key = place.lower()
    coords = cache.get(key)
    if coords is None:
        lat = NL_CENTER["lat"]
        lon = NL_CENTER["lon"]
    else:
        lat = coords["lat"]
        lon = coords["lon"]
    company = row["company"] or ""
    is_company_addcomm = company.strip().lower() == "addcomm"
    rdict = {
        "date_raw": row["date"],
        "date_iso": row["_date_iso"],  # may be None
        "place": place,
        "company": company,
        "company_domain": row["company_domain"],
        "attack_type": row["attack_type"],
        "consequence": row["consequence"],
        "perpetrator": row["perpetrator"],
        "Addcom_related": bool(row["Addcom_related_bool"]),
        "state_related": bool(row["state_related_bool"]),
        "is_company_addcomm": is_company_addcomm,
        "lat": lat,
        "lon": lon,
    }
    rows.append(rdict)

attack_types = sorted(list({r["attack_type"] for r in rows if r["attack_type"]}))
attack_options = "".join([f'<option value="{a}">{a}</option>' for a in attack_types])

# Prepare JSON safely for embedding (avoid closing </script> issues)
data_json = json.dumps(rows, ensure_ascii=False)
data_json = data_json.replace("</", "<\\/")  # safe-guard

# ---------- HTML TEMPLATE (no f-string) ----------
html_template = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Distribution of Cyberattacks in the Netherlands in 2024</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body,#map{height:100%;margin:0;padding:0}
  body{font-family:system-ui,Segoe UI,Roboto,Arial, sans-serif}
  /* map placed to the right of the left sidebar */
  #map{position:absolute;left:300px;top:0;right:0;bottom:0}
  .sidebar {
    position: absolute;
    left: 12px;
    top: 12px;
    width: 276px;
    bottom: 12px;
    background: rgba(255,255,255,0.98);
    border-radius: 8px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.12);
    padding: 12px;
    overflow:auto;
    z-index:1000;
  }
  .sidebar h2{margin:6px 0 10px 0;font-size:16px}
  .field{margin-bottom:10px}
  label{display:block;font-size:13px;margin-bottom:4px;color:#222}
  input[type=date], select, input[type=text]{width:100%;padding:6px;border-radius:6px;border:1px solid #ddd}
  .small{font-size:12px;color:#555}
  .legend{position:absolute;right:12px;bottom:12px;background:rgba(255,255,255,0.95);padding:8px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.12);z-index:1000}
  .dot{width:14px;height:14px;border-radius:50%;display:inline-block;margin-right:8px;vertical-align:middle;border:1px solid #222}
  .popup-company{font-weight:700;font-size:14px;margin-bottom:6px}
  .popup-meta{font-size:13px;color:#333;margin-bottom:6px}
</style>
</head>
<body>
<div class="sidebar">
  <h2>Filters — Distribution of Cyberattacks in the Netherlands in 2024</h2>

  <div class="field">
    <label for="dateFrom">Date (from)</label>
    <input id="dateFrom" type="date">
  </div>
  <div class="field">
    <label for="dateTo">Date (to)</label>
    <input id="dateTo" type="date">
  </div>
  <div class="field">
    <label for="attackType">Attack type</label>
    <select id="attackType">
      <option value="ALL">All</option>
      __ATTACK_OPTIONS__
    </select>
  </div>
  <div class="field">
    <label><input id="stateOnly" type="checkbox"> Only show state-related incidents (state_related)</label>
  </div>
  <div class="field small">
    <label><input id="includeUnknownDates" type="checkbox" checked> Include events without a date</label>
  </div>

  <hr style="margin:12px 0">
  <div class="small">Note: geocoding is performed via Nominatim (results cached locally). If a place can't be geocoded it will appear at the geographic centre of the Netherlands.</div>
  <div class="small">Note: Data mainly extracted from official websites of attacked companies and state service. </div>
</div>

<div id="map"></div>

<div class="legend">
  <div style="font-weight:700;margin-bottom:6px">Legend</div>
  <div style="margin-bottom:6px"><span class="dot" style="background:crimson;border-color:crimson"></span> State-related</div>
  <div style="margin-bottom:6px"><span class="dot" style="background:gold;border-color:gold"></span> AddComm attack</div>
  <div style="margin-bottom:6px"><span class="dot" style="background:grey;border-color:grey"></span> Derived from Addcom attack</div>
  <div><span class="dot" style="background:black;border-color:black"></span> Others</div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const rows = __DATA_JSON__;

  function markerColor(r){
    if(r.state_related) return 'crimson';
    if(r.is_company_addcomm) return 'gold';
    if(r.Addcom_related) return 'grey';
    return 'black';
  }

  const map = L.map('map').setView([52.09,5.12],7);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);

  let markersLayer = L.layerGroup().addTo(map);

  function makePopupHtml(r){
    const dateText = r.date_iso ? new Date(r.date_iso).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'}) : (r.date_raw || 'Unknown date');
    const place = r.place || '—';
    const company = r.company || '—';
    const perpetrator = r.perpetrator || '—';
    const consequence = r.consequence || '—';
    return `
      <div class="popup-company">${escapeHtml(company)}</div>
      <div class="popup-meta">${escapeHtml(place)} — ${escapeHtml(dateText)}</div>
      <div><strong>Perpetrator:</strong> ${escapeHtml(perpetrator)}</div>
      <div><strong>Consequence:</strong> ${escapeHtml(consequence)}</div>
    `;
  }

  function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  function renderMarkers(){
    markersLayer.clearLayers();
    const attackFilter = document.getElementById('attackType').value;
    const stateOnly = document.getElementById('stateOnly').checked;
    const includeUnknownDates = document.getElementById('includeUnknownDates').checked;
    const dateFrom = document.getElementById('dateFrom').value ? new Date(document.getElementById('dateFrom').value) : null;
    const dateTo = document.getElementById('dateTo').value ? new Date(document.getElementById('dateTo').value) : null;

    const toShow = rows.filter(r=>{
      if(stateOnly && !r.state_related) return false;
      if(attackFilter && attackFilter !== 'ALL' && (r.attack_type || '').trim() !== attackFilter) return false;
      const dt = r.date_iso ? new Date(r.date_iso) : null;
      if(dt){
        if(dateFrom && dt < dateFrom) return false;
        if(dateTo && dt > dateTo) return false;
      } else {
        if(!includeUnknownDates) return false;
      }
      return true;
    });

    const latlngs = [];
    toShow.forEach(r=>{
      const lat = r.lat || 52.132633;
      const lon = r.lon || 5.291266;
      const color = markerColor(r);
      const marker = L.circleMarker([lat,lon], { radius:8, fill:true, fillColor:color, color:color, weight:1, fillOpacity:0.95 });
      marker.bindPopup(makePopupHtml(r));
      marker.addTo(markersLayer);
      latlngs.push([lat,lon]);
    });

    if(latlngs.length>0){
      const bounds = L.latLngBounds(latlngs);
      map.fitBounds(bounds.pad(0.2));
    } else {
      map.setView([52.09,5.12],7);
    }
  }

  // default date range: full year 2024
  document.getElementById('dateFrom').value = '2024-01-01';
  document.getElementById('dateTo').value = '2024-12-31';

  // Immediate filtering: call renderMarkers on input/change events
  document.getElementById('dateFrom').addEventListener('input', renderMarkers);
  document.getElementById('dateTo').addEventListener('input', renderMarkers);
  document.getElementById('attackType').addEventListener('change', renderMarkers);
  document.getElementById('stateOnly').addEventListener('change', renderMarkers);
  document.getElementById('includeUnknownDates').addEventListener('change', renderMarkers);

  // initial render
  renderMarkers();
</script>
</body>
</html>
"""

# ---------- FILL PLACEHOLDERS & WRITE ----------
html_filled = html_template.replace("__ATTACK_OPTIONS__", attack_options).replace("__DATA_JSON__", data_json)

with open(out_html, "w", encoding="utf8") as f:
    f.write(html_filled)

print(f"Done — HTML file generated: {out_html}")
print("Check geo_cache.json for stored coordinates (you can edit them manually if needed).")
