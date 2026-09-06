import io
import json
import math
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from core import manifest, paths
from core import _configure_stdio
from core.config import _validated_config
from core.deps import safe_extract_tar, safe_extract_zip
from core.disk import estimate_frame_storage, estimate_pipeline_storage
from core.extract import _get_extraction_filter, _get_pix_fmt_filter, extract_frames
from core.interpolate import (
    _build_ffmpeg_fallback_command,
    _detect_scene_cuts,
    _gpu_requires_safe_fallback,
    _interpolated_frame_is_plausible,
    _repair_scene_cut_frames,
    _validate_generated_sequence,
    _validation_pair_indexes,
    run_interpolation,
)
from core.jobs import PipelineJob
from core.pipeline import run_pipeline
from core.progress import ProgressBar
from core.probe import probe_video_file
from core.reassemble import (
    _build_encode_command,
    _compatible_output,
    _build_video_filter,
    _encoder_args,
    _output_color_info,
    _validate_output,
    reassemble_video,
)
from core.update_utils import create_swap_script, parse_version
from core.updater import UpdateCheckError, check_for_updates
from core.wizard import _valid_cli_target_fps, recommended_target_fps


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

    def test_hdr_output_metadata_matches_tonemapped_sdr(self):
        info = {
            "color_primaries": "bt2020", "color_space": "bt2020nc",
            "color_transfer": "smpte2084", "color_range": "tv",
            "subtitle_streams": [],
        }
        normalized = _output_color_info(info)
        self.assertEqual(normalized["color_primaries"], "bt709")
        self.assertEqual(normalized["color_space"], "bt709")
        self.assertEqual(normalized["color_transfer"], "bt709")
        self.assertEqual(info["color_transfer"], "smpte2084")

    def test_rgb_input_metadata_is_normalized_for_yuv_encoders(self):
        normalized = _output_color_info({
            "color_space": "gbr", "color_range": "pc",
            "color_primaries": None, "color_transfer": None,
        })
        self.assertEqual(normalized["color_space"], "bt709")
        self.assertEqual(normalized["color_transfer"], "bt709")
        self.assertEqual(normalized["color_range"], "tv")

    def test_incompatible_mp4_subtitles_force_lossless_mkv_container(self):
        info = {"subtitle_streams": [{"index": 2, "codec": "hdmv_pgs_subtitle"}]}
        result = _compatible_output("libx264", Path("output.mp4"), info)
        self.assertEqual(result, Path("output.mkv"))

    def test_attachments_force_mkv_and_are_mapped(self):
        info = {"subtitle_streams": [], "attachment_tracks": 1}
        self.assertEqual(
            _compatible_output("libx264", Path("output.mp4"), info),
            Path("output.mkv"),
        )
        cmd = _build_encode_command(
            {"codec": "libx264", "pix_fmt": "yuv420p", "hwaccel": None},
            Path("frames"), Path("input.mkv"), 60, Path("output.mkv"),
            False, 1.0, 18, "fast", info,
        )
        self.assertIn("-map 1:t? -c:t copy", " ".join(cmd))

    def test_encoder_filter_handles_odd_dimensions_and_preserves_sar(self):
        value = _build_video_filter("libx264", {
            "sample_aspect_ratio": "16:15", "color_space": "bt709",
            "color_primaries": "bt709", "color_transfer": "bt709",
            "color_range": "tv",
        })
        self.assertIn("pad=ceil(iw/2)*2:ceil(ih/2)*2", value)
        self.assertIn("setsar=ratio=16/15", value)
        self.assertIn("setparams=color_primaries=bt709", value)
        self.assertIn("range=limited", value)
        vaapi = _build_video_filter("h264_vaapi", {})
        self.assertTrue(vaapi.endswith("format=nv12,hwupload"))

    @mock.patch("core.reassemble._run_ffmpeg", return_value=(1, "encoder failed", None))
    @mock.patch("core.reassemble._detect_available_encoders", return_value=["libx264"])
    @mock.patch(
        "core.reassemble._pick_best_encoder",
        return_value={"codec": "libx264", "pix_fmt": "yuv420p", "hwaccel": None},
    )
    def test_failed_export_does_not_destroy_existing_output(self, _pick, _detect, _run):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output.mp4"
            output.write_bytes(b"existing video")
            result = reassemble_video(
                root, root / "input.mp4", 60, False, output, 60,
                info={"audio_tracks": 0, "subtitle_streams": []},
            )
            self.assertIsNone(result)
            self.assertEqual(output.read_bytes(), b"existing video")
            self.assertEqual(list(root.glob("*.locallyfps-*")), [])


