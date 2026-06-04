"""실제 주행 전 개발을 위한 deterministic mock 세션 생성."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from . import schema


START_LAT = 36.628
START_LON = 127.456
SAMPLE_RATE_HZ = 20
SESSION_SECONDS = 24


def build_demo_dataset(seed: int = 42) -> dict:
    """before/after mock 세션 쌍을 생성한다."""

    before_events = [
        {"t": 2.0, "risk": 0.12, "kind": "normal"},
        {"t": 4.0, "risk": 0.82, "kind": "danger"},
        {"t": 5.0, "risk": 0.76, "kind": "danger"},
        {"t": 8.0, "risk": 0.91, "kind": "exclude"},
        {"t": 11.0, "risk": 0.58, "kind": "caution"},
        {"t": 15.0, "risk": 0.10, "kind": "normal"},
        {"t": 17.0, "risk": 0.68, "kind": "caution"},
        {"t": 18.0, "risk": 0.88, "kind": "danger"},
    ]
    after_events = [
        {"t": 4.0, "risk": 0.40, "kind": "caution"},
        {"t": 11.0, "risk": 0.30, "kind": "normal"},
    ]

    return {
        "before": _build_session(
            seed=seed,
            session_id="demo_before_run01",
            phase="before",
            run_index=1,
            route_offset=0.0,
            event_specs=before_events,
        ),
        "after": _build_session(
            seed=seed + 1000,
            session_id="demo_after_run01",
            phase="after",
            run_index=1,
            route_offset=0.0,
            event_specs=after_events,
        ),
    }


def _build_session(
    *,
    seed: int,
    session_id: str,
    phase: str,
    run_index: int,
    route_offset: float,
    event_specs: list[dict],
) -> dict:
    rng = random.Random(seed)
    start_ts = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc).timestamp()
    raw_imu = []
    gps = []

    event_by_second = {int(spec["t"]): spec for spec in event_specs}
    total_samples = SESSION_SECONDS * SAMPLE_RATE_HZ

    for sample_index in range(total_samples):
        timestamp = round(start_ts + sample_index / SAMPLE_RATE_HZ, 3)
        t = sample_index / SAMPLE_RATE_HZ
        second = int(t)
        route_progress = t / SESSION_SECONDS
        lat = START_LAT + route_progress * 0.0012
        lon = START_LON + route_offset + math.sin(route_progress * math.pi) * 0.00025

        risk = event_by_second.get(second, {}).get("risk", 0.12)
        pulse = _pulse(t, second + 0.45) if second in event_by_second else 0.0
        base_noise = rng.uniform(-0.04, 0.04)
        shock = risk * pulse

        raw_imu.append(
            {
                "timestamp": timestamp,
                "ax": round(base_noise + shock * rng.uniform(1.8, 2.4), 4),
                "ay": round(rng.uniform(-0.06, 0.06) + shock * rng.uniform(0.5, 1.0), 4),
                "az": round(1.0 + rng.uniform(-0.05, 0.05) + shock * rng.uniform(2.0, 3.4), 4),
                "gx": round(rng.uniform(-0.03, 0.03) + shock * 0.30, 4),
                "gy": round(rng.uniform(-0.03, 0.03) + shock * 0.20, 4),
                "gz": round(rng.uniform(-0.03, 0.03) + shock * 0.25, 4),
            }
        )

        if sample_index % SAMPLE_RATE_HZ == 0:
            gps_valid = 0 if second in {9, 20} else 1
            gps.append(
                {
                    "timestamp": timestamp,
                    "lat": round(lat, 7),
                    "lon": round(lon, 7),
                    "gps_valid": gps_valid,
                    "speed_mps": round(rng.uniform(2.3, 3.2), 3),
                }
            )

    events = []
    labels = []
    event_index = 0
    for label_index, spec in enumerate(event_specs, start=1):
        gps_row = min(gps, key=lambda row: abs(row["timestamp"] - (start_ts + spec["t"])))
        event_id = ""
        if spec["kind"] not in {"normal", "exclude"}:
            event_index += 1
            event_id = f"{session_id}_event_{event_index:02d}"
            events.append(
                {
                    "event_id": event_id,
                    "timestamp_start": round(start_ts + spec["t"], 3),
                    "timestamp_end": round(start_ts + spec["t"] + 1.0, 3),
                    "lat": gps_row["lat"],
                    "lon": gps_row["lon"],
                    "gps_valid": gps_row["gps_valid"],
                    "speed_mps": gps_row["speed_mps"],
                    "prediction": spec["kind"],
                    "confidence": round(min(0.99, 0.45 + spec["risk"] * 0.55), 3),
                    "risk_score": round(spec["risk"], 3),
                    "segment_id": "",
                    "photo_before": f"photos/{event_id}_before.jpg",
                    "photo_after": f"photos/{event_id}_after.jpg",
                    "model_version": "mock-model-v1",
                }
            )
        labels.append(
            {
                "label_id": f"{session_id}_label_{label_index:02d}",
                "event_id": event_id,
                "timestamp_start": round(start_ts + spec["t"], 3),
                "timestamp_end": round(start_ts + spec["t"] + 1.0, 3),
                "lat": gps_row["lat"],
                "lon": gps_row["lon"],
                "label": spec["kind"],
                "step_height_mm": round(spec["risk"] * 18, 1),
                "crack_width_mm": round(spec["risk"] * 35, 1),
                "pothole_depth_mm": round(spec["risk"] * 22, 1),
                "non_road_shock": 1 if spec["kind"] == "exclude" else 0,
                "notes": "mock label generated from deterministic risk score",
            }
        )

    bundle = {
        "session": {
            "session_id": session_id,
            "phase": phase,
            "run_index": run_index,
            "started_at": "2026-06-12T10:00:00Z",
            "route_name": "campus_demo_route",
            "device": "mock Raspberry Pi 3B + IMU + GPS + webcam",
            "model_version": "mock-model-v1",
            "label_policy_version": "mock_policy_v1",
            "notes": "deterministic mock session for development",
        },
        "raw_imu": raw_imu,
        "gps": gps,
        "events": events,
        "labels": labels,
    }
    schema.validate_session_bundle(bundle)
    return bundle


def _pulse(t: float, center: float) -> float:
    distance = abs(t - center)
    if distance > 0.20:
        return 0.0
    return 1.0 - distance / 0.20
