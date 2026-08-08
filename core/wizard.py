import argparse
import atexit
import shutil
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
from .utils import format_fps

if sys.platform.startswith("linux") and sys.stdin.isatty():
    import termios as _termios
    _SAVED_TERMIOS = _termios.tcgetattr(sys.stdin.fileno())
    def _restore_terminal():
        try:
            _termios.tcsetattr(sys.stdin.fileno(), _termios.TCSANOW, _SAVED_TERMIOS)
        except Exception:
            pass
    atexit.register(_restore_terminal)
else:
    _SAVED_TERMIOS = None


def prompt_for_video():
    from platform import get_platform
    plat = get_platform()
    videos_dir = paths.VIDEOS_DIR / "original"

    if not videos_dir.exists():
        videos_dir.mkdir(parents=True, exist_ok=True)

    video_files = [f for f in videos_dir.iterdir() if f.is_file()]
    video_files = [f for f in video_files if f.suffix.lower() in ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv')]

    term_w = shutil.get_terminal_size().columns

    if not video_files:
        sys.stdout.write("\033[2J\033[H\033[3J")
        _write_version_corner()
        header = _("SELECT A VIDEO")
        hp = max(0, (term_w - len(header)) // 2)
        msg1 = _("No videos found in videos/original/")
        msg2 = _("Place your videos in the videos/original/ folder to process them.")
        sys.stdout.write("\n\n\n")
        sys.stdout.write(" " * hp + Color.accent_bold(header) + "\n\n")
        sys.stdout.write(" " * max(0, (term_w - len(msg1)) // 2) + Color.warn(msg1) + "\n")
        sys.stdout.write(" " * max(0, (term_w - len(msg2)) // 2) + Color.dim(msg2) + "\n")
        sys.stdout.write("\n")
        sys.stdout.flush()
        try:
            raw = input(" " * max(0, (term_w - 3) // 2) + "b " + Color.dim(_("(Back)")) + " ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        return None

    video_names = [f.name for f in video_files]

    sys.stdout.write("\033[2J\033[H\033[3J")
    _write_version_corner()
    header = _("SELECT A VIDEO")
    hp = max(0, (term_w - len(header)) // 2)
    sub = _("videos/original/")
    sp = max(0, (term_w - len(sub)) // 2)
    sys.stdout.write("\n\n")
    sys.stdout.write(" " * hp + Color.accent_bold(header) + "\n")
    sys.stdout.write(" " * sp + Color.dim(sub) + "\n\n")
    hint = _("Up/Down to navigate, Enter to select, B to go back")
    sys.stdout.write(" " * max(0, (term_w - len(hint)) // 2) + Color.dim(hint) + "\n\n\n")
    sys.stdout.flush()

    if sys.stdin.isatty():
        i = plat.interactive_select_video(video_names)
        if i < 0 or i >= len(video_files):
            return None
        selected_video = video_files[i]
    else:
        for i, name in enumerate(video_names, 1):
            print(f"  {i}. {name}")
        try:
            raw = input(f"{Color.magenta('>')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("b", "back"):
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

    sp = Spinner(_("Probing video..."))
    info = probe_video_file(selected_video)
    if info is None:
        sp.ok(f"{Color.warn(_('Not a processable video file.'))}")
        return None

    info['path'] = selected_video
    return info


def _validate_fps(raw, source_fps):
    raw = raw.strip().replace(",", ".")
    try:
        fps = float(raw)
    except ValueError:
        print(f"{Color.warn(_('Enter a valid number.'))}")
        return None
    if fps <= 0:
        print(f"{Color.warn(_('FPS must be greater than 0.'))}")
        return None
    if fps > 240:
        if not ask_yes_no(f"{fps} {_('is very high. Are you sure?')}", default=False):
            return None
    if fps <= source_fps:
        if not ask_yes_no(
            f"{fps} {_('is not higher than the current framerate (')}{format_fps(source_fps)}). {_('Continue anyway?')}",
            default=False,
        ):
            return None
    return fps


def _prompt_fps_raw(source_fps):
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        term_w = shutil.get_terminal_size().columns
        prompt_pad = " " * max(0, (term_w - 2) // 2)
        while True:
            buf = ""
            sys.stdout.write(prompt_pad + f"{Color.magenta('>')} ")
            sys.stdout.flush()
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x03":
                    sys.stdout.write("\r\x1b[K\r\n")
                    sys.stdout.flush()
                    return None
                if ch in ("b", "B"):
                    sys.stdout.write("\r\x1b[K\r\n")
                    sys.stdout.flush()
                    return None
                if ch in ("\r", "\n"):
                    break
                if ch in ("\x7f", "\x08"):
                    if buf:
                        buf = buf[:-1]
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                if ch.isdigit() or ch in (".", ","):
                    buf += ch
                    sys.stdout.write(ch)
                    sys.stdout.flush()
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSANOW, old)
            fps = _validate_fps(buf, source_fps)
            if fps is not None:
                return fps
            tty.setraw(fd)
            import termios as _t
            _t.tcflush(fd, _t.TCIFLUSH)
    except KeyboardInterrupt:
        sys.stdout.write("\r\n")
        sys.stdout.flush()
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)


def prompt_for_fps(source_fps, video_name=None):
    term_w = shutil.get_terminal_size().columns
    sys.stdout.write("\033[2J\033[H\033[3J")
    _write_version_corner()
    header = _("TARGET FPS")
    hp = max(0, (term_w - len(header)) // 2)
    cur_fps = f"{_('Current')}: {format_fps(source_fps)}"
    cp = max(0, (term_w - len(cur_fps)) // 2)

    sys.stdout.write("\n\n\n")
    if video_name:
        np = max(0, (term_w - len(video_name)) // 2)
        sys.stdout.write(" " * np + Color.bold(video_name) + "\n\n")
    sys.stdout.write(" " * hp + Color.accent_bold(header) + "\n")
    sys.stdout.write(" " * cp + Color.dim(cur_fps) + "\n")
    sys.stdout.write("\n")
    sys.stdout.flush()

    if sys.platform.startswith("linux") and sys.stdin.isatty():
        return _prompt_fps_raw(source_fps)

    while True:
        try:
            prompt_text = f"{Color.magenta('>')} "
            raw = input(prompt_text).strip().replace(",", ".")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        fps = _validate_fps(raw, source_fps)
        if fps is not None:
            return fps


def prompt_for_output(input_path, target_fps):
    return resolve_output_path("", input_path, target_fps)


_RAINBOW = [196, 202, 208, 214, 220, 226, 154, 118, 82, 46, 47, 48, 49, 50, 51, 45, 39, 33, 27, 57, 93, 129, 165, 201]


def _gradient_line(line):
    total = max(1, sum(2 if ch == '█' else 1 for ch in line) - 1)
    col = 0
    out = []
    for ch in line:
        frac = col / total
        idx = _RAINBOW[min(int(frac * (len(_RAINBOW) - 1)), len(_RAINBOW) - 1)]
        out.append(f"\033[38;5;{idx}m{ch}\033[0m")
        col += 2 if ch == '█' else 1
    return "".join(out)


LOGO_LINES = [
    "██╗      ██████╗  ██████╗ █████╗ ██╗     ██╗  ██╗   ██╗███████╗██████╗ ███████╗",
    "██║     ██╔═══██╗██╔════╝██╔══██╗██║     ██║  ╚██╗ ██╔╝██╔════╝██╔══██╗██╔════╝",
    "██║     ██║   ██║██║     ███████║██║     ██║   ╚████╔╝ █████╗  ██████╔╝███████╗",
    "██║     ██║   ██║██║     ██╔══██║██║     ██║    ╚██╔╝  ██╔══╝  ██╔═══╝ ╚════██║",
    "███████╗╚██████╔╝╚██████╗██║  ██║███████╗███████╗██║   ██║     ██║     ███████║",
    "╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝   ╚═╝     ╚═╝     ╚══════╝",
]


def _write_version_corner():
    term_h = shutil.get_terminal_size().lines
    sys.stdout.write("\x1b[s")
    sys.stdout.write(f"\x1b[{term_h};1H")
    sys.stdout.write(Color.dim("v" + paths.APP_VERSION))
    sys.stdout.write("\x1b[u")
    sys.stdout.flush()


def interactive_wizard():
    from .deps import ensure_ffmpeg, ensure_rife
    from .models import ensure_default_model
    ensure_ffmpeg()
    ensure_rife()
    ensure_default_model()

    from platform import get_platform
    plat = get_platform()

    while True:
        menu_items = [
            _("Enhance video"),
            _("Settings"),
            _("Check for updates"),
            _("Exit"),
        ]
        term_w, term_h = shutil.get_terminal_size().columns, shutil.get_terminal_size().lines

        sys.stdout.write("\033[2J\033[3J")
        sys.stdout.write("\033[H")
        _write_version_corner()

        logo_vis_w = max(len(line) + line.count('█') for line in LOGO_LINES)
        has_logo = term_w >= logo_vis_w + 4
        header_lines = (len(LOGO_LINES) + 1) if has_logo else 2
        vpad = max(0, (term_h - header_lines - len(menu_items)) // 2 - 5)
        sys.stdout.write("\n" * vpad)

        if has_logo:
            logo_raw_w = max(len(line) for line in LOGO_LINES)
            logo_pad = max(0, (term_w - logo_raw_w) // 2)
            for line in LOGO_LINES:
                sys.stdout.write(" " * logo_pad + _gradient_line(line) + "\n")
        else:
            title = f"=== LocallyFPS ==="
            sys.stdout.write(" " * max(0, (term_w - len(title)) // 2) + Color.accent_bold(title) + "\n")
        sys.stdout.write("\n\n\n\n")
        sys.stdout.flush()

        i = plat.interactive_select("", menu_items)
        if i == 0:
            pass
        elif i == 1:
            _run_settings()
            continue
        elif i == 2:
            from .updater import run_updater
            run_updater()
            continue
        else:
            sys.exit(0)

        info = prompt_for_video()
        if info is None:
            continue
        gpu_settings = choose_gpu_settings(info["width"], info["height"])
        target_fps = prompt_for_fps(info["fps"], info["path"].name)
        if target_fps is None:
            continue
        output_path = prompt_for_output(info["path"], target_fps)
        if output_path is None:
            continue

        run_pipeline(info, target_fps, output_path, gpu_settings, interactive=True)
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
