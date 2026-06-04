"""MPU6050 IMU adapter.

Raspberry Pi에서는 `python3-smbus` 또는 `smbus2`가 필요하다.
테스트에서는 bus 객체를 주입해 하드웨어 없이 변환 로직을 검증한다.
"""

from __future__ import annotations

import time


MPU6050_ADDR = 0x68
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H = 0x43

ACCEL_SCALE = 16384.0
GYRO_SCALE = 131.0


class MPU6050Reader:
    """MPU6050에서 가속도 g 단위와 gyro deg/s를 읽는다."""

    def __init__(self, bus=None, address: int = MPU6050_ADDR, bus_number: int = 1):
        self.address = address
        self.bus = bus if bus is not None else _open_i2c_bus(bus_number)
        self.bus.write_byte_data(self.address, PWR_MGMT_1, 0)

    def read_sample(self, timestamp: float | None = None) -> dict:
        ts = time.time() if timestamp is None else timestamp
        accel = self.bus.read_i2c_block_data(self.address, ACCEL_XOUT_H, 6)
        gyro = self.bus.read_i2c_block_data(self.address, GYRO_XOUT_H, 6)
        ax_raw, ay_raw, az_raw = _three_int16(accel)
        gx_raw, gy_raw, gz_raw = _three_int16(gyro)
        return {
            "timestamp": ts,
            "ax": ax_raw / ACCEL_SCALE,
            "ay": ay_raw / ACCEL_SCALE,
            "az": az_raw / ACCEL_SCALE,
            "gx": gx_raw / GYRO_SCALE,
            "gy": gy_raw / GYRO_SCALE,
            "gz": gz_raw / GYRO_SCALE,
        }

    def health_check(self) -> dict:
        sample = self.read_sample()
        return {"ok": True, "sensor": "MPU6050", "sample": sample}


def _open_i2c_bus(bus_number: int):
    try:
        from smbus2 import SMBus
    except ImportError:
        try:
            from smbus import SMBus
        except ImportError as exc:
            raise RuntimeError(
                "MPU6050 requires smbus2 or python3-smbus on Raspberry Pi. "
                "Install one and enable I2C with raspi-config."
            ) from exc
    return SMBus(bus_number)


def _three_int16(block: list[int]) -> tuple[int, int, int]:
    return (_to_int16(block[0], block[1]), _to_int16(block[2], block[3]), _to_int16(block[4], block[5]))


def _to_int16(high: int, low: int) -> int:
    value = (high << 8) | low
    if value >= 0x8000:
        value -= 0x10000
    return value
