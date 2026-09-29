import unittest

from settings import Controls


class Service:
    def __init__(self):
        self.saved = 10
        self.saves = 0

    def save(self, value):
        self.saves += 1
        self.saved = value

    def refresh(self):
        raise RuntimeError("status unavailable")


class SettingsTests(unittest.TestCase):
    def test_status_failure(self):
        controls = Controls()
        controls.apply(20, Service())
        self.assertIn("status unavailable", controls.message)
