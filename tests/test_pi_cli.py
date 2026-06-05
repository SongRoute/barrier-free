import io
import unittest
from contextlib import redirect_stdout

from barrier_free import cli


class PiCliTest(unittest.TestCase):
    def test_cli_help_lists_pi_commands(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stdout(output):
                cli.main(["--help"])

        text = output.getvalue()
        self.assertIn("check-imu", text)
        self.assertIn("check-gps", text)
        self.assertIn("check-camera", text)
        self.assertIn("collect", text)
        self.assertIn("compare-sessions", text)
        self.assertIn("audit-session", text)
        self.assertIn("preview-session", text)
        self.assertIn("preview-sessions", text)
        self.assertIn("serve-session", text)
        self.assertIn("serve-sessions", text)

    def test_collect_help_lists_no_camera_option(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stdout(output):
                cli.main(["collect", "--help"])

        self.assertIn("--no-camera", output.getvalue())


if __name__ == "__main__":
    unittest.main()
