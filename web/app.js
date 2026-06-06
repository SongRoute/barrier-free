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
const imuLayer = L.layerGroup().addTo(map);

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
  applyDefaultView(payload);
  render();
}

function applyDefaultView(data) {
  const defaultView = data && data.presentation && data.presentation.default_view;
  if (!["session", "comparison"].includes(defaultView)) return;
  const select = document.getElementById("view-mode");
  if (select) select.value = defaultView;
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
  updateMarkerScaleLabel();
  renderFinalSummary(payload);
  renderThresholdSummary(payload);
  const viewMode = document.getElementById("view-mode").value;
  const comparison = comparisonRows(payload);
  if (viewMode === "comparison") {
    if (comparison.length === 0) {
      renderPath(selectedSession.gps);
      renderImuHeatRoute(selectedSession.imu_windows || []);
      renderSegments(selectedSession.segments);
      renderEvents(selectedSession.events);
      renderSessionSummary(selectedSession, payload);
      showDetails("이 payload에는 전/후 비교 데이터가 없습니다. 세션 선택 화면으로 확인하세요.");
      return;
    }
    renderComparisonMode(comparison, payload.sessions || []);
    renderComparisonSummary(comparison);
    return;
  }

  renderPath(selectedSession.gps);
  renderImuHeatRoute(selectedSession.imu_windows || []);
  renderSegments(selectedSession.segments);
  renderEvents(selectedSession.events);
  renderSessionSummary(selectedSession, payload);
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
      radius: scaledMarkerRadius(4),
      color: segmentColor(segment.risk_level),
      fillColor: segmentColor(segment.risk_level),
      fillOpacity: 0.42,
      weight: scaledStrokeWeight(1.5),
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
      radius: scaledMarkerRadius(2.5 + Number(event.risk_score) * 2.5),
      color: segmentColor(event.prediction),
      fillColor: segmentColor(event.prediction),
      fillOpacity: 0.82,
      weight: scaledStrokeWeight(1),
    });
    marker.bindPopup(eventPopup(event));
    marker.on("click", () => showDetails(eventPopup(event)));
    marker.addTo(eventLayer);
  }
}

function renderImuHeatRoute(windows) {
  if (!document.getElementById("imu-heat-toggle").checked) return;

  const validWindows = windows.filter((row) => {
    const lat = Number(row.lat);
    const lon = Number(row.lon);
    return Number(row.gps_valid) === 1 && Number.isFinite(lat) && Number.isFinite(lon);
  });
  if (validWindows.length === 0) return;

  for (let index = 0; index < validWindows.length; index += 1) {
    const current = validWindows[index];
    const currentCoord = [Number(current.lat), Number(current.lon)];
    const color = imuColor(Number(current.accel_delta_max));
    const popup = imuWindowPopup(current);

    if (index > 0) {
      const prev = validWindows[index - 1];
      const prevCoord = [Number(prev.lat), Number(prev.lon)];
      const line = L.polyline([prevCoord, currentCoord], {
        color,
        weight: 7,
        opacity: 0.72,
      });
      line.bindPopup(popup);
      line.on("click", () => showDetails(popup));
      line.addTo(imuLayer);
    }

    const marker = L.circleMarker(currentCoord, {
      radius: scaledMarkerRadius(2 + Math.min(Number(current.accel_delta_max) * 1.5, 3)),
      color,
      fillColor: color,
      fillOpacity: 0.5,
      weight: scaledStrokeWeight(1),
    });
    marker.bindPopup(popup);
    marker.on("click", () => showDetails(popup));
    marker.addTo(imuLayer);
  }
}

function renderFinalSummary(data) {
  const element = document.getElementById("final-summary");
  if (!element) return;

  const summary = data && data.final_summary;
  if (!summary) {
    element.innerHTML = '<p class="empty-summary">최종 데모 요약 없음</p>';
    return;
  }

  const fields = [
    ["route_name", "경로"],
    ["session_count", "전체 세션"],
    ["before_session_count", "before 세션"],
    ["after_session_count", "after 세션"],
    ["before_danger_windows", "before 위험 창"],
    ["after_danger_windows", "after 위험 창"],
    ["danger_reduction_rate", "위험 감소율"],
    ["improved_segment_count", "개선 구간"],
    ["worsened_segment_count", "악화 구간"],
    ["new_risk_segment_count", "새 위험 구간"],
    ["not_comparable_segment_count", "비교 불가"],
  ];
  const rows = summaryRows(summary, fields);
  element.innerHTML = rows || '<p class="empty-summary">최종 데모 요약 없음</p>';
}

function renderThresholdSummary(data) {
  const element = document.getElementById("threshold-summary");
  if (!element) return;

  const thresholds = data && data.thresholds;
  if (!thresholds) {
    element.innerHTML = '<p class="empty-summary">탐지 기준 없음</p>';
    return;
  }

  const fields = [
    ["caution_delta", "주의 delta"],
    ["danger_delta", "위험 delta"],
    ["danger_jerk", "위험 jerk"],
  ];
  const rows = summaryRows(thresholds, fields);
  element.innerHTML = rows || '<p class="empty-summary">탐지 기준 없음</p>';
}

