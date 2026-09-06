import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from core import paths
from core.deps import safe_extract_tar, safe_extract_zip
from core.extract import _get_pix_fmt_filter, extract_frames
from core.interpolate import (
    _build_ffmpeg_fallback_command,
    _interpolated_frame_is_plausible,
)
from core.probe import probe_video_file
from core.reassemble import _build_encode_command, _encoder_args, _validate_output
from core.update_utils import parse_version
from core.updater import UpdateCheckError, check_for_updates


class EncoderTests(unittest.TestCase):
    def test_encoder_specific_rate_control(self):
        self.assertIn("-cq", _encoder_args("h264_nvenc", 18, "fast"))
        self.assertIn("-qp", _encoder_args("h264_vaapi", 18, "fast"))
        self.assertIn("-global_quality", _encoder_args("h264_qsv", 18, "fast"))
        self.assertIn("-q:v", _encoder_args("h264_videotoolbox", 18, "fast"))
        self.assertEqual(_encoder_args("libx264", 18, "fast"), ["-crf", "18", "-preset", "fast"])

    def test_command_preserves_auxiliary_streams(self):
        enc = {"codec": "libx264", "pix_fmt": "yuv420p", "hwaccel": None}
        info = {"subtitle_streams": [{"index": 3, "codec": "subrip"}]}
        cmd = _build_encode_command(
            enc, Path("frames"), Path("input.mkv"), 60, Path("output.mp4"),
            True, 2.0, 18, "fast", info,
        )
        joined = " ".join(cmd)
        self.assertIn("-map 1:a?", joined)
        self.assertIn("-map 1:3?", joined)
        self.assertIn("-map_metadata 1", joined)
        self.assertIn("-map_chapters 1", joined)

    def test_short_release_version_is_semver_compatible(self):
        self.assertEqual(parse_version("v3.1"), (3, 1, 0))
        self.assertEqual(parse_version("3.1.2"), (3, 1, 2))


class UpdateCheckTests(unittest.TestCase):
    @mock.patch("core.updater.urllib.request.urlopen", side_effect=OSError("offline"))
    def test_network_failure_is_not_reported_as_latest_version(self, _urlopen):
        with self.assertRaises(UpdateCheckError):
            check_for_updates()

    @mock.patch("core.updater.get_platform_base_name", return_value="LocallyFPS_Linux")
    @mock.patch("core.updater.CURRENT_VERSION", "3.1")
    @mock.patch("core.updater.urllib.request.urlopen")
    def test_short_current_version_detects_new_release(self, urlopen, _base_name):
        payload = {
            "tag_name": "v3.2.0",
            "assets": [{
                "name": "LocallyFPS_Linux_v3.2.zip",
                "browser_download_url": "https://example.invalid/LocallyFPS_Linux_v3.2.zip",
            }],
        }
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        urlopen.return_value = response

        result = check_for_updates()

        self.assertEqual(result[0], "v3.2.0")
        self.assertEqual(result[2], "LocallyFPS_Linux_v3.2.zip")


