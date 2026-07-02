from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PYTHON_ROOT = os.path.join(REPO_ROOT, "python")
if PYTHON_ROOT not in sys.path:
    sys.path.insert(0, PYTHON_ROOT)

REGISTRY_FILE = os.path.join(REPO_ROOT, "src", "features", "registry.ts")
PAGES_FILE = os.path.join(REPO_ROOT, "src", "features", "pages.tsx")
API_FILE = os.path.join(REPO_ROOT, "src", "services", "api.ts")
SIDEBAR_FILE = os.path.join(REPO_ROOT, "src", "components", "sidebar", "Sidebar.tsx")
CREATIVE_PAGE = os.path.join(REPO_ROOT, "src", "components", "creative", "CreativeMediaPage.tsx")
BRIDGE_FILE = os.path.join(REPO_ROOT, "python", "bridge.py")


class CreativeMediaUiContractTests(unittest.TestCase):
    def test_creative_page_is_first_class_nav_entry_and_phone_is_hidden(self) -> None:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as handle:
            registry = handle.read()
        with open(PAGES_FILE, "r", encoding="utf-8") as handle:
            pages = handle.read()
        with open(SIDEBAR_FILE, "r", encoding="utf-8") as handle:
            sidebar = handle.read()

        self.assertRegex(registry, r"key:\s*'creative'[\s\S]+?requiresLicense:\s*true")
        self.assertRegex(registry, r"key:\s*'phone'[\s\S]+?visible:\s*HIDDEN")
        self.assertIn("CreativeMediaPage", pages)
        self.assertIn("creative: CreativeMediaPage", pages)
        self.assertIn("'creative'", sidebar)

    def test_creative_page_exposes_image_video_config_and_running_feedback(self) -> None:
        with open(CREATIVE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        for marker in (
            "data-creative-media-page",
            "data-creative-tab-image",
            "data-creative-tab-video",
            "mediaApi.config",
            "mediaApi.saveConfig",
            "mediaApi.testConfig",
            "imageApi.submit",
            "videoApi.submit",
            "jobApi.get",
            "activeJob",
            "generationPulse",
            "生成中",
            "自定义 API",
        ):
            self.assertIn(marker, source)

        self.assertIn("type=\"password\"", source)
        self.assertNotIn("console.log(customApiKey", source)
        self.assertNotIn("console.log(videoApiKey", source)

    def test_creative_page_keeps_image_and_video_jobs_independent(self) -> None:
        with open(CREATIVE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("activeJobs", source)
        self.assertIn("imageRunning", source)
        self.assertIn("videoRunning", source)
        self.assertIn("pollRefs", source)
        self.assertIn("rememberedCreativeJobs", source)
        self.assertNotIn("const generationRunning = Boolean(activeJob", source)
        self.assertIn("disabled={imageRunning}", source)
        self.assertIn("disabled={videoRunning}", source)

    def test_creative_page_does_not_hardcode_unavailable_default_models(self) -> None:
        with open(CREATIVE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("React.useState('')", source)
        self.assertIn("留空使用当前默认模型", source)
        self.assertIn("留空使用 provider 默认模型", source)
        self.assertNotIn("React.useState('gpt-image-2')", source)
        self.assertNotIn("React.useState('wanx2.1-t2v-turbo')", source)

    def test_creative_api_key_config_is_compact_collapsible(self) -> None:
        with open(CREATIVE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-creative-config-details", source)
        self.assertIn("<summary", source)
        self.assertIn("xl:grid-cols-[minmax(0,1fr)_340px]", source)
        self.assertLess(source.count("<Input type=\"password\""), 3)

    def test_api_client_has_media_config_contract(self) -> None:
        with open(API_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("export interface MediaConfigSnapshot", source)
        self.assertIn("export const mediaApi", source)
        self.assertIn("api('/api/media/config')", source)
        self.assertIn("api('/api/media/config', 'POST'", source)
        self.assertIn("api('/api/media/test', 'POST'", source)


class CreativeMediaBackendContractTests(unittest.TestCase):
    def test_media_config_is_sanitized_and_generation_uses_saved_fallback(self) -> None:
        routes_media = importlib.import_module("api.routes_media")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_config = os.path.join(temp_dir, "imgapi_config.json")
            video_config = os.path.join(temp_dir, "video_config.json")
            paths = SimpleNamespace(
                image_config=image_config,
                video_config=video_config,
                data_dir=temp_dir,
            )
            ctx = SimpleNamespace(paths=paths)

            snapshot = routes_media._save_media_config(ctx, {
                "image": {
                    "baseUrl": "https://example.com/v1",
                    "apiKey": "TEST_IMAGE_SECRET",
                    "model": "gpt-image-1",
                },
                "video": {
                    "providerId": "custom",
                    "apiBase": "https://video.example.com",
                    "apiKey": "TEST_VIDEO_SECRET",
                    "model": "video-model",
                },
            })

            self.assertTrue(snapshot["image"]["hasApiKey"])
            self.assertTrue(snapshot["video"]["hasApiKey"])
            public_snapshot = json.dumps(snapshot)
            self.assertNotIn("TEST_IMAGE_SECRET", public_snapshot)
            self.assertNotIn("TEST_VIDEO_SECRET", public_snapshot)

            with open(image_config, "r", encoding="utf-8") as handle:
                saved_image = json.load(handle)
            with open(video_config, "r", encoding="utf-8") as handle:
                saved_video = json.load(handle)
            self.assertEqual(saved_image["apiKey"], "TEST_IMAGE_SECRET")
            self.assertEqual(saved_video["apiKey"], "TEST_VIDEO_SECRET")

            self.assertEqual(
                routes_media._image_config_fallback(ctx)["apiKey"],
                "TEST_IMAGE_SECRET",
            )
            self.assertEqual(
                routes_media._video_config_fallback(ctx)["apiKey"],
                "TEST_VIDEO_SECRET",
            )

    def test_bridge_does_not_clear_video_config_on_startup(self) -> None:
        with open(BRIDGE_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertNotIn("_reset_transient_video_config()", source)
        self.assertNotIn("write_json(paths.video_config, {})", source)

    def test_image_client_accepts_base_url_with_or_without_v1(self) -> None:
        image_api = importlib.import_module("services.image_api")

        self.assertEqual(
            image_api._openai_endpoint("https://api.heang.top", "/v1/images/generations"),
            "https://api.heang.top/v1/images/generations",
        )
        self.assertEqual(
            image_api._openai_endpoint("https://api.heang.top/v1", "/v1/images/generations"),
            "https://api.heang.top/v1/images/generations",
        )


if __name__ == "__main__":
    unittest.main()
