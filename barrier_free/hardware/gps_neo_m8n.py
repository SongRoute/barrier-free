"""NEO-M8N GPS adapter using NMEA sentences."""

from __future__ import annotations

import time


KNOT_TO_MPS = 0.514444


class NEOM8NReader:
    """UART/USB serial NEO-M8N reader."""

    def __init__(self, port: str = "/dev/serial0", baudrate: int = 9600, serial_obj=None):
        self.serial = serial_obj if serial_obj is not None else _open_serial(port, baudrate)

    def read_sample(self, timeout_lines: int = 20) -> dict:
        for _ in range(timeout_lines):
            raw = self.serial.readline()
            if isinstance(raw, bytes):
                raw = raw.decode("ascii", errors="ignore")
            sample = parse_nmea_sentence(raw.strip(), timestamp=time.time())
            if sample is not None:
                return sample
        return {"timestamp": time.time(), "lat": 0.0, "lon": 0.0, "gps_valid": 0, "speed_mps": 0.0}

    def health_check(self) -> dict:
        sample = self.read_sample()
        return {"ok": bool(sample["gps_valid"]), "sensor": "NEO-M8N", "sample": sample}


def parse_nmea_sentence(sentence: str, timestamp: float | None = None) -> dict | None:
    """RMC 문장을 GPS sample로 변환한다."""

    if not sentence.startswith(("$GPRMC", "$GNRMC")):
        return None
    fields = sentence.split(",")
    if len(fields) < 8:
        return None
    valid = fields[2] == "A"
    lat = _parse_lat_lon(fields[3], fields[4]) if valid else 0.0
    lon = _parse_lat_lon(fields[5], fields[6]) if valid else 0.0
    speed_knots = _float_or_zero(fields[7]) if valid else 0.0
    return {
        "timestamp": time.time() if timestamp is None else timestamp,
        "lat": lat,
        "lon": lon,
        "gps_valid": 1 if valid else 0,
        "speed_mps": speed_knots * KNOT_TO_MPS,
    }


def _open_serial(port: str, baudrate: int):
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError(
            "NEO-M8N requires pyserial on Raspberry Pi. Install pyserial and enable UART."
        ) from exc
    return serial.Serial(port, baudrate=baudrate, timeout=1)


def _parse_lat_lon(value: str, hemisphere: str) -> float:
    if not value:
        return 0.0
    degree_digits = 2 if hemisphere in {"N", "S"} else 3
    degrees = float(value[:degree_digits])
    minutes = float(value[degree_digits:])
    result = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        result *= -1
    return result


def _float_or_zero(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0