class InputValidationTests(unittest.TestCase):
    def test_cli_target_fps_rejects_non_finite_and_out_of_range_values(self):
        for value in (0, -1, math.nan, math.inf, -math.inf, 1000.1):
            self.assertFalse(_valid_cli_target_fps(value))
        for value in (1, 23.976, 60, 1000):
            self.assertTrue(_valid_cli_target_fps(value))

    def test_automatic_target_uses_familiar_smooth_rates(self):
        self.assertEqual(recommended_target_fps(23.976), 60)
        self.assertEqual(recommended_target_fps(30), 60)
        self.assertEqual(recommended_target_fps(50), 120)
        self.assertEqual(recommended_target_fps(120), 240)

    def test_invalid_config_values_are_repaired(self):
        repaired = _validated_config({
            "language": "bad", "crf": float("nan"), "preset": "turbo",
            "model": "../../bad", "video_preset": "bad",
        })
        self.assertEqual(repaired["crf"], 16)
        self.assertEqual(repaired["preset"], "fast")
        self.assertEqual(repaired["model"], "rife-v4.6")
        self.assertEqual(repaired["video_preset"], "balanced")
        self.assertEqual(repaired["encoder_mode"], "auto")


class DiskEstimateTests(unittest.TestCase):
    def test_frame_estimate_is_safe_for_incompressible_rgb(self):
        raw_size = 1920 * 1080 * 3 * 100
        self.assertGreaterEqual(estimate_frame_storage(1920, 1080, 100), raw_size)

    def test_pipeline_estimate_includes_source_and_generated_frames(self):
        estimate = estimate_pipeline_storage(100, 100, 30, 30, 60)
        self.assertEqual(estimate, estimate_frame_storage(100, 100, 90))


