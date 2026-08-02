import argparse
import sys
from pathlib import Path

from . import paths
from .colors import Color
from .config import CONFIG, DEFAULT_CONFIG
from .console import status, ask_yes_no
from .gpu import choose_gpu_settings
from .i18n import _
from .output import resolve_output_path
from .pipeline import run_pipeline
from .probe import probe_video_file, print_video_metadata
from .progress import Spinner
from .settings import _run_settings
from .utils import format_duration, format_fps, human_size


def prompt_for_video():
    from platform import get_platform
    plat = get_platform()
    videos_dir = paths.VIDEOS_DIR / "original"

    if not videos_dir.exists():
        videos_dir.mkdir(parents=True, exist_ok=True)

    video_files = [f for f in videos_dir.iterdir() if f.is_file()]
    video_files = [f for f in video_files if f.suffix.lower() in ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv')]

    if not video_files:
        print(f"\n{Color.bold(_('Select video to enhance - (b to go back)'))}")
        print(f"{Color.warn(_('No videos found in videos/original/'))}")
        print(f"{Color.dim(_('Place your videos in the videos/original/ folder to process them.'))}")
        print()
        try:
            raw = input(f"{Color.magenta('▸')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back", "←"):
            return None
        return None

    video_names = [f.name for f in video_files]

    print(f"\n{Color.bold(_('Select video to enhance - (b to go back)'))}")
    print(f"{Color.dim(_('Videos in videos/original/:'))}")

    if sys.stdin.isatty():
        i = plat.interactive_select_video(video_names)
        if i < 0 or i >= len(video_files):
            return None
        selected_video = video_files[i]
    else:
        for i, name in enumerate(video_names, 1):
            print(f"  {i}. {name}")
        try:
            raw = input(f"{Color.magenta('▸')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back", "←"):
            return None
        try:
            i = int(raw) - 1
            if i < 0 or i >= len(video_files):
                print(f"{Color.warn(_('Enter a number between 1 and'))} {len(video_files)}.")
                return None
            selected_video = video_files[i]
        except ValueError:
            print(f"{Color.warn(_('Enter a valid number.'))}")
            return None

    sp = Spinner(_("Verifying video file..."))
    info = probe_video_file(selected_video)
    if info is None:
        sp.ok(f"{Color.warn(_('Not a processable video file.'))}")
        return None
    sp.ok(f"{Color.info(_('Video'))}: {Color.bold(selected_video.name)}, {_('FPS')}: {format_fps(info['fps'])}, {_('Resolution')}: {info['width']}x{info['height']}, {_('Duration')}: {format_duration(info['duration'])}, {_('Size')}: {human_size(info['size_bytes'])}")

    info['path'] = selected_video
    return info


def prompt_for_fps(source_fps):
    print(f"\n{Color.bold(_('Target FPS'))}")
    while True:
        try:
            raw = input(f"{Color.magenta('▸')} ").strip().replace(",", ".")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back", "←"):
            return None
        try:
            fps = float(raw)
        except ValueError:
            print(f"{Color.warn(_('Enter a valid number.'))}")
            continue
        if fps <= 0:
            print(f"{Color.warn(_('FPS must be greater than 0.'))}")
            continue
        if fps > 240:
            if not ask_yes_no(f"{fps} {_('is very high. Are you sure?')}", default=False):
                continue
        if fps <= source_fps:
            if not ask_yes_no(
                f"{fps} {_('is not higher than the current framerate (')}{format_fps(source_fps)}). {_('Continue anyway?')}",
                default=False,
            ):
                continue
        return fps


def prompt_for_output(input_path, target_fps):
    return resolve_output_path("", input_path, target_fps)


def interactive_wizard():
    from .deps import ensure_ffmpeg, ensure_rife
    from .models import ensure_default_model
    print(f"\n{Color.bold(_('=== LocallyFPS'))} - v{paths.APP_VERSION} ===\n")
    sp = Spinner(_("Checking system dependencies..."))
    ensure_ffmpeg()
    ensure_rife()
    ensure_default_model()
    sp.ok(_("All dependencies ready"))

    from platform import get_platform
    plat = get_platform()

    while True:
        menu_items = [
            _("Enhance video"),
            _("Settings"),
            _("Exit"),
        ]
        i = plat.interactive_select("", menu_items)
        if i == 0:
            pass
        elif i == 1:
            _run_settings()
            continue
        else:
            sys.exit(0)

        info = prompt_for_video()
        if info is None:
            continue
        gpu_settings = choose_gpu_settings(info["width"], info["height"])
        target_fps = prompt_for_fps(info["fps"])
        if target_fps is None:
            continue
        output_path = prompt_for_output(info["path"], target_fps)
        if output_path is None:
            continue

        run_pipeline(info, target_fps, output_path, gpu_settings)
        print()


def parse_args():
    parser = argparse.ArgumentParser(
        description=_("LocallyFPS – frame interpolation for video using RIFE AI models.")
    )
    parser.add_argument("input", nargs="?", type=str, help=_("Input video path"))
    parser.add_argument("--target-fps", type=float, default=60.0, help=_("Target FPS (default: 60)"))
    parser.add_argument("--model", type=str, default=None, help=_("RIFE model (default: rife-v4.6)"))
    parser.add_argument("--threads", type=str, default=None, help=_("Threads load:proc:save (default: auto based on GPU)"))
    parser.add_argument("--gpu-id", type=int, default=None, help=_("Vulkan GPU ID to use (default: auto)"))
    parser.add_argument("--uhd", action="store_true", help=_("Force UHD mode (recommended for 4K+)"))
    parser.add_argument("--output", type=str, default=None, help=_("Output path (default: ENHANCED_fpsFPS_filename)"))
    parser.add_argument("--yes", action="store_true", help=_("Skip interactive confirmation"))
    parser.add_argument("--config", action="store_true", help=_("Open settings menu"))
    return parser.parse_args()


def main_cli(args):
    from .deps import ensure_ffmpeg, ensure_rife
    from .models import ensure_default_model
    if args.config:
        _run_settings()
        return

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        status(f"{_('The input file does not exist:')} {input_path}", "ERROR")
        sys.exit(1)

    ensure_ffmpeg()
    ensure_rife()
    ensure_default_model()
    info = probe_video_file(input_path)
    if info is None:
        status(_("Not a processable video file."), "ERROR")
        sys.exit(1)
    print_video_metadata(info)

    gpu_settings = choose_gpu_settings(info["width"], info["height"])
    if args.threads:
        gpu_settings["threads"] = args.threads
    if args.gpu_id is not None:
        gpu_settings["gpu_id"] = args.gpu_id
    if args.uhd:
        gpu_settings["uhd"] = True

    output_path = resolve_output_path(args.output or "", input_path, args.target_fps)
    if output_path.exists() and not args.yes:
        if not ask_yes_no(f"{_('Already exists:')} {output_path.name}. {_('Overwrite?')}"):
            status(_("Output file exists. Skipped."), "WARN")
            return False

    return run_pipeline(
        info,
        args.target_fps,
        output_path,
        gpu_settings,
        model=args.model,
    )


def main():
    from .config import load_config
    from .i18n import load_translations
    from .deps import ensure_ffmpeg, ensure_rife
    from .models import ensure_default_model
    from .paths import ensure_dirs, any_dep_missing

    ensure_dirs()
    load_config()
    load_translations()

    is_first_run = not paths.CONFIG_PATH.exists() or "language" not in CONFIG
    if is_first_run:
        from .settings import _run_language_wizard
        _run_language_wizard()

    if sys.stdout.isatty() and any_dep_missing():
        if ask_yes_no(_("Do you want to install all missing dependencies?"), default=True):
            sp = Spinner(_("Installing dependencies..."))
            ensure_ffmpeg(auto_yes=True)
            ensure_rife(auto_yes=True)
            ensure_default_model(auto_yes=True)
            sp.ok(_("All dependencies ready"))

    args = parse_args()

    if args.config:
        if not sys.stdout.isatty():
            print(_("Settings menu requires an interactive terminal."), file=sys.stderr)
            print(f"{_('Edit the config file directly:')} {paths.CONFIG_PATH}", file=sys.stderr)
            sys.exit(1)
        _run_settings()
        return

    if args.input:
        main_cli(args)
    else:
        interactive_wizard()
