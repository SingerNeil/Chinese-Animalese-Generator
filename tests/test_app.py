from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_home_page_contains_primary_workspace(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("中文动森语音生成器".encode("utf-8"), response.data)
        self.assertIn("把中文变成".encode("utf-8"), response.data)
        self.assertIn("生成语音".encode("utf-8"), response.data)

    def test_generate_preview_and_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            generated_dir = Path(temp_dir)
            with patch.object(app_module, "GENERATED_DIR", generated_dir):
                response = self.client.post(
                    "/api/generate",
                    json={
                        "text": "欢迎来到桌宠小屋",
                        "backend": "equalo",
                        "voice": "med",
                        "dehiss": "remap",
                        "speed": 1.0,
                        "pitch": 0,
                        "variation": 1.0,
                        "pauseScale": 1.0,
                    },
                )
                self.assertEqual(response.status_code, 200)
                result = response.get_json()
                self.assertGreater(result["duration"], 0)
                self.assertGreater(result["sizeBytes"], 1000)
                preview = self.client.get(result["audioUrl"])
                try:
                    self.assertEqual(preview.status_code, 200)
                finally:
                    preview.close()
                download = self.client.get(result["downloadUrl"])
                try:
                    self.assertEqual(download.status_code, 200)
                    self.assertIn("attachment", download.headers["Content-Disposition"])
                finally:
                    download.close()

    def test_rejects_empty_text(self) -> None:
        response = self.client.post("/api/generate", json={"text": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
