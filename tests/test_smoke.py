import unittest

import barrier_free


class SmokeTest(unittest.TestCase):
    def test_package_has_version(self):
        self.assertRegex(barrier_free.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
