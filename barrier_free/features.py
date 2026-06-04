"""IMU 창 분할과 특징 추출."""

from __future__ import annotations

import math
import statistics


def window_imu_rows(rows: list[dict], window_seconds: float = 1.0) -> list[list[dict]]:
    """timestamp 기준으로 겹치지 않는 고정 길이 창을 만든다."""

    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda row: row["timestamp"])
    start = sorted_rows[0]["timestamp"]
    windows: list[list[dict]] = []
    current: list[dict] = []
    current_index = 0

    for row in sorted_rows:
        index = int((row["timestamp"] - start) // window_seconds)
        while index > current_index:
            if current:
                windows.append(current)
            current = []
            current_index += 1
        current.append(row)

    if current:
        windows.append(current)
    return windows


def extract_window_features(rows: list[dict], speed_mps: float) -> dict:
    """한 IMU 창에서 모델 입력 특징을 계산한다."""

    if not rows:
        raise ValueError("rows must not be empty")

    accel_mags = [_magnitude(row["ax"], row["ay"], row["az"]) for row in rows]
    gyro_mags = [_magnitude(row["gx"], row["gy"], row["gz"]) for row in rows]
    jerk_values = _jerk_values(rows)

    return {
        "max_abs_ax": max(abs(row["ax"]) for row in rows),
        "max_abs_ay": max(abs(row["ay"]) for row in rows),
        "max_abs_az": max(abs(row["az"]) for row in rows),
        "accel_mag_max": max(accel_mags),
        "accel_mag_mean": statistics.fmean(accel_mags),
        "accel_mag_stdev": _pstdev(accel_mags),
        "jerk_max": max(jerk_values) if jerk_values else 0.0,
        "jerk_mean": statistics.fmean(jerk_values) if jerk_values else 0.0,
        "z_peak_count": sum(1 for row in rows if row["az"] - 1.0 >= 1.0),
        "gyro_mag_max": max(gyro_mags),
        "gyro_mag_stdev": _pstdev(gyro_mags),
        "speed_mps": speed_mps,
    }


def nearest_speed_for_window(window: list[dict], gps_rows: list[dict]) -> float:
    """창 중간 timestamp와 가장 가까운 GPS 속도를 반환한다."""

    if not gps_rows:
        return 0.0
    middle = (window[0]["timestamp"] + window[-1]["timestamp"]) / 2
    nearest = min(gps_rows, key=lambda row: abs(row["timestamp"] - middle))
    return float(nearest.get("speed_mps", 0.0))


def _jerk_values(rows: list[dict]) -> list[float]:
    values = []
    for prev, current in zip(rows, rows[1:]):
        dt = current["timestamp"] - prev["timestamp"]
        if dt <= 0:
            continue
        prev_mag = _magnitude(prev["ax"], prev["ay"], prev["az"])
        current_mag = _magnitude(current["ax"], current["ay"], current["az"])
        values.append(abs(current_mag - prev_mag) / dt)
    return values


def _magnitude(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def _pstdev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return statistics.pstdev(values)
