# coding: utf-8
"""
Generate a Leaflet HTML map from a CSV (English UI + immediate filters) with
an educational fullscreen modal triggered by a "Source" link inside each popup.

Minimal changes applied:
 - Modal shows two clickable links inside the message:
   • Restore instructions -> shows second didactic alert (no navigation)
   • About the group -> opens the provided YouTube link (or fallback) in new tab
 - The popup anchor now carries data-yt and data-orig attributes so modal can act.
"""
import pandas as pd
import json
import os
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from dateutil import parser as dateparser

# ---------- CONFIG ----------
csv_path = r"C:/Users/bengu/Documents/cyber_nld/cyber_ndl.csv"  # <-- set your CSV path
out_html = r"C:/Users/bengu/Documents/cyberattacks_nl_2024_map_with_modal.html"
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
df["company_domain"] = df["company_domain"].astype(str).str.strip()
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
    domain = row["company_domain"].strip() if row["company_domain"] else ""
    rdict = {
        "date_raw": row["date"],
        "date_iso": row["_date_iso"],  # may be None
        "place": place,
        "company": company,
        "company_domain": domain,
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

# ---------- HTML TEMPLATE ----------
# placeholders: __ATTACK_OPTIONS__ and __DATA_JSON__
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
  /* Modal styles (fullscreen, green-on-black) */
  #eduModal { display:none; }
  #eduOverlay {
    position:fixed; inset:0; background:rgba(0,0,0,0.85); z-index:2000;
  }
  #eduDialog {
    position:fixed; inset:0; width:100%; height:100%; background:#000; color:#00ff66;
    z-index:2001; overflow:auto; display:flex; align-items:center; justify-content:center; padding:28px;
  }
  /* Inner container for image + content */
  #eduInner { display:flex; gap:18px; max-width:1100px; width:100%; }
  #eduImage { width:320px; max-width:38%; height:220px; object-fit:cover; border-radius:8px; border:1px solid #003300 }
  #eduText { flex:1; min-width:220px; }
  #eduDialog h1 { margin:0 0 10px 0; font-size:22px; color:#00ff66; }
  #eduContent { flex:1; overflow:auto; }
  #eduDialog .small { font-size:13px; color:#a8f0b6; }
  #eduCloseBtn { padding:10px 14px; border-radius:6px; border:none; background:#00a64d; color:white; cursor:pointer; }
  #eduCloseBtn[aria-hidden="true"]{ display:none; }
  .simPre { white-space:pre-wrap; background:#000; color:#00ff66; padding:12px; border-radius:6px; overflow:auto; border:1px solid #003300 }
  a.educational-warning { color:#7fffb5; text-decoration:underline; }

  /* Progress bar (green on black) */
  .progressWrap { margin-top:12px; background:#001a00; border:1px solid #003300; border-radius:8px; padding:6px; }
  .progressBar { height:18px; width:100%; background:#000; border-radius:6px; overflow:hidden; }
  .progressFill { height:100%; width:0%; background:linear-gradient(90deg,#00ff66,#00aa44); box-shadow:0 0 8px rgba(0,170,68,0.6); transition:width 0.2s linear; }
  .progressLabel { margin-top:6px; font-size:13px; color:#a8f0b6; }

  /* Second inline alert (appears inside modal) */
  #eduSecondAlert {
    position:fixed; inset:0; z-index:3000; display:none; align-items:center; justify-content:center;
  }
  #eduSecondBox {
    background:#000; border:2px solid #ff8800; color:#ffcc66; padding:22px; border-radius:10px; width:min(760px,94%);
    box-shadow:0 12px 40px rgba(0,0,0,0.8);
  }
  #eduSecondBox h2{margin:0 0 8px 0; font-size:20px; color:#ffcc66}
  #eduSecondBox p{color:#ffdca8; margin:8px 0}

  /* Responsive: stack image on small screens */
  @media (max-width:720px){
    #eduInner{flex-direction:column; align-items:stretch}
    #eduImage{width:100%; height:180px; max-width:none}
  }
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
  <div class="small">Note: Data mainly extracted from official websites of attacked companies and state services.</div>
</div>

<div id="map"></div>

<div class="legend">
  <div style="font-weight:700;margin-bottom:6px">Legend</div>
  <div style="margin-bottom:6px"><span class="dot" style="background:crimson;border-color:crimson"></span> State-related</div>
  <div style="margin-bottom:6px"><span class="dot" style="background:gold;border-color:gold"></span> AddComm attack</div>
  <div style="margin-bottom:6px"><span class="dot" style="background:grey;border-color:grey"></span> Derived from Addcom attack</div>
  <div><span class="dot" style="background:black;border-color:black"></span> Others</div>
</div>

<!-- Educational fullscreen modal (hidden by default) -->
<div id="eduModal" aria-hidden="true">
  <div id="eduOverlay"></div>
  <div id="eduDialog" role="dialog" aria-modal="true" aria-labelledby="eduTitle" tabindex="-1">
    <div id="eduInner">
      <img id="eduImage" src="C:/Users/bengu/Documents/cyber_nld/image.jpeg" alt="Educational image" />
      <div id="eduText">
        <h1 id="eduTitle">⚠️ Simulated Security Incident — Educational</h1>
        <div id="eduContent">
          <p>This is a message from the <span id="eduPerpStatic">—</span> team.</p>

          <!-- message area: using <div> so inserted HTML (lists & anchors) render properly -->
          <div class="simPre" id="eduPre">Sample incident: "Some service reports data exfiltration after following a malicious link."</div>

          <p class="large">FILE ENCRYPTING PROCESS -- DO NOT TRY TO INTERRUPT</p>

          <div class="progressWrap">
            <div class="progressBar" aria-hidden="true"><div id="eduProgressFill" class="progressFill"></div></div>
            <div id="eduProgressLabel" class="progressLabel">Progress: 0%</div>
          </div>


          <label style="display:block;margin-top:10px; color:#a8f0b6;">
            <input type="checkbox" id="eduAcknowledge"> Stop the encrypting process and open discussion canal with us.
          </label>
          <div style="margin-top:12px;">
            <button id="eduCloseBtn" aria-hidden="true">Close</button>

            <p id="eduDisclaimer" class="small" style="display:none; color:rebeccapurple;">
  This popup is intentionally attention-grabbing for training purposes. Please pay attention before clicking anywhere, it could prevent you from having to deal with real hackers!
</p>

          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Second ephemeral alert (appears on "Restore instructions") -->
<div id="eduSecondAlert" aria-hidden="true">
  <div id="eduSecondBox" role="dialog" aria-modal="true">
    <h2>Not only you clicked on a dangerous unknown link, but you keep going !</h2>
    <p>This second popup is intentionally blunt: continuing to interact with unknown, coercive instructions increases risk. Close this warning and use official channels to verify any notification.</p>
    <div style="margin-top:12px; text-align:right;">
      <button id="eduSecondClose" style="padding:8px 12px; border-radius:6px; border:none; background:#aa5500; color:white;">Understood</button>
    </div>
  </div>
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

  function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  function ensureFullUrl(u){
    if(!u) return '';
    try{ if(u.match(/^https?:\/\//i)) return u; }catch(e){}
    return 'https://' + u.replace(/^\/+/, '');
  }

  function makePopupHtml(r){
    const dateText = r.date_iso ? new Date(r.date_iso).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'}) : (r.date_raw || 'Unknown date');
    const place = r.place || '—';
    const company = r.company || '—';
    const perpetrator = r.perpetrator || '—';
    const consequence = r.consequence || '—';

    // Prefer a real company domain if available, otherwise fallback to example.com/report/123
    let rawUrl = (r.company_domain && r.company_domain.trim()) ? r.company_domain.trim() : 'https://example.com/report/123';
    rawUrl = ensureFullUrl(rawUrl);

    // For the 'about' (video) link, if the company_domain looks like a YouTube url use it
    let yt_candidate = '';
    if(r.company_domain && /youtube\\.com|youtu\\.be/i.test(r.company_domain)) {
      yt_candidate = ensureFullUrl(r.company_domain.trim());
    }

    const displayUrlText = escapeHtml(rawUrl);

    // Anchor transports metadata that the modal will consume. We keep href so user sees actual link on hover.
    return `
      <div class="popup-company">${escapeHtml(company)}</div>
      <div class="popup-meta">${escapeHtml(place)} — ${escapeHtml(dateText)}</div>
      <div><strong>Perpetrator:</strong> ${escapeHtml(perpetrator)}</div>
      <div><strong>Consequence:</strong> ${escapeHtml(consequence)}</div>
      <div style="margin-top:8px;">
        Source: <a href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener noreferrer" class="educational-warning"
                  data-title="${escapeHtml("YOUR FILES ARE GETTING ENCRYPTED")}"
                  data-yt="${escapeHtml(yt_candidate)}"
                  data-orig="${escapeHtml(rawUrl)}"
                  data-company="${escapeHtml(company)}"
                  data-perp="${escapeHtml(perpetrator)}"
                  data-date="${escapeHtml(dateText)}"
                  >${displayUrlText}</a>
      </div>
    `;
  }

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

  // --- Educational modal logic (fullscreen behaviour + show Close only after ack) ---
(function(){
  const modalWrap = document.getElementById('eduModal');
  const ackCheckbox = document.getElementById('eduAcknowledge');
  const closeBtn = document.getElementById('eduCloseBtn');
  const eduPre = document.getElementById('eduPre'); // message container (HTML)
  const eduTitle = document.getElementById('eduTitle');
  const eduFill = document.getElementById('eduProgressFill');
  const eduLabel = document.getElementById('eduProgressLabel');

  const secondAlertWrap = document.getElementById('eduSecondAlert');
  const secondClose = document.getElementById('eduSecondClose');
  const perpSpan = document.getElementById('eduPerpStatic');

  let progressTimer = null;
  let currentYt = '';
  let currentOrig = '';
  let currentPerp = '';
  let currentDateText = '';

  function setProgress(p){
    const pct = Math.max(0, Math.min(99, Math.round(p)));
    eduFill.style.width = pct + '%';
    eduLabel.textContent = 'Progress: ' + pct + '%';
  }

  function startProgress(){
    let progress = 0;
    setProgress(progress);
    if(progressTimer) clearTimeout(progressTimer);

    function step(){
      const remaining = 99 - progress;
      if(remaining <= 0){
        setProgress(99);
        progressTimer = null;
        return;
      }
      const maxStep = Math.max(0.06, remaining / 80);
      const stepAmt = (Math.random() * maxStep) + (Math.random() < 0.22 ? Math.random() * 0.6 : 0);
      progress = Math.min(99, progress + stepAmt);
      setProgress(progress);

      let delay = 800 + Math.random() * 2600;
      if(Math.random() < 0.18) delay += 800 + Math.random() * 2600;
      progressTimer = setTimeout(step, delay);
    }

    const initialDelay = 500 + Math.random() * 900;
    progressTimer = setTimeout(step, initialDelay);
  }

  function resetProgress(){
    if(progressTimer) clearTimeout(progressTimer);
    progressTimer = null;
    setProgress(0);
  }

  // helper to sanitize a name for inclusion in a fake URL segment
  function sanitizeForUrl(s){
    if(!s) return 'unknown';
    return String(s).trim().replace(/\s+/g, '_').replace(/[^A-Za-z0-9_\-]/g, '') || 'unknown';
  }

  async function openEduModalFromAnchor(anchor){
  // read attributes (robust fallbacks)
  const title = anchor.getAttribute('data-title') || 'YOUR FILES ARE GETTING ENCRYPTED';
  const yt = anchor.getAttribute('data-yt') || '';
  const orig = anchor.getAttribute('data-orig') || '';
  // prefer explicit data-perp, else company, else ''
  const perpAttr = anchor.getAttribute('data-perp');
  const companyAttr = anchor.getAttribute('data-company');
  const perp = (perpAttr && perpAttr.trim()) ? perpAttr.trim() : ((companyAttr && companyAttr.trim()) ? companyAttr.trim() : '');
  const dateText = anchor.getAttribute('data-date') || '';

  // decide display name (use Lockit when unknown)
  const displayPerp = (perp && perp.length > 0) ? perp : 'Lockit';

  // store for handlers (use displayPerp so handlers see fallback name)
  currentYt = yt || '';
  currentOrig = orig || '';
  currentPerp = displayPerp;
  currentDateText = dateText || '';

  // show perp in the header zone
  if(perpSpan) perpSpan.textContent = displayPerp;

  // set modal title
  eduTitle.textContent = title;

  // construct disguised (display) URLs but keep actual click behaviour separate
  const perpForUrl = sanitizeForUrl(displayPerp);
  const restoreDisplay = 'https://restore_file_help_plan.com';
  const aboutDisplay = 'https://communication_' + perpForUrl + '_group.com';

  // build HTML message (we escape dynamic bits)
  const messageHtml =
    '<p>Don\\'t worry, you can return all your files!</p>' +
    '<p>If you want to restore them follow this link: <a href="#" class="eduInlineRestore">' + escapeHtml(restoreDisplay) + '</a></p>' +
    '<p><strong>Attention</strong></p>' +
    '<ul>' +
      '<li>Do not rename encrypted files</li>' +
      '<li>Do not try to decrypt your data using third party software, it may cause permanent data loss</li>' +
      '<li>Decryption of your file with the help of third parties may cause increased price</li>' +
    '</ul>' +
    '<p>Learn more about the ' + escapeHtml(displayPerp) + ' team at <a href="#" class="eduInlineAbout">' + escapeHtml(aboutDisplay) + '</a></p>';

  // put HTML into message container
  eduPre.innerHTML = messageHtml;

  // ensure disclaimer hidden at modal open
  const disclaimer = document.getElementById('eduDisclaimer');
  if(disclaimer) disclaimer.style.display = 'none';

  // reset ack / close visibility, show modal
  ackCheckbox.checked = false;
  closeBtn.setAttribute('aria-hidden','true');
  closeBtn.style.display = 'none';
  modalWrap.style.display = 'block';
  modalWrap.setAttribute('aria-hidden','false');
  document.getElementById('eduDialog').focus();

  // start progress simulation
  startProgress();

  // attach handlers to inline links injected above

  // Restore: exit fullscreen if active, THEN show the second didactic alert
  const inlineRestore = modalWrap.querySelector('.eduInlineRestore');
  if(inlineRestore){
    inlineRestore.addEventListener('click', async function(ev){
      ev.preventDefault();
      try {
        if(document.fullscreenElement){
          await document.exitFullscreen();
        }
      } catch(err){
        console.warn('exitFullscreen failed:', err);
      }
      setTimeout(function(){
        secondAlertWrap.style.display = 'flex';
        secondAlertWrap.setAttribute('aria-hidden','false');
      }, 120);
    });
  }

  // About: open data-yt if provided, otherwise rickroll (but text stays the disguised aboutDisplay)
  const inlineAbout = modalWrap.querySelector('.eduInlineAbout');
  if(inlineAbout){
    inlineAbout.addEventListener('click', function(ev){
      ev.preventDefault();
      const rick = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';
      if(currentYt && currentYt.trim()){
        window.open(currentYt, '_blank', 'noopener');
      } else {
        window.open(rick, '_blank', 'noopener');
      }
    });
  }

  // Try to request fullscreen (best-effort; browsers only allow in user gesture contexts)
  try{
    const el = document.getElementById('eduDialog');
    if(el.requestFullscreen){
      await el.requestFullscreen();
    }
  }catch(err){
    console.warn('Fullscreen request failed or was denied:', err);
  }
}


  function closeEduModal(){
    modalWrap.style.display = 'none';
    modalWrap.setAttribute('aria-hidden','true');
    try{
      if(document.fullscreenElement){
        document.exitFullscreen();
      }
    }catch(e){/* ignore */}
    resetProgress();
  }

  // second alert controls
  secondClose.addEventListener('click', function(){
    secondAlertWrap.style.display = 'none';
    secondAlertWrap.setAttribute('aria-hidden','true');
  });

  // --- replace existing ackCheckbox 'change' handler with this ---
ackCheckbox.addEventListener('change', function(){
  const disclaimer = document.getElementById('eduDisclaimer');
  if(this.checked){
    // show Close button
    closeBtn.style.display = 'inline-block';
    closeBtn.removeAttribute('aria-hidden');
    closeBtn.focus();

    // show the disclaimer at the same time (styled in purple)
    if(disclaimer){
      disclaimer.style.display = 'block';
      disclaimer.style.color = 'rebeccapurple';
      // optional: make it slightly more visible (increase weight)
      disclaimer.style.fontWeight = '600';
    }
  } else {
    // hide Close button again
    closeBtn.setAttribute('aria-hidden','true');
    closeBtn.style.display = 'none';

    // hide disclaimer again
    if(disclaimer){
      disclaimer.style.display = 'none';
    }
  }
});


  closeBtn.addEventListener('click', function(){
    closeEduModal();
  });

  // Delegate clicks on links with class 'educational-warning' (popup anchors)
  document.addEventListener('click', function(ev){
    const a = ev.target.closest && ev.target.closest('a.educational-warning');
    if(!a) return;
    ev.preventDefault(); // stop normal navigation
    openEduModalFromAnchor(a);
  }, false);

  // Prevent Escape from closing modal (best-effort)
  document.addEventListener('keydown', function(ev){
    if(ev.key === 'Escape'){
      if(modalWrap.style.display === 'block'){
        ev.preventDefault();
        ev.stopPropagation();
      }
    }
  }, true);

  // Keep listening to fullscreenchange purely for awareness (no auto-close):
  document.addEventListener('fullscreenchange', function(){
    if(!document.fullscreenElement){
      // user exited fullscreen — modal stays visible; we do not auto-close it.
    }
  });

})(); // end IIFE


</script>
</body>
</html>
"""

# ---------- FILL PLACEHOLDERS & WRITE ----------
html_filled = html_template.replace("__ATTACK_OPTIONS__", attack_options).replace("__DATA_JSON__", data_json)

with open(out_html, "w", encoding="utf8") as f:
    f.write(html_filled)

print(f"Done — HTML file generated: {out_html}")
print("Place modal_image.jpg (or your image) next to the generated HTML and open the file in a modern browser to test.")
