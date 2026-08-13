import os
import unittest
from unittest.mock import patch


class AppTest(unittest.TestCase):
    @patch.dict(os.environ, {"MONGO_URI": "mongodb://localhost:27017"})
    def test_wsgi_import_does_not_start_flask_development_server(self):
        with patch("flask.Flask.run") as run:
            import main

            run.assert_not_called()
            response = main.app.test_client().get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "device": "dexcom-g7"})


if __name__ == "__main__":
    unittest.main()
