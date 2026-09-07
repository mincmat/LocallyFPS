import argparse
import math
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QThread, QTimer, QUrl, Signal, Slot, QLocale
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter,
    QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget, QLineEdit,
    QProgressBar, QCheckBox, QDialog,
)

from core import paths
from core import config


SUPPORTED_EXTENSIONS = {
    ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".ogv", ".3gp", ".vob",
}

LANGUAGES = [
    ("Español", "es"), ("English", "en"), ("Português", "pt"),
    ("Français", "fr"), ("Deutsch", "de"), ("中文", "zh"),
    ("日本語", "ja"), ("한국어", "ko"), ("Русский", "ru"), ("العربية", "ar"),
]


class SetupWorker(QObject):
    progress = Signal(int, str, str)
    finished = Signal(bool, str)

    @Slot()
    def run(self):
        try:
            from core.deps import _setup_system_paths, ensure_ffmpeg, ensure_rife
            from core.models import ensure_default_model

            paths.ensure_dirs()
            _setup_system_paths()

            class Bar:
                def __init__(inner_self, owner, start, span, component):
                    inner_self.owner, inner_self.start = owner, start
                    inner_self.span, inner_self.component = span, component
                    inner_self.error = ""

                def update(inner_self, fraction, label=None, **_kwargs):
                    value = inner_self.start + int(max(0, min(1, float(fraction))) * inner_self.span)
                    inner_self.owner.progress.emit(value, str(label or inner_self.component), inner_self.component)

                def ok(inner_self, label):
                    inner_self.owner.progress.emit(inner_self.start + inner_self.span, str(label), inner_self.component)

                def fail(inner_self, label):
                    inner_self.error = str(label)
                    inner_self.owner.progress.emit(inner_self.start, str(label), inner_self.component)

            ffmpeg = Bar(self, 3, 22, "FFmpeg")
            self.progress.emit(2, "Comprobando FFmpeg…", "FFmpeg")
            if not ensure_ffmpeg(auto_yes=True, bar=ffmpeg):
                raise RuntimeError(ffmpeg.error or "No se pudo instalar FFmpeg")
            rife = Bar(self, 25, 65, "Motor de IA")
            self.progress.emit(25, "Preparando el motor de IA…", "Motor de IA")
            if not ensure_rife(auto_yes=True, bar=rife):
                raise RuntimeError(rife.error or "No se pudo instalar el motor de IA")
            self.progress.emit(92, "Comprobando el modelo…", "Modelo RIFE")
            ensure_default_model(auto_yes=True)
            if not (paths.MODELS_DIR / "rife-v4.6").is_dir():
                raise RuntimeError("No se pudo preparar el modelo RIFE")
            self.progress.emit(100, "Todo está listo", "Componentes verificados")
            self.finished.emit(True, "")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class SettingsDialog(QDialog):
    repair_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración · LocallyFPS")
        self.setModal(True)
        self.setMinimumSize(740, 650)
        self.setObjectName("settingsDialog")
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 30, 34, 30)
        root.setSpacing(18)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Configuración")
        title.setObjectName("headline")
        subtitle = QLabel("Tu experiencia, sin complicaciones.")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading.addLayout(title_box)
        heading.addStretch()
        root.addLayout(heading)

        general = QFrame()
        general.setObjectName("settingsSection")
        general.setMinimumHeight(175)
        form = QVBoxLayout(general)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(13)
        label = QLabel("GENERAL")
        label.setObjectName("eyebrow")
        form.addWidget(label)
        self.language = self._row_combo(form, "Idioma", "El idioma de botones y mensajes", LANGUAGES,
                                        config.CONFIG.get("language", "en"))
        fps_items = [("Automático · recomendado", "auto"), ("60 FPS", "60"),
                     ("120 FPS", "120"), ("240 FPS", "240")]
        self.default_fps = self._row_combo(form, "FPS predeterminados", "Se aplica al agregar videos", fps_items,
                                           config.CONFIG.get("default_target_fps", "auto"))
        root.addWidget(general)

        output = QFrame()
        output.setObjectName("settingsSection")
        output.setMinimumHeight(112)
        output_layout = QVBoxLayout(output)
        output_layout.setContentsMargins(24, 20, 24, 20)
        output_layout.setSpacing(12)
        output_label = QLabel("RESULTADOS")
        output_label.setObjectName("eyebrow")
        output_layout.addWidget(output_label)
        path_row = QHBoxLayout()
        path_text = QVBoxLayout()
        path_text.addWidget(QLabel("Carpeta de salida"))
        path_hint = QLabel("Vacío usa la carpeta de videos de LocallyFPS")
        path_hint.setObjectName("muted")
        path_text.addWidget(path_hint)
        path_row.addLayout(path_text)
        self.output_path = QLineEdit(config.CONFIG.get("output_directory", ""))
        self.output_path.setPlaceholderText("Automática")
        path_row.addWidget(self.output_path, 1)
        choose = QPushButton("Elegir")
        choose.setObjectName("ghostButton")
        choose.clicked.connect(self._choose_output)
        path_row.addWidget(choose)
        output_layout.addLayout(path_row)
        root.addWidget(output)

        engine = QFrame()
        engine.setObjectName("settingsSection")
        engine_layout = QHBoxLayout(engine)
        engine_layout.setContentsMargins(24, 18, 24, 18)
        engine_text = QVBoxLayout()
        engine_title = QLabel("Motor de interpolación")
        engine_hint = QLabel("Comprobá o repará FFmpeg, RIFE y el modelo")
        engine_hint.setObjectName("muted")
        engine_text.addWidget(engine_title)
        engine_text.addWidget(engine_hint)
        engine_layout.addLayout(engine_text)
        engine_layout.addStretch()
        repair = QPushButton("Comprobar")
        repair.setObjectName("ghostButton")
        repair.clicked.connect(self._repair)
        engine_layout.addWidget(repair)
        root.addWidget(engine)
        root.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghostButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Guardar cambios")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

    def _row_combo(self, layout, title, hint, values, selected):
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(QLabel(title))
        muted = QLabel(hint)
        muted.setObjectName("muted")
        text.addWidget(muted)
        row.addLayout(text)
        row.addStretch()
        combo = QComboBox()
        for name, value in values:
            combo.addItem(name, value)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        combo.setMinimumWidth(230)
        row.addWidget(combo)
        layout.addLayout(row)
        return combo

    def _choose_output(self):
        selected = QFileDialog.getExistingDirectory(self, "Carpeta de resultados", self.output_path.text() or str(Path.home()))
        if selected:
            self.output_path.setText(selected)

    def _repair(self):
        self.accept()
        self.repair_requested.emit()

    def _save(self):
        config.CONFIG["language"] = self.language.currentData()
        config.CONFIG["default_target_fps"] = self.default_fps.currentData()
        config.CONFIG["output_directory"] = self.output_path.text().strip()
        config.save_config()
        self.accept()


