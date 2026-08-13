import os
import unittest
from unittest.mock import Mock, patch

from dexcom_g7 import DexcomG7Client


class DexcomG7ClientTest(unittest.TestCase):
    @patch("dexcom_g7.Dexcom")
    def test_uses_international_share_server_for_italy(self, dexcom):
        DexcomG7Client("utente", "segreto", "OUS")
        dexcom.assert_called_once_with("utente", "segreto", ous=True)

    @patch("dexcom_g7.Dexcom")
    def test_normalizes_a_g7_reading(self, dexcom):
        raw = Mock(value=123, trend_description="steady", trend_arrow="→")
        raw.time = Mock()
        dexcom.return_value.get_current_glucose_reading.return_value = raw

        reading = DexcomG7Client("utente", "segreto", "US").get_current_reading()

        self.assertEqual(reading.value, 123.0)
        self.assertEqual(reading.trend_arrow, "→")
        dexcom.assert_called_once_with("utente", "segreto", ous=False)

    def test_rejects_unknown_region(self):
        with self.assertRaisesRegex(ValueError, "US oppure OUS"):
            DexcomG7Client("utente", "segreto", "EU")

    @patch.dict(os.environ, {}, clear=True)
    def test_requires_account_credentials(self):
        with self.assertRaisesRegex(ValueError, "obbligatori"):
            DexcomG7Client.from_environment()


if __name__ == "__main__":
    unittest.main()
