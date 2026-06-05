const INITIAL_CENTER = [36.628, 127.456];
const map = L.map("map").setView(INITIAL_CENTER, 16);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const segmentLayer = L.layerGroup().addTo(map);
const eventLayer = L.layerGroup().addTo(map);
const pathLayer = L.layerGroup().addTo(map);
const comparisonLayer = L.layerGroup().addTo(map);

let payload = null;
let selectedSession = null;

async function loadDemo() {
  const response = await fetch("demo_data.json");
  if (!response.ok) {
    throw new Error(`demo_data.json 로딩 실패: HTTP ${response.status}`);
  }
  payload = await response.json();
  populateSessions(payload.sessions);
  selectedSession = payload.sessions[0];
  render();
}

function populateSessions(sessions) {
  const select = document.getElementById("session-list");
  select.innerHTML = "";
  for (const session of sessions) {
    const option = document.createElement("option");
    option.value = session.name;
    option.textContent = `${session.name} · ${session.session.session_id}`;
    select.appendChild(option);
  }
  select.addEventListener("change", () => {
    selectedSession = payload.sessions.find((session) => session.name === select.value);
    render();
  });
}

function render() {
  clearLayers();
  const viewMode = document.getElementById("view-mode").value;
  if (viewMode === "comparison") {
    renderComparisonMode(payload.comparison, payload.sessions);
    renderSummary(payload.comparison);
    return;
  }

  renderPath(selectedSession.gps);
  renderSegments(selectedSession.segments);
  renderEvents(selectedSession.events);
  renderSummary(payload.comparison);
}

function renderPath(gpsRows) {
  const coords = gpsRows
    .filter((row) => Number(row.gps_valid) === 1)
    .map((row) => [row.lat, row.lon]);
  if (coords.length >= 2) {
    L.polyline(coords, { color: "#64748b", weight: 3, opacity: 0.6 }).addTo(pathLayer);
    map.fitBounds(L.latLngBounds(coords), { padding: [32, 32] });
  }
}

function renderSegments(segments) {
  for (const segment of segments) {
    const events = segment.events || [];
    if (events.length === 0) continue;
    const lat = average(events.map((event) => event.lat));
    const lon = average(events.map((event) => event.lon));
    const marker = L.circleMarker([lat, lon], {
      radius: 12,
      color: segmentColor(segment.risk_level),
      fillColor: segmentColor(segment.risk_level),
      fillOpacity: 0.22,
      weight: 3,
    });
    marker.bindPopup(segmentPopup(segment));
    marker.on("click", () => showDetails(segmentPopup(segment)));
    marker.addTo(segmentLayer);
  }
}

function renderEvents(events) {
  const dangerOnly = document.getElementById("danger-only").checked;
  const gpsValidOnly = document.getElementById("gps-valid-only").checked;
  const minConfidence = Number(document.getElementById("confidence-filter").value);
  document.getElementById("confidence-value").textContent = minConfidence.toFixed(2);

  for (const event of events) {
    if (gpsValidOnly && Number(event.gps_valid) !== 1) continue;
    if (dangerOnly && !["caution", "danger", "candidate"].includes(event.prediction)) continue;
    if (Number(event.confidence) < minConfidence) continue;

    const marker = L.circleMarker([event.lat, event.lon], {
      radius: 5 + Number(event.risk_score) * 6,
      color: segmentColor(event.prediction),
      fillColor: segmentColor(event.prediction),
      fillOpacity: 0.82,
      weight: 1,
    });
    marker.bindPopup(eventPopup(event));
    marker.on("click", () => showDetails(eventPopup(event)));
    marker.addTo(eventLayer);
  }
}

function renderSummary(comparison) {
  const counts = comparison.reduce((acc, row) => {
    acc[row.status] = (acc[row.status] || 0) + 1;
    return acc;
  }, {});
  document.getElementById("summary").innerHTML = `
    <dl>
      <dt>개선</dt><dd>${counts.improved || 0}</dd>
      <dt>악화</dt><dd>${counts.worsened || 0}</dd>
      <dt>새 위험</dt><dd>${counts.new_risk || 0}</dd>
      <dt>비교 불가</dt><dd>${counts.not_comparable || 0}</dd>
    </dl>
  `;
}

function clearLayers() {
  segmentLayer.clearLayers();
  eventLayer.clearLayers();
  pathLayer.clearLayers();
  comparisonLayer.clearLayers();
}

function segmentColor(level) {
  if (level === "danger") return "#dc2626";
  if (level === "caution" || level === "candidate") return "#f97316";
  return "#64748b";
}

function renderComparisonMode(comparison, sessions) {
  const segmentById = new Map();
  for (const session of sessions) {
    for (const segment of session.segments || []) {
      if (!segmentById.has(segment.segment_id)) {
        segmentById.set(segment.segment_id, segment);
      }
    }
  }

  for (const row of comparison) {
    if (!["improved", "worsened", "new_risk"].includes(row.status)) continue;
    const segment = segmentById.get(row.segment_id);
    if (!segment) continue;
    const lat = Number(segment.center_lat);
    const lon = Number(segment.center_lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

    const popup = comparisonPopup(row);
    const marker = L.circleMarker([lat, lon], {
      radius: 16,
      color: statusColor(row.status),
      fillColor: statusColor(row.status),
      fillOpacity: 0.14,
      weight: 4,
    });
    marker.bindPopup(popup);
    marker.on("click", () => showDetails(popup));
    marker.addTo(comparisonLayer);
  }
}

function statusColor(status) {
  if (status === "improved") return "#16a34a";
  if (status === "worsened") return "#dc2626";
  if (status === "new_risk") return "#7c3aed";
  return "#64748b";
}

function segmentPopup(segment) {
  return `
    <strong>${segment.segment_id}</strong><br>
    위험 수준: ${segment.risk_level}<br>
    이벤트 수: ${segment.event_count}<br>
    평균 점수: ${Number(segment.avg_risk_score).toFixed(2)}<br>
    최대 점수: ${Number(segment.max_risk_score).toFixed(2)}<br>
    반복 검출 비율: ${(Number(segment.repeated_detection_ratio) * 100).toFixed(1)}%
  `;
}

function eventPopup(event) {
  return `
    <strong>${event.prediction}</strong><br>
    risk: ${Number(event.risk_score).toFixed(2)} / confidence: ${Number(event.confidence).toFixed(2)}<br>
    사진: ${event.photo_before || "없음"}<br>
    GPS: ${event.lat.toFixed(6)}, ${event.lon.toFixed(6)}
  `;
}

function comparisonPopup(row) {
  return `
    <strong>전/후 비교</strong><br>
    상태: ${comparisonStatusLabel(row.status)}<br>
    before: ${Number(row.before_score || 0).toFixed(2)}<br>
    after: ${Number(row.after_score || 0).toFixed(2)}<br>
    개선율: ${row.improvement_rate === null ? "N/A" : `${(Number(row.improvement_rate) * 100).toFixed(1)}%`}
  `;
}

function comparisonStatusLabel(status) {
  if (status === "improved") return "개선";
  if (status === "worsened") return "악화";
  if (status === "new_risk") return "새 위험";
  if (status === "unchanged_clean") return "양호 유지";
  return "비교 불가";
}

function showDetails(html) {
  document.getElementById("details").innerHTML = html;
}

function average(values) {
  return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

for (const id of ["danger-only", "gps-valid-only", "confidence-filter", "view-mode"]) {
  document.getElementById(id).addEventListener("input", render);
}

loadDemo().catch((error) => {
  document.getElementById("summary").textContent = error.message;
});