class MagicCanvas(QWidget):
    """Small, inexpensive animated visualization driven by real progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(245)
        self._phase = 0.0
        self._progress = 0.0
        self._active = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_progress(self, value):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def set_active(self, active):
        self._active = bool(active)
        self.update()

    def _tick(self):
        self._phase = (self._phase + (0.045 if self._active else 0.012)) % (math.pi * 2)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) * 0.28

        glow = QRadialGradient(center, radius * 2.1)
        glow.setColorAt(0.0, QColor(130, 88, 255, 90 if self._active else 52))
        glow.setColorAt(0.45, QColor(49, 208, 255, 32))
        glow.setColorAt(1.0, QColor(8, 10, 25, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 2.1, radius * 2.1)

        for index in range(18):
            angle = self._phase * (1.0 + index % 3 * 0.12) + index * math.pi * 2 / 18
            orbit = radius * (1.35 + 0.22 * math.sin(index * 1.7 + self._phase))
            x = center.x() + math.cos(angle) * orbit
            y = center.y() + math.sin(angle) * orbit * 0.58
            size = 1.7 + (index % 4) * 0.65
            color = QColor(112, 221, 255) if index % 2 else QColor(192, 123, 255)
            color.setAlpha(80 + (index % 5) * 30)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), size, size)

        ring = self.rect().adjusted(
            int(center.x() - radius), int(center.y() - radius),
            -int(self.width() - center.x() - radius),
            -int(self.height() - center.y() - radius),
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 25), 9))
        painter.drawEllipse(ring)
        gradient = QLinearGradient(ring.topLeft(), ring.bottomRight())
        gradient.setColorAt(0, QColor("#8b5cf6"))
        gradient.setColorAt(0.52, QColor("#38bdf8"))
        gradient.setColorAt(1, QColor("#34d399"))
        painter.setPen(QPen(gradient, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, 90 * 16, -int(max(self._progress, 0.018) * 360 * 16))

        painter.setPen(QColor("#f8fafc"))
        font = QFont("Sans Serif", 27, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(ring, Qt.AlignmentFlag.AlignCenter, f"{round(self._progress * 100)}%")


class DropCard(QFrame):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropCard")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(7)
        icon = QLabel("✦")
        icon.setObjectName("dropIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Soltá tus videos acá")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("o hacé clic para elegirlos · MP4, MKV, MOV, WebM y más")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(hint)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.files_dropped.emit([])
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.files_dropped.emit(files)
        event.acceptProposedAction()


class EnhanceWorker(QObject):
    progress = Signal(float, str, str)
    item_finished = Signal(str, bool, str)
    finished = Signal(list, list)

    def __init__(self, videos, target_fps):
        super().__init__()
        self.videos = [Path(video) for video in videos]
        self.target_fps = target_fps
        self._stop_after_current = False

    @Slot()
    def request_stop(self):
        self._stop_after_current = True

    @Slot()
    def run(self):
        completed, failed = [], []
        try:
            from core.config import load_config
            from core.deps import _setup_system_paths, ensure_ffmpeg, ensure_rife
            from core.gpu import choose_gpu_settings
            from core.i18n import load_translations
            from core.models import ensure_default_model
            from core.output import resolve_output_path, unique_output_path
            from core.pipeline import run_pipeline
            from core.probe import probe_video_file
            from core.wizard import recommended_target_fps

            paths.ensure_dirs()
            load_config()
            load_translations()
            _setup_system_paths()
            self.progress.emit(0.01, "Preparando el motor…", "")

            class DependencyProgress:
                def __init__(inner_self, worker):
                    inner_self.worker = worker
                    inner_self.last_error = ""

                def update(inner_self, fraction, label=None, **_kwargs):
                    value = 0.02 + max(0.0, min(1.0, float(fraction))) * 0.06
                    inner_self.worker.progress.emit(
                        value, str(label or "Preparando componentes…"), "Solo la primera vez",
                    )

                def ok(inner_self, label):
                    inner_self.worker.progress.emit(0.08, str(label), "Componentes listos")

                def fail(inner_self, label):
                    inner_self.last_error = str(label)
                    inner_self.worker.progress.emit(0.08, str(label), "Revisá tu conexión")

            dependency_progress = DependencyProgress(self)
            if not ensure_ffmpeg(auto_yes=True, bar=dependency_progress):
                detail = dependency_progress.last_error or "Error de descarga desconocido"
                raise RuntimeError(f"No se pudo preparar FFmpeg: {detail}")
            ensure_rife(auto_yes=True, bar=dependency_progress)
            ensure_default_model(auto_yes=True)

            total = max(len(self.videos), 1)
            for index, video in enumerate(self.videos):
                if self._stop_after_current:
                    break
                self.progress.emit(0.1 + 0.9 * index / total, "Leyendo el video…", video.name)
                info = probe_video_file(video)
                if info is None:
                    failed.append((str(video), "Formato de video no reconocido"))
                    self.item_finished.emit(str(video), False, "Formato no reconocido")
                    continue
                target = self.target_fps or recommended_target_fps(info["fps"])
                output = unique_output_path(resolve_output_path(
                    config.CONFIG.get("output_directory", ""), video, target,
                ))
                gpu = choose_gpu_settings(
                    info.get("display_width", info["width"]),
                    info.get("display_height", info["height"]),
                )

                def report(fraction, label, *, item=index, name=video.name):
                    overall = 0.1 + 0.9 * (item + max(0.0, min(1.0, fraction))) / total
                    self.progress.emit(overall, str(label), name)

                try:
                    ok = run_pipeline(
                        info, target, output, gpu, interactive=False,
                        progress_cb=report,
                    )
                except Exception as exc:
                    ok = False
                    failed.append((str(video), str(exc)))
                if ok:
                    completed.append(str(output))
                    self.item_finished.emit(str(video), True, str(output))
                else:
                    if not any(name == str(video) for name, _ in failed):
                        failed.append((str(video), "La interpolación no pudo completarse"))
                    self.item_finished.emit(str(video), False, failed[-1][1])
        except Exception as exc:
            failed.append(("", str(exc)))
        self.finished.emit(completed, failed)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LocallyFPS · v{paths.APP_VERSION}")
        self.setMinimumSize(980, 680)
        self.resize(1120, 760)
        self.video_paths = []
        self.output_paths = []
        self.worker = None
        self.thread = None
        self.setup_worker = None
        self.setup_thread = None
        self._build_ui()
        if not config.CONFIG.get("onboarding_complete", False) or paths.any_dep_missing():
            self.pages.setCurrentWidget(self.onboarding_page)
        else:
            self.pages.setCurrentWidget(self.main_page)

    def _build_ui(self):
        self.pages = QStackedWidget()
        self.pages.setObjectName("root")
        self.setCentralWidget(self.pages)
        self.onboarding_page = self._build_onboarding()
        self.main_page = QWidget()
        self.main_page.setObjectName("root")
        self.pages.addWidget(self.onboarding_page)
        self.pages.addWidget(self.main_page)
        root = self.main_page
        outer = QVBoxLayout(root)
        outer.setContentsMargins(42, 32, 42, 34)
        outer.setSpacing(24)

        header = QHBoxLayout()
        brand = QLabel("Locally<span style='color:#a78bfa'>FPS</span>")
        brand.setObjectName("brand")
        brand.setTextFormat(Qt.TextFormat.RichText)
        beta = QLabel("4.0  BETA")
        beta.setObjectName("beta")
        header.addWidget(brand)
        header.addWidget(beta)
        header.addStretch()
        self.theme_button = QPushButton("☾")
        self.theme_button.setObjectName("iconButton")
        self.theme_button.setToolTip("Apariencia")
        self.theme_button.clicked.connect(self._theme_notice)
        header.addWidget(self.theme_button)
        settings_button = QPushButton("⚙")
        settings_button.setObjectName("iconButton")
        settings_button.setToolTip("Configuración")
        settings_button.clicked.connect(self._show_settings)
        header.addWidget(settings_button)
        outer.addLayout(header)

        workspace = QFrame()
        workspace.setObjectName("workspace")
        content = QHBoxLayout(workspace)
        content.setContentsMargins(28, 28, 28, 28)
        content.setSpacing(22)

        left = QFrame()
        left.setObjectName("flowCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(22, 22, 22, 22)
        left_layout.setSpacing(14)
        videos_title = QLabel("TUS VIDEOS")
        videos_title.setObjectName("eyebrow")
        left_layout.addWidget(videos_title)
        self.queue = QListWidget()
        self.queue.setObjectName("queue")
        self.queue.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.queue, 1)
        self.drop = DropCard()
        self.drop.files_dropped.connect(self._choose_or_add)
        left_layout.addWidget(self.drop)
        self.clear_button = QPushButton("Limpiar lista")
        self.clear_button.setObjectName("ghostButton")
        self.clear_button.clicked.connect(self._clear)
        left_layout.addWidget(self.clear_button)
        content.addWidget(left, 1)

        middle = QFrame()
        middle.setObjectName("flowCard")
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(24, 24, 24, 24)
        middle_layout.setSpacing(18)
        middle_layout.addStretch()
        fps_icon = QLabel("AUTO")
        fps_icon.setObjectName("flowIcon")
        fps_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fps_value = fps_icon
        middle_layout.addWidget(self.fps_value)
        fps_label = QLabel("Elegí los FPS de destino")
        fps_label.setObjectName("statusTitle")
        fps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        middle_layout.addWidget(fps_label)
        self.fps_combo = QComboBox()
        self.fps_combo.addItem("Automático · recomendado", None)
        self.fps_combo.addItem("60 FPS", 60.0)
        self.fps_combo.addItem("120 FPS", 120.0)
        self.fps_combo.addItem("240 FPS", 240.0)
        saved_fps = config.CONFIG.get("default_target_fps", "auto")
        fps_index = 0 if saved_fps == "auto" else self.fps_combo.findData(float(saved_fps))
        self.fps_combo.setCurrentIndex(max(0, fps_index))
        self.fps_combo.currentIndexChanged.connect(self._update_fps_value)
        self._update_fps_value()
        self.fps_combo.setMinimumHeight(50)
        middle_layout.addWidget(self.fps_combo)
        self.start_button = QPushButton("✦  Mejorar videos")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumHeight(55)
        self.start_button.clicked.connect(self._start)
        middle_layout.addWidget(self.start_button)
        middle_layout.addStretch()
        content.addWidget(middle, 1)

        right = QFrame()
        right.setObjectName("flowCard")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 18, 22, 22)
        right_layout.setSpacing(10)
        self.magic = MagicCanvas()
        right_layout.addWidget(self.magic)
        self.status_title = QLabel("Esperando un video")
        self.status_title.setObjectName("statusTitle")
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail = QLabel("Arrastrá algo increíble para empezar")
        self.status_detail.setObjectName("muted")
        self.status_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail.setWordWrap(True)
        right_layout.addWidget(self.status_title)
        right_layout.addWidget(self.status_detail)
        right_layout.addStretch()
        self.open_button = QPushButton("Abrir carpeta de resultados")
        self.open_button.setObjectName("ghostButton")
        self.open_button.setVisible(False)
        self.open_button.clicked.connect(self._open_results)
        right_layout.addWidget(self.open_button)
        content.addWidget(right, 1)
        outer.addWidget(workspace, 1)

    def _build_onboarding(self):
        page = QWidget()
        page.setObjectName("root")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(64, 42, 64, 48)
        header = QHBoxLayout()
        brand = QLabel("Locally<span style='color:#a78bfa'>FPS</span>")
        brand.setObjectName("brand")
        brand.setTextFormat(Qt.TextFormat.RichText)
        badge = QLabel("4.0  BETA")
        badge.setObjectName("beta")
        header.addWidget(brand)
        header.addWidget(badge)
        header.addStretch()
        outer.addLayout(header)
        outer.addStretch()

        card = QFrame()
        card.setObjectName("setupCard")
        card.setMaximumWidth(760)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(54, 42, 54, 42)
        card_layout.setSpacing(18)
        self.setup_steps = QLabel("1  ●────────○  2")
        self.setup_steps.setObjectName("steps")
        self.setup_steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.setup_steps)
        self.setup_title = QLabel("Hagamos que LocallyFPS se sienta tuyo")
        self.setup_title.setObjectName("setupTitle")
        self.setup_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.setup_title)
        self.setup_subtitle = QLabel("Elegí el idioma de la aplicación. Podés cambiarlo cuando quieras desde Configuración.")
        self.setup_subtitle.setObjectName("subtitle")
        self.setup_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setup_subtitle.setWordWrap(True)
        card_layout.addWidget(self.setup_subtitle)
        self.setup_content = QStackedWidget()
        language_page = QWidget()
        language_layout = QVBoxLayout(language_page)
        language_layout.setContentsMargins(45, 10, 45, 0)
        self.language_combo = QComboBox()
        for name, code in LANGUAGES:
            self.language_combo.addItem(name, code)
        language = config.CONFIG.get("language", paths.DEFAULT_LANGUAGE)
        if not paths.CONFIG_PATH.exists() or not config.CONFIG.get("onboarding_complete"):
            locale_language = QLocale.system().name().split("_")[0]
            if locale_language in {code for _, code in LANGUAGES}:
                language = locale_language
        current = self.language_combo.findData(language)
        self.language_combo.setCurrentIndex(max(0, current))
        self.language_combo.setMinimumHeight(52)
        language_layout.addWidget(self.language_combo)
        language_layout.addStretch()
        self.setup_content.addWidget(language_page)

        dependency_page = QWidget()
        dependency_layout = QVBoxLayout(dependency_page)
        dependency_layout.setContentsMargins(20, 8, 20, 0)
        dependency_layout.setSpacing(12)
        self.setup_component = QLabel("Listo para comprobar tu equipo")
        self.setup_component.setObjectName("statusTitle")
        self.setup_component.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dependency_layout.addWidget(self.setup_component)
        self.setup_progress = QProgressBar()
        self.setup_progress.setRange(0, 100)
        self.setup_progress.setValue(0)
        self.setup_progress.setTextVisible(False)
        dependency_layout.addWidget(self.setup_progress)
        self.setup_detail = QLabel("FFmpeg · Motor de IA · Modelo RIFE")
        self.setup_detail.setObjectName("muted")
        self.setup_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setup_detail.setWordWrap(True)
        dependency_layout.addWidget(self.setup_detail)
        dependency_layout.addStretch()
        self.setup_content.addWidget(dependency_page)
        card_layout.addWidget(self.setup_content, 1)
        self.setup_button = QPushButton("Continuar  →")
        self.setup_button.setObjectName("primaryButton")
        self.setup_button.setMinimumHeight(54)
        self.setup_button.clicked.connect(self._advance_setup)
        card_layout.addWidget(self.setup_button)
        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(card, 1)
        centered.addStretch()
        outer.addLayout(centered, 4)
        outer.addStretch()
        return page

    def _advance_setup(self):
        if self.setup_content.currentIndex() == 0:
            config.CONFIG["language"] = self.language_combo.currentData()
            config.save_config()
            self.setup_content.setCurrentIndex(1)
            self.setup_steps.setText("1  ●────────●  2")
            self.setup_title.setText("Preparando la magia")
            self.setup_subtitle.setText("Descargaremos y verificaremos los componentes necesarios. Esto ocurre una sola vez.")
            self.setup_button.setText("Preparar LocallyFPS")
            return
        if self.setup_thread and self.setup_thread.isRunning():
            return
        if self.setup_progress.value() == 100:
            self.pages.setCurrentWidget(self.main_page)
            return
        self._run_setup()

    def _run_setup(self):
        self.setup_button.setEnabled(False)
        self.setup_button.setText("Preparando…")
        self.setup_progress.setValue(1)
        self.setup_thread = QThread(self)
        self.setup_worker = SetupWorker()
        self.setup_worker.moveToThread(self.setup_thread)
        self.setup_thread.started.connect(self.setup_worker.run)
        self.setup_worker.progress.connect(self._on_setup_progress)
        self.setup_worker.finished.connect(self._on_setup_finished)
        self.setup_worker.finished.connect(self.setup_thread.quit)
        self.setup_thread.finished.connect(self.setup_worker.deleteLater)
        self.setup_thread.finished.connect(self.setup_thread.deleteLater)
        self.setup_thread.start()

    @Slot(int, str, str)
    def _on_setup_progress(self, value, label, component):
        self.setup_progress.setValue(value)
        self.setup_component.setText(label)
        self.setup_detail.setText(component)

    @Slot(bool, str)
    def _on_setup_finished(self, ok, error):
        self.setup_button.setEnabled(True)
        if ok:
            config.CONFIG["onboarding_complete"] = True
            config.save_config()
            self.setup_progress.setValue(100)
            self.setup_title.setText("Todo listo para crear fluidez")
            self.setup_subtitle.setText("Tu equipo está preparado. LocallyFPS elegirá automáticamente la opción más segura para cada video.")
            self.setup_component.setText("✓  Componentes verificados")
            self.setup_detail.setText("No necesitás configurar nada más")
            self.setup_button.setText("Empezar  ✦")
        else:
            self.setup_title.setText("Necesitamos un intento más")
            self.setup_component.setText("No se pudo completar la preparación")
            self.setup_detail.setText(error)
            self.setup_button.setText("Reintentar")
        self.setup_worker = None
        self.setup_thread = None

    @Slot(list)
    def _choose_or_add(self, paths_from_drop):
        if not paths_from_drop:
            paths_from_drop, _ = QFileDialog.getOpenFileNames(
                self, "Elegí tus videos", str(Path.home() / "Videos"),
                "Videos (*.mp4 *.m4v *.mkv *.avi *.mov *.webm *.flv *.wmv *.mpg *.mpeg *.ts *.mts *.m2ts *.ogv *.3gp *.vob)",
            )
        added = 0
        for raw in paths_from_drop:
            path = Path(raw).expanduser().resolve()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and path not in self.video_paths:
                self.video_paths.append(path)
                item = QListWidgetItem(f"  ◇  {path.name}")
                item.setToolTip(str(path))
                self.queue.addItem(item)
                added += 1
        if added:
            count = len(self.video_paths)
            self.status_title.setText(f"{count} video{'s' if count != 1 else ''} listo{'s' if count != 1 else ''}")
            self.status_detail.setText("Todo preparado para mejorar el movimiento")
            self.start_button.setEnabled(True)

    def _clear(self):
        if self.thread and self.thread.isRunning():
            return
        self.video_paths.clear()
        self.queue.clear()
        self.magic.set_progress(0)
        self.status_title.setText("Esperando un video")
        self.status_detail.setText("Arrastrá algo increíble para empezar")
        self.open_button.setVisible(False)

    def _start(self):
        if not self.video_paths or (self.thread and self.thread.isRunning()):
            return
        self.output_paths = []
        self.start_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.fps_combo.setEnabled(False)
        self.open_button.setVisible(False)
        self.magic.set_progress(0)
        self.magic.set_active(True)
        self.status_title.setText("Despertando la magia…")
        self.status_detail.setText("Preparando el motor de interpolación")

        self.thread = QThread(self)
        self.worker = EnhanceWorker(self.video_paths, self.fps_combo.currentData())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.item_finished.connect(self._on_item_finished)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(float, str, str)
    def _on_progress(self, progress, label, filename):
        self.magic.set_progress(progress)
        self.status_title.setText(label or "Trabajando…")
        self.status_detail.setText(filename or "LocallyFPS está preparando todo")

    @Slot(str, bool, str)
    def _on_item_finished(self, video, ok, detail):
        target = Path(video)
        for index, queued in enumerate(self.video_paths):
            if queued == target:
                prefix = "✓" if ok else "!"
                self.queue.item(index).setText(f"  {prefix}  {queued.name}")
                break
        if ok:
            self.output_paths.append(detail)

    @Slot(list, list)
    def _on_finished(self, completed, failed):
        self.magic.set_active(False)
        self.start_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.fps_combo.setEnabled(True)
        if completed and not failed:
            self.magic.set_progress(1)
            self.status_title.setText("La magia está lista ✦")
            self.status_detail.setText(f"{len(completed)} video{'s' if len(completed) != 1 else ''} mejorado{'s' if len(completed) != 1 else ''} correctamente")
            self.open_button.setVisible(True)
        elif completed:
            self.status_title.setText("Proceso terminado con avisos")
            self.status_detail.setText(f"{len(completed)} completados · {len(failed)} con error")
            self.open_button.setVisible(True)
        else:
            self.status_title.setText("No se pudo completar")
            message = failed[-1][1] if failed else "Error desconocido"
            self.status_detail.setText(message)
            QMessageBox.warning(self, "LocallyFPS", message)
        self.worker = None
        self.thread = None

    def _open_results(self):
        directory = Path(self.output_paths[-1]).parent if self.output_paths else paths.VIDEOS_DIR / "enhanced"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _update_fps_value(self, *_args):
        value = self.fps_combo.currentData()
        self.fps_value.setText("AUTO" if value is None else str(int(value)))

    def _show_settings(self):
        dialog = SettingsDialog(self)
        dialog.repair_requested.connect(self._show_repair)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved_fps = config.CONFIG.get("default_target_fps", "auto")
            index = 0 if saved_fps == "auto" else self.fps_combo.findData(float(saved_fps))
            self.fps_combo.setCurrentIndex(max(0, index))

    def _show_repair(self):
        self.pages.setCurrentWidget(self.onboarding_page)
        self.setup_content.setCurrentIndex(1)
        self.setup_steps.setText("COMPROBACIÓN DEL MOTOR")
        self.setup_title.setText("Comprobando la magia")
        self.setup_subtitle.setText("Verificaremos los componentes y repararemos automáticamente lo que falte.")
        self.setup_progress.setValue(0)
        self.setup_button.setText("Comprobar ahora")

    def _theme_notice(self):
        QMessageBox.information(self, "Apariencia", "El modo oscuro es el diseño de esta beta. El modo del sistema llegará durante la v4.")

    def closeEvent(self, event):
        if ((self.thread and self.thread.isRunning()) or
                (self.setup_thread and self.setup_thread.isRunning())):
            QMessageBox.information(
                self, "LocallyFPS está trabajando",
                "Esperá a que termine el video actual antes de cerrar la aplicación.",
            )
            event.ignore()
            return
        event.accept()


STYLE = """
QWidget#root { background: #080b16; color: #f8fafc; }
QStackedWidget#root { background: #080b16; }
QWidget { font-family: Inter, "Segoe UI", sans-serif; font-size: 14px; }
QLabel { color: #eef2f7; }
QDialog#settingsDialog { background: #090c16; color: #f8fafc; }
QLabel#brand { font-size: 27px; font-weight: 800; color: #f8fafc; }
QLabel#beta { color: #c4b5fd; background: rgba(139,92,246,0.18); border: 1px solid rgba(167,139,250,0.36); border-radius: 10px; padding: 4px 9px; font-size: 10px; font-weight: 700; }
QLabel#headline { font-size: 28px; font-weight: 750; color: #ffffff; }
QLabel#subtitle { color: #9aa5ba; font-size: 14px; line-height: 1.4; }
QLabel#muted { color: #7f8aa3; font-size: 12px; }
QLabel#fieldLabel, QLabel#eyebrow { color: #98a3ba; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#statusTitle { color: #f8fafc; font-size: 18px; font-weight: 700; }
QLabel#setupTitle { color: #ffffff; font-size: 26px; font-weight: 750; }
QLabel#steps { color: #a78bfa; font-size: 13px; font-weight: 700; letter-spacing: 2px; }
QFrame#panel { background: rgba(17,22,40,0.94); border: 1px solid #202943; border-radius: 22px; }
QFrame#workspace { background: #202431; border: 1px solid #303647; border-radius: 25px; }
QFrame#flowCard { background: #343947; border: 1px solid #424858; border-radius: 20px; }
QFrame#setupCard { background: #111628; border: 1px solid #29324c; border-radius: 26px; }
QFrame#settingsSection { background: #111628; border: 1px solid #252e47; border-radius: 16px; }
QFrame#dropCard { background: rgba(11,15,30,0.72); border: 1px dashed #475375; border-radius: 18px; }
QFrame#dropCard:hover, QFrame#dropCard[dragging="true"] { background: rgba(92,63,180,0.16); border: 1px solid #8b5cf6; }
QLabel#dropIcon { color: #a78bfa; font-size: 38px; }
QLabel#dropTitle { color: #eef2ff; font-size: 17px; font-weight: 700; }
QLabel#flowIcon { color: #f8fafc; font-size: 42px; font-weight: 500; }
QComboBox { color: #eef2ff; background: #0d1325; border: 1px solid #2a3555; border-radius: 11px; padding: 10px 14px; min-height: 20px; }
QComboBox:hover { border-color: #7255cc; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView { color: #eef2ff; background: #10172a; selection-background-color: #6d4dd1; border: 1px solid #2a3555; }
QPushButton { border: 0; border-radius: 12px; padding: 10px 16px; font-weight: 650; }
QPushButton#primaryButton { color: white; background: #7652df; font-size: 15px; }
QPushButton#primaryButton:hover { background: #8968ea; }
QPushButton#primaryButton:pressed { background: #6342c5; }
QPushButton#primaryButton:disabled { color: #727b91; background: #252b3c; }
QPushButton#ghostButton { color: #b9c2d6; background: #151c31; border: 1px solid #293451; }
QPushButton#ghostButton:hover { color: white; border-color: #6650ae; background: #1b2340; }
QPushButton#iconButton { color: #f8fafc; background: transparent; font-size: 27px; padding: 5px; min-width: 42px; }
QPushButton#iconButton:hover { color: #c4b5fd; background: #171b29; }
QLineEdit { color: #eef2ff; background: #0d1325; border: 1px solid #2a3555; border-radius: 10px; padding: 10px 12px; }
QLineEdit:focus { border-color: #8060dc; }
QProgressBar { background: #090d19; border: 1px solid #28324e; border-radius: 7px; height: 13px; }
QProgressBar::chunk { background: #8059e8; border-radius: 6px; }
QListWidget#queue { color: #cbd5e1; background: transparent; border: 0; outline: 0; }
QListWidget#queue::item { background: #0e1426; border: 1px solid #202a45; border-radius: 9px; margin: 3px 0; padding: 9px 5px; }
QListWidget#queue::item:selected { background: #18213a; color: white; border-color: #554399; }
QScrollBar:vertical { background: transparent; width: 7px; }
QScrollBar::handle:vertical { background: #33405f; border-radius: 3px; min-height: 22px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--network-smoke-test", action="store_true")
    args, qt_args = parser.parse_known_args(argv)
    if args.network_smoke_test:
        from core.network import open_url
        with open_url("https://api.github.com/zen", timeout=15) as response:
            if not response.read(256):
                return 1
        return 0
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("LocallyFPS")
    app.setApplicationDisplayName("LocallyFPS")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    paths.ensure_dirs()
    config.load_config()
    icon = paths.RESOURCE_DIR / "packaging" / "locallyfps.svg"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    if args.smoke_test:
        QTimer.singleShot(250, app.quit)
    return app.exec()
