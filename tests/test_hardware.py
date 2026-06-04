import tempfile
import unittest
from pathlib import Path

from barrier_free.hardware import camera_usb, gps_neo_m8n, imu_mpu6050


class HardwareAdapterTest(unittest.TestCase):
    def test_mpu6050_reader_converts_raw_registers(self):
        bus = FakeI2CBus(
            {
                imu_mpu6050.ACCEL_XOUT_H: [0x40, 0x00, 0x00, 0x00, 0x40, 0x00],
                imu_mpu6050.GYRO_XOUT_H: [0x00, 0x00, 0x00, 0x00, 0x00, 0x83],
            }
        )
        reader = imu_mpu6050.MPU6050Reader(bus=bus)

        sample = reader.read_sample(timestamp=123.4)

        self.assertAlmostEqual(sample["timestamp"], 123.4)
        self.assertAlmostEqual(sample["ax"], 1.0)
        self.assertAlmostEqual(sample["ay"], 0.0)
        self.assertAlmostEqual(sample["az"], 1.0)
        self.assertAlmostEqual(sample["gz"], 1.0, places=2)
        self.assertIn((imu_mpu6050.MPU6050_ADDR, imu_mpu6050.PWR_MGMT_1, 0), bus.writes)

    def test_neo_m8n_rmc_sentence_parses_position_and_speed(self):
        sentence = "$GNRMC,092751.000,A,3723.2475,N,12158.3416,W,10.0,0.0,120626,,,A*00"

        sample = gps_neo_m8n.parse_nmea_sentence(sentence, timestamp=10.5)

        self.assertEqual(sample["gps_valid"], 1)
        self.assertAlmostEqual(sample["lat"], 37.387458333333335)
        self.assertAlmostEqual(sample["lon"], -121.97236)
        self.assertAlmostEqual(sample["speed_mps"], 5.14444, places=4)

    def test_usb_camera_uses_fswebcam_command(self):
        calls = []

        def fake_runner(cmd, check, capture_output, text):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"fake jpeg")
            return object()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.jpg"
            camera = camera_usb.USBCamera(device="/dev/video2", runner=fake_runner)

            result = camera.capture(path)

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            self.assertEqual(calls[0][0], "fswebcam")
            self.assertIn("/dev/video2", calls[0])


class FakeI2CBus:
    def __init__(self, blocks):
        self.blocks = blocks
        self.writes = []

    def write_byte_data(self, address, register, value):
        self.writes.append((address, register, value))

    def read_i2c_block_data(self, address, register, length):
        return self.blocks[register][:length]


if __name__ == "__main__":
    unittest.main()
