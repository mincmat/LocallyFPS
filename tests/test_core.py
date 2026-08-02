import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TESTS_DIR.parent

sys.path.insert(0, str(PROJECT_DIR))


class TestPaths(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        from core import paths
        paths.setup(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from platform import reset_platform
        reset_platform()

    def test_setup_linux(self):
        from core import paths
        self.assertEqual(paths.OS_NAME, "linux")
        self.assertEqual(paths.BIN_EXT, "")
        self.assertEqual(paths.DEFAULT_LANGUAGE, "en")
        self.assertTrue(paths.FFMPEG_BIN.name.startswith("ffmpeg"))
        self.assertTrue(paths.RIFE_BIN.name.startswith("rife-ncnn-vulkan"))

    def test_ensure_dirs(self):
        from core.paths import ensure_dirs
        ensure_dirs()
        from core import paths
        self.assertTrue(paths.MODELS_DIR.is_dir())
        self.assertTrue(paths.CACHE_DIR.is_dir())
        self.assertTrue(paths.CONFIG_DIR.is_dir())
        self.assertTrue((paths.VIDEOS_DIR / "original").is_dir())
        self.assertTrue((paths.VIDEOS_DIR / "enhanced").is_dir())


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        from core import paths
        paths.setup(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from platform import reset_platform
        reset_platform()

    def test_default_config(self):
        from core.config import CONFIG, DEFAULT_CONFIG
        self.assertIn("language", DEFAULT_CONFIG)
        self.assertIn("encoder", DEFAULT_CONFIG)
        self.assertIn("crf", DEFAULT_CONFIG)

    def test_save_and_load(self):
        from core import config
        from core import paths
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config.CONFIG["language"] = "es"
        config.save_config()
        config.CONFIG["language"] = "en"
        config.load_config()
        self.assertEqual(config.CONFIG["language"], "es")


class TestI18n(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        from core import paths
        paths.setup(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from platform import reset_platform
        reset_platform()

    def test_load_translations(self):
        from core.i18n import load_translations, TRANSLATIONS
        load_translations()
        self.assertIsInstance(TRANSLATIONS, dict)

    def test_translation_fallback(self):
        from core.i18n import _
        result = _("nonexistent_key_xyz")
        self.assertEqual(result, "nonexistent_key_xyz")

    def test_language_names(self):
        from core.i18n import get_language_name, LANGUAGE_NAMES
        self.assertEqual(get_language_name("en"), "English")
        self.assertEqual(get_language_name("es"), "Español")


class TestColors(unittest.TestCase):
    def test_color_classmethods(self):
        from core.colors import Color
        result = Color.bold("test")
        self.assertIn("test", result)
        result = Color.ok("test")
        self.assertIn("test", result)
        result = Color.warn("test")
        self.assertIn("test", result)
        result = Color.error("test")
        self.assertIn("test", result)


class TestUtils(unittest.TestCase):
    def test_format_duration(self):
        from core.utils import format_duration
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(30), "30s")
        self.assertEqual(format_duration(90), "1min 30s")
        self.assertEqual(format_duration(3661), "1h 1min")

    def test_format_fps(self):
        from core.utils import format_fps
        self.assertEqual(format_fps(30.0), "30")
        self.assertEqual(format_fps(29.97), "30.0")
        self.assertEqual(format_fps(59.94), "59.9")

    def test_human_size(self):
        from core.utils import human_size
        self.assertIn("B", human_size(100))
        self.assertIn("KB", human_size(2048))
        self.assertIn("MB", human_size(5 * 1024 * 1024))
        self.assertIn("GB", human_size(2 * 1024 * 1024 * 1024))

    def test_clean_path_input(self):
        from core.utils import clean_path_input
        self.assertEqual(clean_path_input("  hello  "), "hello")
        self.assertEqual(clean_path_input("'hello world'"), "hello world")
        self.assertEqual(clean_path_input('"hello world"'), "hello world")
        self.assertEqual(clean_path_input("hello\\ world"), "hello world")


class TestDisk(unittest.TestCase):
    def test_estimate_frame_storage(self):
        from core.disk import estimate_frame_storage
        result = estimate_frame_storage(1920, 1080, 1000)
        self.assertGreater(result, 0)
        self.assertIsInstance(result, int)


class TestUrls(unittest.TestCase):
    def test_urls_exist(self):
        from core.urls import RIFE_RELEASE_URLS, FFMPEG_RELEASE_URLS
        self.assertIn("linux", RIFE_RELEASE_URLS)
        self.assertIn("windows", RIFE_RELEASE_URLS)
        self.assertIn("macos", RIFE_RELEASE_URLS)
        self.assertIn("linux", FFMPEG_RELEASE_URLS)
        self.assertIn("windows", FFMPEG_RELEASE_URLS)
        self.assertIn("macos", FFMPEG_RELEASE_URLS)


class TestOutput(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        from core import paths
        paths.setup(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from platform import reset_platform
        reset_platform()

    def test_build_default_output_name(self):
        from core.output import build_default_output_name
        result = build_default_output_name(Path("video.mp4"), 60.0)
        self.assertEqual(result, "ENHANCED_60FPS_video.mp4")

    def test_resolve_output_path_empty(self):
        from core.output import resolve_output_path
        result = resolve_output_path("", Path("video.mp4"), 60.0)
        self.assertIn("ENHANCED_60FPS_video.mp4", str(result))


class TestGpu(unittest.TestCase):
    def test_classify_gpu(self):
        from core.gpu import classify_gpu
        self.assertEqual(classify_gpu("NVIDIA RTX 3060"), "discrete_high")
        self.assertEqual(classify_gpu("NVIDIA GTX 1060"), "discrete")
        self.assertEqual(classify_gpu("Intel UHD Graphics 630"), "integrated")
        self.assertEqual(classify_gpu("AMD Radeon RX 580"), "discrete_high")
        self.assertEqual(classify_gpu("Unknown Device"), "unknown")

    def test_estimate_duration(self):
        from core.gpu import estimate_duration
        result = estimate_duration(1000, 1920, 1080, "discrete")
        self.assertGreater(result, 0)


class TestPlatform(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        from core import paths
        paths.setup(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from platform import reset_platform
        reset_platform()

    def test_get_platform(self):
        from platform import get_platform
        plat = get_platform()
        self.assertIsNotNone(plat)
        self.assertIn(plat.os_name, ("linux", "macos", "windows"))

    def test_encoder_presets(self):
        from platform import get_platform
        plat = get_platform()
        presets = plat.get_encoder_presets()
        self.assertIn("libx264", presets)
        self.assertIn("codec", presets["libx264"])

    def test_hw_encoder_map(self):
        from platform import get_platform
        plat = get_platform()
        hw_map = plat.get_hw_encoder_map()
        self.assertIsInstance(hw_map, list)
        self.assertGreater(len(hw_map), 0)


class TestModels(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        from core import paths
        paths.setup(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from platform import reset_platform
        reset_platform()

    def test_list_available_rife_models_default(self):
        from core.models import list_available_rife_models
        result = list_available_rife_models()
        self.assertEqual(result, ["rife-v4.6"])

    def test_list_available_rife_models_with_dir(self):
        from core import paths
        (paths.MODELS_DIR / "rife-v4.6").mkdir(parents=True, exist_ok=True)
        (paths.MODELS_DIR / "rife-v4.15").mkdir(parents=True, exist_ok=True)
        from core.models import list_available_rife_models
        result = list_available_rife_models()
        self.assertIn("rife-v4.6", result)
        self.assertIn("rife-v4.15", result)


if __name__ == "__main__":
    unittest.main()