function renderComparisonSummary(comparison) {
  const counts = comparisonCounts(comparison);
  document.getElementById("summary").innerHTML = `
    <dl>
      <dt>개선</dt><dd>${counts.improved || 0}</dd>
      <dt>악화</dt><dd>${counts.worsened || 0}</dd>
      <dt>새 위험</dt><dd>${counts.new_risk || 0}</dd>
      <dt>비교 불가</dt><dd>${counts.not_comparable || 0}</dd>
    </dl>
  `;
}

function comparisonRows(data) {
  if (!data) return [];
  if ((data.comparison || []).length > 0) {
    return data.comparison;
  }
  return data.group_comparison || [];
}

function comparisonCounts(comparison) {
  const group = comparison.find((row) => row.improved_segment_count !== undefined);
  if (group && comparison.every((row) => row.status === undefined)) {
    return {
      improved: Number(group.improved_segment_count || 0),
      worsened: Number(group.worsened_segment_count || 0),
      new_risk: Number(group.new_risk_segment_count || 0),
      not_comparable: Number(group.not_comparable_segment_count || 0),
    };
  }

  return comparison.reduce((acc, row) => {
    acc[row.status] = (acc[row.status] || 0) + 1;
    return acc;
  }, {});
}

function summaryRows(values, fields) {
  const rows = fields
    .filter(([key]) => values[key] !== undefined && values[key] !== null)
    .map(([key, label]) => `<dt>${label}</dt><dd>${formatSummaryValue(values[key], key)}</dd>`);
  if (rows.length === 0) return "";
  return `<dl class="compact-summary">${rows.join("")}</dl>`;
}

function formatSummaryValue(value, key) {
  const number = Number(value);
  if (Number.isFinite(number)) {
    if (key.endsWith("_rate")) return `${(number * 100).toFixed(1)}%`;
    if (Number.isInteger(number)) return String(number);
    return number.toFixed(2);
  }
  return escapeHtml(String(value));
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderSessionSummary(session, data) {
  const gpsRows = session.gps || [];
  const validGpsRows = gpsRows.filter((row) => Number(row.gps_valid) === 1);
  const gpsRatio = gpsRows.length === 0 ? 0 : validGpsRows.length / gpsRows.length;
  const windows = session.imu_windows || [];
  const roughWindows = windows.filter((row) => Number(row.accel_delta_max) >= 0.6);
  const imuRowCount = windows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0);
  document.getElementById("summary").innerHTML = `
    <dl>
      <dt>전체 세션</dt><dd>${(data.sessions || []).length}</dd>
      <dt>선택 세션</dt><dd>${session.session.session_id}</dd>
      <dt>phase</dt><dd>${session.session.phase}</dd>
      <dt>IMU row</dt><dd>${imuRowCount}</dd>
      <dt>GPS valid</dt><dd>${(gpsRatio * 100).toFixed(1)}%</dd>
      <dt>이벤트</dt><dd>${(session.events || []).length}</dd>
      <dt>거친 IMU 창</dt><dd>${roughWindows.length}</dd>
    </dl>
  `;
}

function clearLayers() {
  segmentLayer.clearLayers();
  eventLayer.clearLayers();
  pathLayer.clearLayers();
  comparisonLayer.clearLayers();
  imuLayer.clearLayers();
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
      radius: scaledMarkerRadius(5),
      color: statusColor(row.status),
      fillColor: statusColor(row.status),
      fillOpacity: 0.48,
      weight: scaledStrokeWeight(2),
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

function imuColor(delta) {
  if (delta >= 1.0) return "#dc2626";
  if (delta >= 0.6) return "#f97316";
  if (delta >= 0.25) return "#eab308";
  return "#16a34a";
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
    GPS: ${Number(event.lat).toFixed(6)}, ${Number(event.lon).toFixed(6)}
  `;
}

function imuWindowPopup(row) {
  return `
    <strong>IMU 강도</strong><br>
    시간: ${Number(row.timestamp_start).toFixed(1)} ~ ${Number(row.timestamp_end).toFixed(1)}<br>
    accel max: ${Number(row.accel_mag_max).toFixed(2)}g<br>
    delta max: ${Number(row.accel_delta_max).toFixed(2)}g<br>
    jerk max: ${Number(row.jerk_max).toFixed(2)}<br>
    speed: ${Number(row.speed_mps).toFixed(2)} m/s<br>
    GPS: ${Number(row.lat).toFixed(6)}, ${Number(row.lon).toFixed(6)}
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

function markerScale() {
  const input = document.getElementById("marker-size");
  const value = input ? Number(input.value) : 1;
  if (!Number.isFinite(value) || value <= 0) return 1;
  return value;
}

function scaledMarkerRadius(baseRadius) {
  return Math.max(1, baseRadius * markerScale());
}

function scaledStrokeWeight(baseWeight) {
  return Math.max(1, baseWeight * Math.sqrt(markerScale()));
}

function updateMarkerScaleLabel() {
  const element = document.getElementById("marker-size-value");
  if (!element) return;
  element.textContent = `${markerScale().toFixed(1)}x`;
}

function average(values) {
  return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

for (const id of ["danger-only", "gps-valid-only", "confidence-filter", "view-mode", "imu-heat-toggle", "marker-size"]) {
  document.getElementById(id).addEventListener("input", render);
}

loadDemo().catch((error) => {
  document.getElementById("summary").textContent = error.message;
});