class InterpolationValidationTests(unittest.TestCase):
    def test_optical_flow_fallback_is_motion_compensated(self):
        cmd = _build_ffmpeg_fallback_command(
            Path("input"), Path("output"), 30.0, 60.0, 120
        )
        joined = " ".join(cmd)
        self.assertIn("minterpolate=fps=60", joined)
        self.assertIn("mi_mode=mci", joined)
        self.assertIn("me_mode=bilat", joined)
        self.assertIn("tpad=stop_mode=clone", joined)
        self.assertIn("-frames:v 120", joined)
        self.assertIn(str(Path("input") / "%08d.png"), cmd)
        self.assertIn(str(Path("output") / "%08d.png"), cmd)

    def test_valid_interpolation_is_accepted(self):
        first = bytes([10, 20, 30]) * 100
        second = bytes([20, 30, 40]) * 100
        middle = bytes([15, 25, 35]) * 100
        self.assertTrue(_interpolated_frame_is_plausible(first, second, middle))

    def test_corrupt_interpolation_is_rejected(self):
        first = bytes([20, 30, 40]) * 100
        second = bytes([25, 35, 45]) * 100
        corrupt = bytes([0, 255, 0]) * 100
        self.assertFalse(_interpolated_frame_is_plausible(first, second, corrupt))

    def test_duplicate_frame_is_rejected(self):
        first = bytes([10, 20, 30]) * 100
        second = bytes([30, 40, 50]) * 100
        self.assertFalse(_interpolated_frame_is_plausible(first, second, first))


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe not installed")
        paths.FFMPEG_BIN = Path(ffmpeg)
        paths.FFPROBE_BIN = Path(ffprobe)

    def test_hdr_filter_has_separate_tonemap_stage(self):
        value = _get_pix_fmt_filter({"color_transfer": "smpte2084"})
        self.assertIn(",tonemap=tonemap=hable", value)
        self.assertNotIn("zscale=p=bt709:tonemap", value)

    def test_hevc_10bit_hdr_extraction(self):
        encoders = subprocess.run(
            [str(paths.FFMPEG_BIN), "-encoders"], capture_output=True, text=True
        ).stdout
        filters = subprocess.run(
            [str(paths.FFMPEG_BIN), "-filters"], capture_output=True, text=True
        ).stdout
        if "libx265" not in encoders or "zscale" not in filters or "tonemap" not in filters:
            self.skipTest("FFmpeg lacks libx265/zscale/tonemap")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "hevc10.mkv"
            frames = root / "frames"
            frames.mkdir()
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=96x64:rate=24:duration=0.25", "-pix_fmt", "yuv420p10le",
                "-color_primaries", "bt2020", "-color_trc", "smpte2084",
                "-colorspace", "bt2020nc", "-c:v", "libx265", "-x265-params",
                "log-level=error", str(source),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            info = probe_video_file(source)
            self.assertEqual(info["codec"], "hevc")
            self.assertEqual(info["pix_fmt"], "yuv420p10le")
            count = extract_frames(source, frames, info, progress_cb=lambda _: None)
            self.assertGreater(count, 0)

    def test_lossless_png_extraction_and_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            frames = root / "frames"
            frames.mkdir()
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-f", "lavfi",
                "-i", "testsrc=size=64x64:rate=24:duration=0.25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
            ], check=True)
            info = probe_video_file(source)
            self.assertIsNotNone(info)
            count = extract_frames(source, frames, info, progress_cb=lambda _: None)
            self.assertGreater(count, 0)
            self.assertEqual(count, len(list(frames.glob("*.png"))))
            self.assertTrue(_validate_output(source))

    def test_reassembly_command_keeps_all_audio_tracks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.mkv"
            frames = root / "frames"
            output = root / "output.mkv"
            frames.mkdir()
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-f", "lavfi",
                "-i", "color=c=blue:size=64x64:rate=2:duration=1", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1", "-f", "lavfi",
                "-i", "sine=frequency=880:duration=1", "-map", "0:v", "-map", "1:a",
                "-map", "2:a", "-c:v", "libx264", "-c:a", "aac", str(original),
            ], check=True)
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-i", str(original),
                str(frames / "%08d.png"),
            ], check=True)
            enc = {"codec": "libx264", "pix_fmt": "yuv420p", "hwaccel": None}
            cmd = _build_encode_command(
                enc, frames, original, 2, output, True, 1.0, 18, "fast",
                {"subtitle_streams": []},
            )
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            result = subprocess.run([
                str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(output),
            ], capture_output=True, text=True, check=True)
            self.assertEqual(len(result.stdout.strip().splitlines()), 2)


class ProbeTests(unittest.TestCase):
    @mock.patch("core.probe.subprocess.run")
    def test_avg_frame_rate_is_preferred_and_probe_runs_once(self, run):
        payload = {
            "streams": [{
                "codec_type": "video", "codec_name": "h264", "width": 10,
                "height": 10, "avg_frame_rate": "24000/1001",
                "r_frame_rate": "60/1", "nb_frames": "24",
            }],
            "format": {"duration": "1", "size": "100"},
        }
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.touch()
            info = probe_video_file(video)
        self.assertAlmostEqual(info["fps"], 24000 / 1001)
        self.assertEqual(run.call_count, 1)


class ArchiveSafetyTests(unittest.TestCase):
    def test_zip_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.txt", "nope")
            with zipfile.ZipFile(archive) as zf:
                with self.assertRaises(ValueError):
                    safe_extract_zip(zf, Path(temp) / "out")

    def test_tar_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.tar"
            with tarfile.open(archive, "w") as tf:
                item = tarfile.TarInfo("link")
                item.type = tarfile.SYMTYPE
                item.linkname = "/tmp/target"
                tf.addfile(item, io.BytesIO())
            with tarfile.open(archive) as tf:
                with self.assertRaises(ValueError):
                    safe_extract_tar(tf, Path(temp) / "out")


if __name__ == "__main__":
    unittest.main()