class ResumeTests(unittest.TestCase):
    def test_job_checkpoint_is_stable_and_invalidated_by_source_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "video.mp4"
            source.write_bytes(b"first")
            old_cache = paths.CACHE_DIR
            paths.CACHE_DIR = root / "cache"
            try:
                first = PipelineJob(source, 60, "rife-v4.6")
                first.update(extracted_frames=12)
                same = PipelineJob(source, 60, "rife-v4.6")
                self.assertEqual(same.root, first.root)
                self.assertEqual(same.load()["extracted_frames"], 12)
                source.write_bytes(b"changed source")
                changed = PipelineJob(source, 60, "rife-v4.6")
                self.assertNotEqual(changed.root, first.root)
            finally:
                paths.CACHE_DIR = old_cache

    @staticmethod
    def _fake_extract(_source, frames_dir, *_args, **_kwargs):
        for index in range(1, 3):
            (frames_dir / f"{index:08d}.png").touch()
        return 2

    @staticmethod
    def _fake_interpolation(**kwargs):
        for index in range(1, 5):
            (kwargs["out_frames_dir"] / f"{index:08d}.png").touch()
        return 60

    @mock.patch("core.pipeline.reassemble_video", return_value=None)
    @mock.patch("core.pipeline.run_interpolation", side_effect=_fake_interpolation)
    @mock.patch("core.pipeline.extract_frames", side_effect=_fake_extract)
    def test_failed_export_keeps_completed_interpolation_checkpoint(
        self, _extract, _interpolate, _reassemble,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            old_cache = paths.CACHE_DIR
            old_models = paths.MODELS_DIR
            paths.CACHE_DIR = root / "cache"
            paths.MODELS_DIR = root / "models"
            (paths.MODELS_DIR / "rife-v4.6").mkdir(parents=True)
            info = {
                "path": source, "width": 16, "height": 16,
                "display_width": 16, "display_height": 16,
                "frame_count": 2, "fps": 30, "duration": 2 / 30,
                "has_audio": False,
            }
            try:
                self.assertFalse(run_pipeline(
                    info, 60, root / "output.mp4",
                    {"gpu_id": 0, "uhd": False, "threads": "1:1:1"},
                    model="rife-v4.6",
                ))
                job = PipelineJob(source, 60, "rife-v4.6")
                self.assertTrue(job.root.is_dir())
                self.assertTrue(job.load()["interpolation_complete"])
                self.assertEqual(job.load()["output_frames"], 4)

                with mock.patch(
                    "core.pipeline._validate_generated_sequence", return_value=True,
                ):
                    _reassemble.return_value = root / "output.mp4"
                    self.assertTrue(run_pipeline(
                        info, 60, root / "output.mp4",
                        {"gpu_id": 0, "uhd": False, "threads": "1:1:1"},
                        model="rife-v4.6",
                    ))
                self.assertEqual(_extract.call_count, 1)
                self.assertEqual(_interpolate.call_count, 1)
                self.assertFalse(job.root.exists())
            finally:
                paths.CACHE_DIR = old_cache
                paths.MODELS_DIR = old_models


class ProgressTests(unittest.TestCase):
    @mock.patch("core.progress.time.time", side_effect=[0, 180])
    def test_frame_progress_is_not_formatted_as_bytes_and_eta_is_normalized(self, _time):
        output = io.StringIO()
        with mock.patch("core.progress.sys.stdout", output):
            bar = ProgressBar(total=300, desc="Interpolating", unit="frame")
            bar._enabled = True
            bar.current = 150
            bar._draw()
        rendered = output.getvalue()
        self.assertIn("150/300", rendered)
        self.assertNotIn("150B", rendered)
        self.assertIn("ETA 3min 0s", rendered)
        self.assertNotIn("60s", rendered)

    def test_stdio_configuration_tolerates_streams_without_reconfigure(self):
        with mock.patch("core.sys.stdout", io.StringIO()), mock.patch(
            "core.sys.stderr", io.StringIO(),
        ):
            _configure_stdio()


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

    @mock.patch("core.update_utils.sys.platform", "linux")
    def test_posix_update_swap_keeps_backup_and_has_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = create_swap_script(root / "Locally FPS", root / "Locally FPS_update")
            content = script.read_text()
            self.assertIn("if ! mv --", content)
            self.assertIn("Locally FPS.old", content)
            self.assertIn("mv -- 'Locally FPS.old' 'Locally FPS'", content)


class InterpolationValidationTests(unittest.TestCase):
    @mock.patch("core.interpolate.sys.platform", "linux")
    def test_linux_amd_gpu_forces_safe_fallback(self):
        self.assertTrue(_gpu_requires_safe_fallback("AMD Radeon Graphics (RADV RENOIR)"))
        self.assertFalse(_gpu_requires_safe_fallback("NVIDIA GeForce RTX 4070"))

    def test_validation_pairs_cover_the_whole_video(self):
        self.assertEqual(_validation_pair_indexes(2), [0])
        self.assertEqual(_validation_pair_indexes(102), [0, 25, 50, 75, 100])

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

    def test_intermediate_frames_across_scene_cuts_are_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs, outputs = root / "in", root / "out"
            inputs.mkdir()
            outputs.mkdir()
            for index, value in enumerate((b"A", b"B", b"C"), 1):
                (inputs / f"{index:08d}.png").write_bytes(value)
            for index in range(1, 7):
                (outputs / f"{index:08d}.png").write_bytes(b"AI")
            repaired = _repair_scene_cut_frames(inputs, outputs, 3, 6, {1})
            self.assertEqual(repaired, 1)
            self.assertEqual((outputs / "00000002.png").read_bytes(), b"B")
            self.assertEqual((outputs / "00000004.png").read_bytes(), b"AI")

    @mock.patch("core.interpolate._decode_rgb_frame", return_value=b"rgb")
    def test_generated_sequence_must_be_complete_and_contiguous(self, _decode):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(1, 4):
                (root / f"{index:08d}.png").touch()
            self.assertTrue(_validate_generated_sequence(root, 3))
            (root / "00000002.png").rename(root / "00000004.png")
            self.assertFalse(_validate_generated_sequence(root, 3))


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parent.parent
        ffmpeg = shutil.which("ffmpeg") or str(repo_root / "deps" / "ffmpeg" / "ffmpeg")
        ffprobe = shutil.which("ffprobe") or str(repo_root / "deps" / "ffmpeg" / "ffprobe")
        if not Path(ffmpeg).is_file() or not Path(ffprobe).is_file():
            self.skipTest("ffmpeg/ffprobe not installed")
        paths.FFMPEG_BIN = Path(ffmpeg)
        paths.FFPROBE_BIN = Path(ffprobe)

    def test_hdr_filter_has_separate_tonemap_stage(self):
        value = _get_pix_fmt_filter({"color_transfer": "smpte2084"})
        self.assertIn(",tonemap=tonemap=hable", value)
        self.assertNotIn("zscale=p=bt709:tonemap", value)

    @mock.patch("core.extract._supports_hdr_tonemapping", return_value=False)
    def test_hdr_is_rejected_when_required_filters_are_missing(self, _supported):
        with tempfile.TemporaryDirectory() as temp:
            frames = Path(temp) / "frames"
            frames.mkdir()
            info = {
                "color_transfer": "smpte2084", "width": 64, "height": 64,
                "frame_count": 1, "fps": 24, "duration": 1,
            }
            self.assertEqual(
                extract_frames(Path(temp) / "missing.mkv", frames, info,
                               progress_cb=lambda _: None),
                0,
            )
            self.assertEqual(list(frames.iterdir()), [])

    def test_timestamps_are_normalized_before_frame_extraction(self):
        value = _get_extraction_filter({"is_vfr": False, "fps": 24000 / 1001})
        self.assertIn("fps=23.976", value)
        self.assertTrue(value.endswith("format=rgb24"))

    def test_interlaced_input_is_deinterlaced_before_interpolation(self):
        value = _get_extraction_filter({"field_order": "tt", "fps": 25})
        self.assertTrue(value.startswith("bwdif="))
        self.assertIn(",fps=25,", value)

    def test_scene_changes_are_detected_from_normalized_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            frames = Path(temp) / "frames"
            frames.mkdir()
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-f", "lavfi", "-i",
                "color=red:size=64x64:rate=4:duration=1", "-f", "lavfi", "-i",
                "color=blue:size=64x64:rate=4:duration=1", "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0", str(frames / "%08d.png"),
            ], check=True)
            self.assertEqual(_detect_scene_cuts(frames, 4, 8), {4})

    def test_10bit_hdr_extraction(self):
        filters = subprocess.run(
            [str(paths.FFMPEG_BIN), "-filters"], capture_output=True, text=True
        ).stdout
        if "zscale" not in filters or "tonemap" not in filters:
            self.fail("FFmpeg lacks the zscale/tonemap filters required for HDR input")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "hdr10.mkv"
            frames = root / "frames"
            frames.mkdir()
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-f", "lavfi", "-i",
                "testsrc2=size=96x64:rate=24:duration=0.25", "-pix_fmt", "yuv420p10le",
                "-color_primaries", "bt2020", "-color_trc", "smpte2084",
                "-colorspace", "bt2020nc", "-c:v", "ffv1", "-level", "3", str(source),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            info = probe_video_file(source)
            self.assertEqual(info["codec"], "ffv1")
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
            info = probe_video_file(original)
            self.assertTrue(info["has_audio"])
            self.assertEqual(info["audio_tracks"], 2)
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-i", str(original),
                str(frames / "%08d.png"),
            ], check=True)
            enc = {"codec": "libx264", "pix_fmt": "yuv420p", "hwaccel": None}
            cmd = _build_encode_command(
                enc, frames, original, 2, output, True, 1.0, 18, "fast",
                info,
            )
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            result = subprocess.run([
                str(paths.FFPROBE_BIN), "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", str(output),
            ], capture_output=True, text=True, check=True)
            self.assertEqual(len(result.stdout.strip().splitlines()), 2)
            self.assertTrue(_validate_output(
                output, expected_fps=2, expected_frames=2,
                expected_duration=1.0, expected_audio_tracks=2,
            ))

    @mock.patch("core.interpolate._gpu_requires_safe_fallback", return_value=True)
    def test_safe_backend_end_to_end_keeps_audio_and_exact_fps(self, _fallback):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.mkv"
            in_frames = root / "in"
            out_frames = root / "out"
            output = root / "output.mkv"
            in_frames.mkdir()
            out_frames.mkdir()
            subprocess.run([
                str(paths.FFMPEG_BIN), "-v", "error", "-y", "-f", "lavfi",
                "-i", "testsrc2=size=64x64:rate=6:duration=1", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1", "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(original),
            ], check=True)
            info = probe_video_file(original)
            source_count = extract_frames(
                original, in_frames, info, progress_cb=lambda _: None,
            )
            actual_fps = run_interpolation(
                in_frames, out_frames, "rife-v4.6", "1:1:1",
                source_count, info["fps"], 12, gpu_id=0, gpu_name="test",
                progress_cb=lambda _: None,
            )
            result_frames = len(list(out_frames.glob("*.png")))
            self.assertEqual(actual_fps, 12)
            self.assertEqual(result_frames, 12)
            final = reassemble_video(
                out_frames, original, actual_fps, True, output, result_frames,
                encoder_name="libx264", info=info, progress_cb=lambda _: None,
            )
            self.assertEqual(final, output)
            self.assertTrue(_validate_output(
                output, expected_fps=12, expected_frames=12,
                expected_duration=1.0, expected_audio_tracks=1,
            ))


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

    @mock.patch("core.probe.subprocess.run")
    def test_audio_and_subtitles_are_detected_alongside_video(self, run):
        payload = {
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264",
                 "width": 10, "height": 10, "avg_frame_rate": "30/1",
                 "r_frame_rate": "30/1", "nb_frames": "30",
                 "sample_aspect_ratio": "1:1"},
                {"index": 1, "codec_type": "audio", "codec_name": "aac"},
                {"index": 2, "codec_type": "subtitle", "codec_name": "subrip"},
            ],
            "format": {"duration": "1", "size": "100"},
        }
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mkv"
            video.touch()
            info = probe_video_file(video)
        self.assertTrue(info["has_audio"])
        self.assertEqual(info["audio_tracks"], 1)
        self.assertEqual(info["video_stream_index"], 0)
        self.assertEqual(info["subtitle_streams"], [{"index": 2, "codec": "subrip"}])


class ArchiveSafetyTests(unittest.TestCase):
    def test_integrity_failure_is_quarantined_without_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            original = Path(temp) / "dependency.bin"
            original.write_bytes(b"recoverable")
            quarantined = manifest.quarantine(original)
            self.assertFalse(original.exists())
            self.assertEqual(quarantined.read_bytes(), b"recoverable")

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
