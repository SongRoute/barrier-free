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


if __name__ == "__main__":
    unittest.main()
