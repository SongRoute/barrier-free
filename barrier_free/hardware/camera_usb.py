"""USB webcam adapter.

기본 구현은 Raspberry Pi에서 흔히 쓰는 `fswebcam` 명령을 호출한다.
OpenCV 의존성을 강제하지 않기 위한 선택이다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class USBCamera:
    """USB webcam still-image capture wrapper."""

    def __init__(self, device: str = "/dev/video0", resolution: str = "1280x720", runner=None):
        self.device = device
        self.resolution = resolution
        self.runner = runner if runner is not None else subprocess.run

    def capture(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "fswebcam",
            "-d",
            self.device,
            "-r",
            self.resolution,
            "--no-banner",
            str(path),
        ]
        self.runner(cmd, check=True, capture_output=True, text=True)
        return path

    def health_check(self, output_dir: Path) -> dict:
        path = self.capture(output_dir / "camera_check.jpg")
        return {"ok": path.exists(), "sensor": "USB webcam", "path": str(path)}
