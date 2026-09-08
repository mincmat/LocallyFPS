import argparse
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QThread, QTimer, QUrl, Signal, Slot, QLocale
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPainterPath,
    QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget, QLineEdit,
    QProgressBar, QDialog, QDoubleSpinBox, QGraphicsBlurEffect,
    QGraphicsPixmapItem, QGraphicsScene,
)

from core import paths
from core import config
from core.cancel import OperationCancelled


SUPPORTED_EXTENSIONS = {
    ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".ogv", ".3gp", ".vob",
}

LANGUAGES = [
    ("Español", "es"), ("English", "en"), ("Português", "pt"),
    ("Français", "fr"), ("Deutsch", "de"), ("中文", "zh"),
    ("日本語", "ja"), ("한국어", "ko"), ("Русский", "ru"), ("العربية", "ar"),
]

GUI_TEXT = {
    "en": {
        "videos": "YOUR VIDEOS", "drop": "Add or drop videos here",
        "drop_hint": "click to select · MP4, MKV, MOV, WebM and more",
        "clear": "Clear list", "fps": "Set the target FPS", "custom": "Custom…",
        "enhance": "Enhance videos", "stop": "Stop", "waiting": "Waiting for a video",
        "waiting_detail": "Add one or more videos to begin", "open": "Open output folder",
        "settings": "Settings", "settings_sub": "Application preferences",
        "language": "Language", "language_hint": "Preview the change, then save it",
        "default_fps": "Default FPS", "default_fps_hint": "Used when the application starts",
        "appearance": "Appearance", "output": "Output folder", "choose": "Choose",
        "engine": "Interpolation engine", "engine_hint": "Check FFmpeg, RIFE and the model",
        "check": "Check", "reset": "Reset and maintenance", "cancel": "Cancel",
        "save": "Save changes", "continue": "Continue", "prepare": "Prepare LocallyFPS",
        "setup_title": "Initial setup", "setup_language": "Choose the application language.",
        "setup_engine": "Required components", "setup_engine_hint": "FFmpeg, RIFE and the model will be checked before continuing.",
        "ready": "Setup complete", "ready_hint": "Required components are installed.",
        "retry": "Retry", "start": "Open LocallyFPS", "stopped": "Process stopped",
        "stopped_detail": "Temporary files were removed", "working": "Processing…",
        "stopping": "Stopping…", "stopping_detail": "Closing processes and removing temporary files",
        "light": "Light", "dark": "Dark", "select_videos": "Select videos",
        "queued_one": "1 video ready", "queued_many": "{count} videos ready",
        "queued_detail": "Select the target FPS and start processing", "preparing": "Preparing the interpolation engine",
        "queue": "NEXT IN QUEUE", "queue_empty": "There are no more videos in the queue",
        "remove_selected": "Remove selected", "remove_queue": "Remove from queue",
        "complete": "Completed", "complete_one": "1 video processed successfully",
        "complete_many": "{count} videos processed successfully", "warnings": "Completed with warnings",
        "failed": "Could not complete", "unknown_error": "Unknown error", "working_close": "LocallyFPS is working",
        "working_close_detail": "Stop the current process before closing the application.",
        "maintenance_safe": "Exported videos will not be deleted.", "reset_settings": "Reset settings",
        "reinstall_dependencies": "Reinstall dependencies", "clear_cache": "Clear temporary cache",
        "maintenance_confirm": "Do you want to continue?", "maintenance_done": "Maintenance completed",
        "dependencies_removed": "Dependencies were removed. They will be installed again now.",
        "settings_reset": "Settings were reset.", "cache_cleared": "Temporary cache was cleared.",
        "checking": "Checking components", "checking_hint": "Missing or damaged components will be installed again.",
        "check_now": "Check now", "setup_check_ready": "Ready to check required components",
        "setup_preparing": "Preparing…", "components_verified": "Components verified",
        "setup_failed": "Setup could not be completed", "appearance_cycle": "Change appearance",
    },
    "es": {
        "videos": "TUS VIDEOS", "drop": "Añadí o soltá videos acá",
        "drop_hint": "hacé clic para elegir · MP4, MKV, MOV, WebM y más",
        "clear": "Limpiar lista", "fps": "Elegí los FPS de destino", "custom": "Personalizado…",
        "enhance": "Mejorar videos", "stop": "Detener", "waiting": "Esperando un video",
        "waiting_detail": "Añadí uno o más videos para comenzar", "open": "Abrir carpeta de salida",
        "settings": "Configuración", "settings_sub": "Preferencias de la aplicación",
        "language": "Idioma", "language_hint": "Vista previa del cambio; guardalo para aplicarlo",
        "default_fps": "FPS predeterminados", "default_fps_hint": "Se usan al iniciar la aplicación",
        "appearance": "Apariencia", "output": "Carpeta de salida", "choose": "Elegir",
        "engine": "Motor de interpolación", "engine_hint": "Comprobar FFmpeg, RIFE y el modelo",
        "check": "Comprobar", "reset": "Restablecer y mantenimiento", "cancel": "Cancelar",
        "save": "Guardar cambios", "continue": "Continuar", "prepare": "Preparar LocallyFPS",
        "setup_title": "Configuración inicial", "setup_language": "Elegí el idioma de la aplicación.",
        "setup_engine": "Componentes necesarios", "setup_engine_hint": "Se comprobarán FFmpeg, RIFE y el modelo antes de continuar.",
        "ready": "Configuración completada", "ready_hint": "Los componentes necesarios están instalados.",
        "retry": "Reintentar", "start": "Abrir LocallyFPS", "stopped": "Proceso detenido",
        "stopped_detail": "Se eliminaron los archivos temporales", "working": "Procesando…",
        "stopping": "Deteniendo…", "stopping_detail": "Cerrando procesos y eliminando archivos temporales",
        "light": "Claro", "dark": "Oscuro", "select_videos": "Elegir videos",
        "queued_one": "1 video listo", "queued_many": "{count} videos listos",
        "queued_detail": "Elegí los FPS de destino e iniciá el proceso", "preparing": "Preparando el motor de interpolación",
        "queue": "SIGUEN EN COLA", "queue_empty": "No quedan más videos en la cola",
        "remove_selected": "Quitar seleccionado", "remove_queue": "Quitar de la cola",
        "complete": "Completado", "complete_one": "1 video procesado correctamente",
        "complete_many": "{count} videos procesados correctamente", "warnings": "Proceso terminado con avisos",
        "failed": "No se pudo completar", "unknown_error": "Error desconocido", "working_close": "LocallyFPS está trabajando",
        "working_close_detail": "Detené el proceso actual antes de cerrar la aplicación.",
        "maintenance_safe": "Los videos exportados no se eliminarán.", "reset_settings": "Restablecer configuración",
        "reinstall_dependencies": "Reinstalar dependencias", "clear_cache": "Borrar caché temporal",
        "maintenance_confirm": "¿Querés continuar?", "maintenance_done": "Mantenimiento completado",
        "dependencies_removed": "Se eliminaron las dependencias. Ahora se instalarán nuevamente.",
        "settings_reset": "Se restableció la configuración.", "cache_cleared": "Se borró la caché temporal.",
        "checking": "Comprobando componentes", "checking_hint": "Se instalarán nuevamente los componentes faltantes o dañados.",
        "check_now": "Comprobar ahora", "setup_check_ready": "Listo para comprobar los componentes necesarios",
        "setup_preparing": "Preparando…", "components_verified": "Componentes verificados",
        "setup_failed": "No se pudo completar la preparación", "appearance_cycle": "Cambiar apariencia",
    },
}


def tr(key):
    language = config.CONFIG.get("language", "en")
    return GUI_TEXT.get(language, GUI_TEXT["en"]).get(key, key)


def format_fps(value):
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0").rstrip(".")


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
    maintenance_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        # Settings are previewed live, but must never escape this dialog until
        # the user explicitly saves them.
        self._original_language = config.CONFIG.get("language", "en")
        self._original_theme = config.CONFIG.get("theme", "dark")
        self.setMinimumSize(780, 760)
        self.setObjectName("settingsDialog")
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 28, 34, 28)
        root.setSpacing(14)
        self.title = QLabel()
        self.title.setObjectName("headline")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("subtitle")
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        general = QFrame()
        general.setObjectName("settingsSection")
        form = QVBoxLayout(general)
        form.setContentsMargins(24, 18, 24, 18)
        form.setSpacing(10)
        self.general_section = QLabel("GENERAL")
        self.general_section.setObjectName("eyebrow")
        form.addWidget(self.general_section)
        self.language, self.language_title, self.language_hint = self._row_combo(
            form, LANGUAGES, config.CONFIG.get("language", "en"),
        )
        saved = config.CONFIG.get("default_target_fps", "60")
        selected = saved if saved in {"60", "120", "240"} else "custom"
        fps_values = [("60 FPS", "60"), ("120 FPS", "120"), ("240 FPS", "240"), (tr("custom"), "custom")]
        self.default_fps, self.fps_title, self.fps_hint = self._row_combo(form, fps_values, selected)
        self.custom_fps = QDoubleSpinBox()
        self.custom_fps.setRange(1, 1000)
        self.custom_fps.setDecimals(3)
        self.custom_fps.setValue(max(1, min(1000, float(saved))))
        self.custom_fps.setSuffix(" FPS")
        self.custom_fps.setVisible(selected == "custom")
        form.addWidget(self.custom_fps)
        theme_values = [(tr("dark"), "dark"), (tr("light"), "light")]
        self.theme, self.theme_title, self.theme_hint = self._row_combo(
            form, theme_values, config.CONFIG.get("theme", "dark"),
        )
        root.addWidget(general)

        output = QFrame()
        output.setObjectName("settingsSection")
        output_layout = QVBoxLayout(output)
        output_layout.setContentsMargins(24, 18, 24, 18)
        self.output_section = QLabel("RESULTS")
        self.output_section.setObjectName("eyebrow")
        output_layout.addWidget(self.output_section)
        output_row = QHBoxLayout()
        self.output_title = QLabel()
        output_row.addWidget(self.output_title)
        self.output_path = QLineEdit(
            config.CONFIG.get("output_directory") or str(paths.DOWNLOADS_DIR / "interpoled_locallyfps")
        )
        output_row.addWidget(self.output_path, 1)
        self.choose_button = QPushButton()
        self.choose_button.setObjectName("ghostButton")
        self.choose_button.clicked.connect(self._choose_output)
        output_row.addWidget(self.choose_button)
        output_layout.addLayout(output_row)
        root.addWidget(output)

        engine = QFrame()
        engine.setObjectName("settingsSection")
        engine_layout = QHBoxLayout(engine)
        engine_layout.setContentsMargins(24, 18, 24, 18)
        engine_text = QVBoxLayout()
        self.engine_title = QLabel()
        self.engine_hint = QLabel()
        self.engine_hint.setObjectName("muted")
        engine_text.addWidget(self.engine_title)
        engine_text.addWidget(self.engine_hint)
        engine_layout.addLayout(engine_text)
        engine_layout.addStretch()
        self.repair = QPushButton()
        self.repair.setObjectName("ghostButton")
        self.repair.clicked.connect(self._repair)
        engine_layout.addWidget(self.repair)
        root.addWidget(engine)
        self.maintenance = QPushButton()
        self.maintenance.setObjectName("ghostButton")
        self.maintenance.clicked.connect(self._show_maintenance)
        root.addWidget(self.maintenance)
        root.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("ghostButton")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton()
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)

        self.language.currentIndexChanged.connect(self._language_changed)
        self.default_fps.currentIndexChanged.connect(
            lambda: self.custom_fps.setVisible(self.default_fps.currentData() == "custom")
        )
        self.theme.currentIndexChanged.connect(self._theme_changed)
        self.apply_language()

    def _row_combo(self, layout, values, selected):
        row = QHBoxLayout()
        labels = QVBoxLayout()
        title = QLabel()
        hint = QLabel()
        hint.setObjectName("muted")
        labels.addWidget(title)
        labels.addWidget(hint)
        row.addLayout(labels)
        row.addStretch()
        combo = QComboBox()
        for name, value in values:
            combo.addItem(name, value)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        combo.setMinimumWidth(230)
        row.addWidget(combo)
        layout.addLayout(row)
        return combo, title, hint

    def apply_language(self):
        self.setWindowTitle(f"{tr('settings')} · LocallyFPS")
        self.title.setText(tr("settings"))
        self.subtitle.setText(tr("settings_sub"))
        self.language_title.setText(tr("language"))
        self.language_hint.setText(tr("language_hint"))
        self.fps_title.setText(tr("default_fps"))
        self.fps_hint.setText(tr("default_fps_hint"))
        self.theme_title.setText(tr("appearance"))
        self.theme_hint.setText("Claro / Oscuro" if config.CONFIG.get("language") == "es" else "Light / Dark")
        self.output_title.setText(tr("output"))
        self.choose_button.setText(tr("choose"))
        self.engine_title.setText(tr("engine"))
        self.engine_hint.setText(tr("engine_hint"))
        self.repair.setText(tr("check"))
        self.maintenance.setText(tr("reset"))
        self.cancel_button.setText(tr("cancel"))
        self.save_button.setText(tr("save"))
        self.default_fps.setItemText(3, tr("custom"))
        self.theme.setItemText(0, tr("dark"))
        self.theme.setItemText(1, tr("light"))
        self.output_section.setText("RESULTADOS" if config.CONFIG.get("language") == "es" else "RESULTS")

    def _language_changed(self):
        config.CONFIG["language"] = self.language.currentData()
        if self.parent():
            self.parent().apply_language()
        self.apply_language()

    def _theme_changed(self):
        config.CONFIG["theme"] = self.theme.currentData()
        apply_theme(QApplication.instance())
        if self.parent():
            self.parent()._update_theme_button()

    def _restore_preview_settings(self):
        config.CONFIG["language"] = self._original_language
        config.CONFIG["theme"] = self._original_theme
        apply_theme(QApplication.instance())
        if self.parent():
            self.parent().apply_language()

    def reject(self):
        self._restore_preview_settings()
        super().reject()

    def _choose_output(self):
        selected = QFileDialog.getExistingDirectory(self, tr("output"), self.output_path.text())
        if selected:
            self.output_path.setText(selected)

    def _show_maintenance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("reset"))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        hint = QLabel(tr("maintenance_safe"))
        hint.setObjectName("muted")
        layout.addWidget(hint)
        actions = [
            (tr("reset_settings"), "settings"),
            (tr("reinstall_dependencies"), "dependencies"),
            (tr("clear_cache"), "cache"),
        ]
        for label, action in actions:
            button = QPushButton(label)
            button.setObjectName("ghostButton")
            button.clicked.connect(lambda _checked=False, value=action: self._maintenance_choice(dialog, value))
            layout.addWidget(button)
        dialog.exec()

    def _maintenance_choice(self, dialog, action):
        dialog.accept()
        self.reject()
        self.maintenance_requested.emit(action)

    def _repair(self):
        self.reject()
        self.repair_requested.emit()

    def _save(self):
        value = self.custom_fps.value() if self.default_fps.currentData() == "custom" else int(self.default_fps.currentData())
        config.CONFIG["default_target_fps"] = format_fps(value)
        config.CONFIG["theme"] = self.theme.currentData()
        config.CONFIG["output_directory"] = self.output_path.text().strip()
        config.save_config()
        self.accept()


class MagicCanvas(QWidget):
    """A blurred preview of the video currently being processed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._progress = 0.0
        self._active = False
        self._preview = None
        self._blurred_preview = None
        self._aspect_ratio = 16 / 9

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(160, min(360, round(width / self._aspect_ratio)))

    def sizeHint(self):
        return QSize(360, self.heightForWidth(360))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        desired_height = self.heightForWidth(max(1, event.size().width()))
        if self.minimumHeight() != desired_height:
            self.setFixedHeight(desired_height)

    def set_progress(self, value):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def set_active(self, active):
        self._active = bool(active)
        self.update()

    @Slot(object)
    def set_preview(self, image):
        self._preview = image if isinstance(image, QImage) and not image.isNull() else None
        self._blurred_preview = self._blur_image(self._preview) if self._preview is not None else None
        if self._preview is not None:
            self._aspect_ratio = self._preview.width() / max(1, self._preview.height())
            self.setFixedHeight(self.heightForWidth(max(1, self.width())))
        self.updateGeometry()
        self.update()

    def clear_preview(self):
        self._preview = None
        self._blurred_preview = None
        self._aspect_ratio = 16 / 9
        self.setFixedHeight(self.heightForWidth(max(1, self.width())))
        self.updateGeometry()
        self.update()

    @staticmethod
    def _blur_image(image):
        """Render Qt's high-quality Gaussian blur once per video preview."""
        pixmap = QPixmap.fromImage(image)
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(pixmap)
        effect = QGraphicsBlurEffect()
        effect.setBlurRadius(14)
        effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        item.setGraphicsEffect(effect)
        scene.addItem(item)
        source = effect.boundingRectFor(QRectF(pixmap.rect()))
        result = QImage(source.size().toSize(), QImage.Format.Format_ARGB32_Premultiplied)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        scene.render(painter, QRectF(result.rect()), source)
        painter.end()
        return result

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        dark = _effective_theme(QApplication.instance()) == "dark"
        frame = self.rect().adjusted(1, 1, -1, -1)
        rounded = QPainterPath()
        rounded.addRoundedRect(QRectF(frame), 18, 18)
        painter.setClipPath(rounded)
        painter.fillRect(frame, QColor("#1f1f1f") if dark else QColor("#dedede"))
        if self._blurred_preview is not None:
            blurred = self._blurred_preview.scaled(
                frame.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawImage(
                frame.center().x() - blurred.width() // 2,
                frame.center().y() - blurred.height() // 2,
                blurred,
            )
            painter.fillRect(frame, QColor(0, 0, 0, 92))

        percent_rect = frame
        shadow = QColor(0, 0, 0, 175)
        font = QFont("Sans Serif", 31, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(shadow)
        painter.drawText(percent_rect.translated(1, 2), Qt.AlignmentFlag.AlignCenter, f"{round(self._progress * 100)}%")
        painter.setPen(QColor("#ffffff"))
        painter.drawText(percent_rect, Qt.AlignmentFlag.AlignCenter, f"{round(self._progress * 100)}%")
        painter.setClipping(False)
        border = QColor("#555555") if dark else QColor("#bdbdbd")
        painter.setPen(QPen(border, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(rounded)


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
        self.icon = QLabel("+")
        self.icon.setObjectName("dropIcon")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName("dropTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        self.apply_language()

    def apply_language(self):
        self.title.setText(tr("drop"))
        self.hint.setText(tr("drop_hint"))

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
    preview_ready = Signal(object)
    item_finished = Signal(str, bool, str)
    finished = Signal(list, list)
    cancelled = Signal(list)

    def __init__(self, videos, target_fps):
        super().__init__()
        self.videos = [Path(video) for video in videos]
        self.target_fps = target_fps
        self.cancel_event = threading.Event()
        self._skip_lock = threading.Lock()
        self._skipped_videos = set()

    @Slot()
    def request_stop(self):
        self.cancel_event.set()

    def skip_video(self, video):
        """Skip a not-yet-started item without interrupting the current export."""
        with self._skip_lock:
            self._skipped_videos.add(Path(video))

    def _is_skipped(self, video):
        with self._skip_lock:
            return Path(video) in self._skipped_videos

    def _extract_preview(self, video, duration):
        """Return one representative PNG frame without creating a temporary file."""
        from core.cancel import run_cancellable

        seek = min(max(float(duration or 0) * 0.1, 0.0), max(float(duration or 0) - 0.05, 0.0))
        command = [
            str(paths.FFMPEG_BIN), "-hide_banner", "-loglevel", "error",
            "-ss", f"{seek:.3f}", "-i", str(video),
            "-map", "0:v:0", "-frames:v", "1",
            "-vf", "scale=960:540:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "png", "pipe:1",
        ]
        try:
            result = run_cancellable(
                command, cancel_event=self.cancel_event, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if result.returncode != 0 or not result.stdout:
            return None
        image = QImage.fromData(result.stdout, "PNG")
        return image if not image.isNull() else None

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
                    if inner_self.worker.cancel_event.is_set():
                        raise OperationCancelled("Operation cancelled by the user")
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
                if self.cancel_event.is_set():
                    self.cancelled.emit(completed)
                    return
                if self._is_skipped(video):
                    continue
                self.preview_ready.emit(None)
                self.progress.emit(0.1 + 0.9 * index / total, "Leyendo el video…", video.name)
                info = probe_video_file(video)
                if info is None:
                    failed.append((str(video), "Formato de video no reconocido"))
                    self.item_finished.emit(str(video), False, "Formato no reconocido")
                    continue
                preview = self._extract_preview(video, info.get("duration", 0))
                if preview is not None:
                    self.preview_ready.emit(preview)
                target = self.target_fps
                output = unique_output_path(resolve_output_path(
                    config.CONFIG.get("output_directory", ""), video, target,
                ))
                gpu = choose_gpu_settings(
                    info.get("display_width", info["width"]),
                    info.get("display_height", info["height"]),
                )

                def report(fraction, label, *, item=index, name=video.name):
                    if self.cancel_event.is_set():
                        return
                    overall = 0.1 + 0.9 * (item + max(0.0, min(1.0, fraction))) / total
                    self.progress.emit(overall, str(label), name)

                try:
                    ok = run_pipeline(
                        info, target, output, gpu, interactive=False,
                        progress_cb=report,
                        cancel_event=self.cancel_event,
                    )
                except OperationCancelled:
                    self.cancelled.emit(completed)
                    return
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
        except OperationCancelled:
            self.cancelled.emit(completed)
            return
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
        brand = QLabel("LocallyFPS")
        brand.setObjectName("brand")
        beta = QLabel("4.0  BETA")
        beta.setObjectName("beta")
        header.addWidget(brand)
        header.addWidget(beta)
        header.addStretch()
        self.theme_button = QPushButton("☾")
        self.theme_button.setObjectName("iconButton")
        self.theme_button.clicked.connect(self._cycle_theme)
        header.addWidget(self.theme_button)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("iconButton")
        self.settings_button.clicked.connect(self._show_settings)
        header.addWidget(self.settings_button)
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
        self.videos_title = QLabel()
        self.videos_title.setObjectName("eyebrow")
        left_layout.addWidget(self.videos_title)
        self.video_list = QListWidget()
        self.video_list.setObjectName("queue")
        self.video_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_list.itemSelectionChanged.connect(self._update_remove_buttons)
        left_layout.addWidget(self.video_list, 1)
        self.drop = DropCard()
        self.drop.files_dropped.connect(self._choose_or_add)
        left_layout.addWidget(self.drop)
        self.clear_button = QPushButton()
        self.clear_button.setObjectName("ghostButton")
        self.clear_button.clicked.connect(self._clear)
        left_layout.addWidget(self.clear_button)
        self.remove_selected_button = QPushButton()
        self.remove_selected_button.setObjectName("ghostButton")
        self.remove_selected_button.setEnabled(False)
        self.remove_selected_button.clicked.connect(self._remove_selected_videos)
        left_layout.addWidget(self.remove_selected_button)
        content.addWidget(left, 1)

        middle = QFrame()
        middle.setObjectName("flowCard")
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(24, 24, 24, 24)
        middle_layout.setSpacing(18)
        middle_layout.addStretch()
        fps_icon = QLabel("60")
        fps_icon.setObjectName("flowIcon")
        fps_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fps_value = fps_icon
        middle_layout.addWidget(self.fps_value)
        self.fps_label = QLabel()
        self.fps_label.setObjectName("statusTitle")
        self.fps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        middle_layout.addWidget(self.fps_label)
        self.fps_combo = QComboBox()
        self.fps_combo.addItem("60 FPS", 60.0)
        self.fps_combo.addItem("120 FPS", 120.0)
        self.fps_combo.addItem("240 FPS", 240.0)
        self.fps_combo.addItem(tr("custom"), "custom")
        saved_fps = config.CONFIG.get("default_target_fps", "60")
        saved_number = float(saved_fps)
        fps_index = self.fps_combo.findData(saved_number if saved_fps in {"60", "120", "240"} else "custom")
        self.fps_combo.setCurrentIndex(max(0, fps_index))
        self.fps_combo.currentIndexChanged.connect(self._update_fps_value)
        self.fps_combo.setMinimumHeight(50)
        middle_layout.addWidget(self.fps_combo)
        self.custom_fps = QDoubleSpinBox()
        self.custom_fps.setRange(1, 1000)
        self.custom_fps.setDecimals(3)
        self.custom_fps.setValue(max(1, min(1000, saved_number)))
        self.custom_fps.setSuffix(" FPS")
        self.custom_fps.valueChanged.connect(self._update_fps_value)
        middle_layout.addWidget(self.custom_fps)
        self._update_fps_value()
        self.start_button = QPushButton()
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumHeight(55)
        self.start_button.clicked.connect(self._start)
        middle_layout.addWidget(self.start_button)
        self.stop_button = QPushButton()
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setMinimumHeight(48)
        self.stop_button.setVisible(False)
        self.stop_button.setEnabled(True)
        self.stop_button.clicked.connect(self._stop)
        middle_layout.addWidget(self.stop_button)
        middle_layout.addStretch()
        content.addWidget(middle, 1)

        right = QFrame()
        right.setObjectName("flowCard")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 18, 22, 22)
        right_layout.setSpacing(10)
        self.magic = MagicCanvas()
        right_layout.addWidget(self.magic)
        self.status_title = QLabel()
        self.status_title.setObjectName("statusTitle")
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail = QLabel()
        self.status_detail.setObjectName("muted")
        self.status_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail.setWordWrap(True)
        right_layout.addWidget(self.status_title)
        right_layout.addWidget(self.status_detail)
        self.pending_title = QLabel()
        self.pending_title.setObjectName("eyebrow")
        self.pending_title.setVisible(False)
        right_layout.addWidget(self.pending_title)
        self.pending_queue = QListWidget()
        self.pending_queue.setObjectName("queue")
        self.pending_queue.setMinimumHeight(104)
        self.pending_queue.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pending_queue.itemSelectionChanged.connect(self._update_remove_buttons)
        self.pending_queue.setVisible(False)
        right_layout.addWidget(self.pending_queue, 1)
        self.pending_empty = QLabel()
        self.pending_empty.setObjectName("muted")
        self.pending_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_empty.setWordWrap(True)
        self.pending_empty.setVisible(False)
        right_layout.addWidget(self.pending_empty)
        self.remove_queue_button = QPushButton()
        self.remove_queue_button.setObjectName("ghostButton")
        self.remove_queue_button.setEnabled(False)
        self.remove_queue_button.setVisible(False)
        self.remove_queue_button.clicked.connect(self._remove_from_pending_queue)
        right_layout.addWidget(self.remove_queue_button)
        self.open_button = QPushButton()
        self.open_button.setObjectName("ghostButton")
        self.open_button.setVisible(False)
        self.open_button.clicked.connect(self._open_results)
        right_layout.addWidget(self.open_button)
        content.addWidget(right, 1)
        outer.addWidget(workspace, 1)
        self.apply_language()

    def _build_onboarding(self):
        page = QWidget()
        page.setObjectName("root")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(64, 42, 64, 48)
        header = QHBoxLayout()
        brand = QLabel("LocallyFPS")
        brand.setObjectName("brand")
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
        self.setup_title = QLabel()
        self.setup_title.setObjectName("setupTitle")
        self.setup_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.setup_title)
        self.setup_subtitle = QLabel()
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
        self.language_combo.currentIndexChanged.connect(self._on_onboarding_language_changed)
        self.language_combo.setMinimumHeight(52)
        language_layout.addWidget(self.language_combo)
        language_layout.addStretch()
        self.setup_content.addWidget(language_page)

        dependency_page = QWidget()
        dependency_layout = QVBoxLayout(dependency_page)
        dependency_layout.setContentsMargins(20, 8, 20, 0)
        dependency_layout.setSpacing(12)
        self.setup_component = QLabel()
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
        self.setup_button = QPushButton()
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
        self._apply_onboarding_language()
        return page

    def _on_onboarding_language_changed(self):
        config.CONFIG["language"] = self.language_combo.currentData()
        config.save_config()
        self.apply_language()

    def _apply_onboarding_language(self):
        if self.setup_content.currentIndex() == 0:
            self.setup_title.setText(tr("setup_title"))
            self.setup_subtitle.setText(tr("setup_language"))
            self.setup_button.setText(f"{tr('continue')}  →")
            self.setup_component.setText(tr("setup_check_ready"))
        elif self.setup_progress.value() == 100:
            self.setup_title.setText(tr("ready"))
            self.setup_subtitle.setText(tr("ready_hint"))
            self.setup_component.setText(f"✓  {tr('components_verified')}")
            self.setup_button.setText(tr("start"))
        else:
            self.setup_title.setText(tr("setup_engine"))
            self.setup_subtitle.setText(tr("setup_engine_hint"))
            self.setup_button.setText(tr("prepare"))

    def _advance_setup(self):
        if self.setup_content.currentIndex() == 0:
            config.CONFIG["language"] = self.language_combo.currentData()
            config.save_config()
            self.setup_content.setCurrentIndex(1)
            self.setup_steps.setText("1  ●────────●  2")
            self._apply_onboarding_language()
            return
        if self.setup_thread and self.setup_thread.isRunning():
            return
        if self.setup_progress.value() == 100:
            self.pages.setCurrentWidget(self.main_page)
            return
        self._run_setup()

    def _run_setup(self):
        self.setup_button.setEnabled(False)
        self.setup_button.setText(tr("setup_preparing"))
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
            self.setup_title.setText(tr("ready"))
            self.setup_subtitle.setText(tr("ready_hint"))
            self.setup_component.setText(f"✓  {tr('components_verified')}")
            self.setup_detail.setText("FFmpeg · RIFE")
            self.setup_button.setText(tr("start"))
        else:
            self.setup_title.setText(tr("setup_failed"))
            self.setup_component.setText(tr("setup_failed"))
            self.setup_detail.setText(error)
            self.setup_button.setText(tr("retry"))
        self.setup_worker = None
        self.setup_thread = None

    @Slot(list)
    def _choose_or_add(self, paths_from_drop):
        if not paths_from_drop:
            paths_from_drop, _ = QFileDialog.getOpenFileNames(
                self, tr("select_videos"), str(Path.home() / "Videos"),
                "Videos (*.mp4 *.m4v *.mkv *.avi *.mov *.webm *.flv *.wmv *.mpg *.mpeg *.ts *.mts *.m2ts *.ogv *.3gp *.vob)",
            )
        added = 0
        for raw in paths_from_drop:
            path = Path(raw).expanduser().resolve()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and path not in self.video_paths:
                self.video_paths.append(path)
                item = QListWidgetItem(f"  ◇  {path.name}")
                item.setToolTip(str(path))
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.video_list.addItem(item)
                added += 1
        if added:
            count = len(self.video_paths)
            key = "queued_one" if count == 1 else "queued_many"
            self.status_title.setText(tr(key).format(count=count))
            self.status_detail.setText(tr("queued_detail"))
            self.start_button.setEnabled(True)
            self._update_remove_buttons()

    def _update_remove_buttons(self):
        working = bool(self.thread and self.thread.isRunning())
        self.remove_selected_button.setEnabled(
            not working and bool(self.video_list.selectedItems())
        )
        self.remove_queue_button.setEnabled(
            working and bool(self.pending_queue.selectedItems())
        )

    def _remove_selected_videos(self):
        if self.thread and self.thread.isRunning():
            return
        selected = self.video_list.selectedItems()
        if not selected:
            return
        selected_paths = {Path(item.data(Qt.ItemDataRole.UserRole)) for item in selected}
        self.video_paths = [path for path in self.video_paths if path not in selected_paths]
        for item in selected:
            self.video_list.takeItem(self.video_list.row(item))
        if self.video_paths:
            count = len(self.video_paths)
            key = "queued_one" if count == 1 else "queued_many"
            self.status_title.setText(tr(key).format(count=count))
            self.status_detail.setText(tr("queued_detail"))
        else:
            self.status_title.setText(tr("waiting"))
            self.status_detail.setText(tr("waiting_detail"))
            self.start_button.setEnabled(False)
        self._update_remove_buttons()

    def _set_pending_queue_visible(self, visible):
        has_pending = self.pending_queue.count() > 0
        self.pending_title.setVisible(visible)
        self.pending_queue.setVisible(visible and has_pending)
        self.pending_empty.setVisible(visible and not has_pending)
        self.remove_queue_button.setVisible(visible and has_pending)
        self._update_remove_buttons()

    def _remove_from_pending_queue(self):
        selected = self.pending_queue.selectedItems()
        if not selected or not self.worker:
            return
        for item in selected:
            path = Path(item.data(Qt.ItemDataRole.UserRole))
            self.worker.skip_video(path)
            self.video_paths = [video for video in self.video_paths if video != path]
            self.pending_queue.takeItem(self.pending_queue.row(item))
            for index in range(self.video_list.count()):
                listed = self.video_list.item(index)
                if Path(listed.data(Qt.ItemDataRole.UserRole)) == path:
                    self.video_list.takeItem(index)
                    break
        self._set_pending_queue_visible(True)

    def _clear(self):
        if self.thread and self.thread.isRunning():
            return
        self.video_paths.clear()
        self.video_list.clear()
        self.pending_queue.clear()
        self._set_pending_queue_visible(False)
        self.magic.set_progress(0)
        self.magic.clear_preview()
        self.status_title.setText(tr("waiting"))
        self.status_detail.setText(tr("waiting_detail"))
        self.open_button.setVisible(False)
        self._update_remove_buttons()

    def _start(self):
        if not self.video_paths or (self.thread and self.thread.isRunning()):
            return
        self.output_paths = []
        self.start_button.setEnabled(False)
        self.start_button.setVisible(False)
        self.stop_button.setVisible(True)
        self.stop_button.setEnabled(True)
        self.clear_button.setEnabled(False)
        self.fps_combo.setEnabled(False)
        self.custom_fps.setEnabled(False)
        self.open_button.setVisible(False)
        self.magic.set_progress(0)
        self.magic.clear_preview()
        self.magic.set_active(True)
        self.status_title.setText(tr("working"))
        self.status_detail.setText(tr("preparing"))
        self.pending_queue.clear()
        for path in self.video_paths:
            item = QListWidgetItem(f"  ◇  {path.name}")
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.pending_queue.addItem(item)
        self.pending_title.setText(tr("queue"))
        self.pending_empty.setText(tr("queue_empty"))
        self._set_pending_queue_visible(True)

        self.thread = QThread(self)
        self.worker = EnhanceWorker(self.video_paths, self._target_fps())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.preview_ready.connect(self.magic.set_preview)
        self.worker.item_finished.connect(self._on_item_finished)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(float, str, str)
    def _on_progress(self, progress, label, filename):
        self.magic.set_progress(progress)
        self.status_title.setText(label or tr("working"))
        self.status_detail.setText(filename or tr("preparing"))
        if filename:
            self._remove_current_from_pending_queue(filename)

    @Slot(str, bool, str)
    def _on_item_finished(self, video, ok, detail):
        target = Path(video)
        for index, queued in enumerate(self.video_paths):
            if queued == target:
                prefix = "✓" if ok else "!"
                self.video_list.item(index).setText(f"  {prefix}  {queued.name}")
                break
        if ok:
            self.output_paths.append(detail)

    def _remove_current_from_pending_queue(self, filename):
        for index in range(self.pending_queue.count()):
            item = self.pending_queue.item(index)
            if Path(item.data(Qt.ItemDataRole.UserRole)).name == filename:
                self.pending_queue.takeItem(index)
                self._set_pending_queue_visible(True)
                return

    @Slot(list, list)
    def _on_finished(self, completed, failed):
        self.magic.set_active(False)
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self.clear_button.setEnabled(True)
        self.fps_combo.setEnabled(True)
        self.custom_fps.setEnabled(True)
        self.pending_queue.clear()
        self._set_pending_queue_visible(False)
        if completed and not failed:
            self.magic.set_progress(1)
            self.status_title.setText(tr("complete"))
            key = "complete_one" if len(completed) == 1 else "complete_many"
            self.status_detail.setText(tr(key).format(count=len(completed)))
            self.open_button.setVisible(True)
        elif completed:
            self.status_title.setText(tr("warnings"))
            self.status_detail.setText(f"{len(completed)} completados · {len(failed)} con error")
            self.open_button.setVisible(True)
        else:
            self.status_title.setText(tr("failed"))
            message = failed[-1][1] if failed else tr("unknown_error")
            self.status_detail.setText(message)
            QMessageBox.warning(self, "LocallyFPS", message)
        self.worker = None
        self.thread = None

    def _stop(self):
        if not self.worker or not self.thread or not self.thread.isRunning():
            return
        self.stop_button.setEnabled(False)
        self.stop_button.setText(tr("stopping"))
        self.status_title.setText(tr("stopping"))
        self.status_detail.setText(tr("stopping_detail"))
        self.worker.request_stop()

    @Slot(list)
    def _on_cancelled(self, completed):
        self.magic.set_active(False)
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.stop_button.setVisible(False)
        self.stop_button.setEnabled(True)
        self.stop_button.setText(f"■  {tr('stop')}")
        self.clear_button.setEnabled(True)
        self.fps_combo.setEnabled(True)
        self.custom_fps.setEnabled(True)
        self.pending_queue.clear()
        self._set_pending_queue_visible(False)
        self.status_title.setText(tr("stopped"))
        self.status_detail.setText(tr("stopped_detail"))
        if completed:
            self.open_button.setVisible(True)
        self.worker = None
        self.thread = None

    def _open_results(self):
        configured = config.CONFIG.get("output_directory", "").strip()
        directory = Path(self.output_paths[-1]).parent if self.output_paths else Path(
            configured or paths.DOWNLOADS_DIR / "interpoled_locallyfps"
        ).expanduser()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _update_fps_value(self, *_args):
        value = self.fps_combo.currentData()
        custom = value == "custom"
        self.custom_fps.setVisible(custom)
        self.fps_value.setText(format_fps(self.custom_fps.value() if custom else value))

    def _target_fps(self):
        value = self.fps_combo.currentData()
        return float(self.custom_fps.value() if value == "custom" else value)

    def _show_settings(self):
        dialog = SettingsDialog(self)
        dialog.repair_requested.connect(self._show_repair)
        dialog.maintenance_requested.connect(self._maintenance)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved_fps = config.CONFIG.get("default_target_fps", "60")
            number = float(saved_fps)
            index = self.fps_combo.findData(number if saved_fps in {"60", "120", "240"} else "custom")
            self.fps_combo.setCurrentIndex(max(0, index))
            self.custom_fps.setValue(max(1, min(1000, number)))
            self._update_fps_value()

    def _show_repair(self):
        self.pages.setCurrentWidget(self.onboarding_page)
        self.setup_content.setCurrentIndex(1)
        self.setup_steps.setText("FFMPEG  ·  RIFE")
        self.setup_title.setText(tr("checking"))
        self.setup_subtitle.setText(tr("checking_hint"))
        self.setup_progress.setValue(0)
        self.setup_button.setText(tr("check_now"))

    def _maintenance(self, action):
        if self.thread and self.thread.isRunning():
            QMessageBox.information(self, tr("working_close"), tr("working_close_detail"))
            return
        if QMessageBox.question(
            self, tr("reset"), tr("maintenance_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        if action == "settings":
            language = config.CONFIG.get("language", paths.DEFAULT_LANGUAGE)
            config.CONFIG.clear()
            config.CONFIG.update(config.DEFAULT_CONFIG)
            config.CONFIG["language"] = language
            config.CONFIG["onboarding_complete"] = not paths.any_dep_missing()
            config.save_config()
            apply_theme(QApplication.instance())
            self.apply_language()
            QMessageBox.information(self, tr("maintenance_done"), tr("settings_reset"))
        elif action == "dependencies":
            for directory in (paths._FFMPEG_DIR, paths._RIFE_DIR, paths.MODELS_DIR):
                if directory:
                    shutil.rmtree(directory, ignore_errors=True)
            paths.ensure_dirs()
            QMessageBox.information(self, tr("maintenance_done"), tr("dependencies_removed"))
            self._show_repair()
        elif action == "cache":
            shutil.rmtree(paths.CACHE_DIR, ignore_errors=True)
            paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            QMessageBox.information(self, tr("maintenance_done"), tr("cache_cleared"))

    def _cycle_theme(self):
        current = config.CONFIG.get("theme", "dark")
        config.CONFIG["theme"] = "light" if current == "dark" else "dark"
        config.save_config()
        apply_theme(QApplication.instance())
        self._update_theme_button()

    def _update_theme_button(self):
        mode = config.CONFIG.get("theme", "dark")
        self.theme_button.setText("☀" if mode == "light" else "☾")
        self.theme_button.setToolTip(f"{tr('appearance_cycle')}: {tr(mode)}")

    def apply_language(self):
        if not hasattr(self, "videos_title"):
            return
        self.videos_title.setText(tr("videos"))
        self.drop.apply_language()
        self.clear_button.setText(tr("clear"))
        self.remove_selected_button.setText(tr("remove_selected"))
        self.pending_title.setText(tr("queue"))
        self.pending_empty.setText(tr("queue_empty"))
        self.remove_queue_button.setText(tr("remove_queue"))
        self.fps_label.setText(tr("fps"))
        self.fps_combo.setItemText(3, tr("custom"))
        self.start_button.setText(tr("enhance"))
        self.stop_button.setText(f"■  {tr('stop')}")
        self.open_button.setText(tr("open"))
        self.settings_button.setToolTip(tr("settings"))
        self._update_theme_button()
        self._apply_onboarding_language()
        if not (self.thread and self.thread.isRunning()):
            if self.video_paths:
                count = len(self.video_paths)
                key = "queued_one" if count == 1 else "queued_many"
                self.status_title.setText(tr(key).format(count=count))
                self.status_detail.setText(tr("queued_detail"))
            else:
                self.status_title.setText(tr("waiting"))
                self.status_detail.setText(tr("waiting_detail"))

    def closeEvent(self, event):
        if ((self.thread and self.thread.isRunning()) or
                (self.setup_thread and self.setup_thread.isRunning())):
            QMessageBox.information(
                self, tr("working_close"), tr("working_close_detail"),
            )
            event.ignore()
            return
        event.accept()


def _effective_theme(_app):
    return "light" if config.CONFIG.get("theme") == "light" else "dark"


def style_for_theme(theme):
    if theme == "light":
        c = {
            "root": "#f4f4f4", "workspace": "#e7e7e7", "card": "#ffffff",
            "field": "#f7f7f7", "text": "#171717", "muted": "#666666",
            "border": "#c9c9c9", "hover": "#dddddd", "selected": "#2b2b2b",
            "selected_text": "#ffffff", "primary": "#151515", "primary_text": "#ffffff",
            "disabled": "#bdbdbd", "disabled_text": "#777777",
        }
    else:
        c = {
            "root": "#0b0b0b", "workspace": "#202020", "card": "#303030",
            "field": "#171717", "text": "#f2f2f2", "muted": "#a0a0a0",
            "border": "#4a4a4a", "hover": "#414141", "selected": "#eeeeee",
            "selected_text": "#151515", "primary": "#f0f0f0", "primary_text": "#111111",
            "disabled": "#393939", "disabled_text": "#777777",
        }
    return """
QWidget { font-family: Inter, "Segoe UI", sans-serif; font-size: 14px; color: %(text)s; }
QWidget#root, QStackedWidget#root, QDialog, QMessageBox { background: %(root)s; color: %(text)s; }
QLabel { color: %(text)s; background: transparent; }
QLabel#brand { font-size: 27px; font-weight: 800; }
QLabel#beta { color: %(text)s; background: %(hover)s; border: 1px solid %(border)s; border-radius: 10px; padding: 4px 9px; font-size: 10px; font-weight: 700; }
QLabel#headline { font-size: 28px; font-weight: 750; }
QLabel#subtitle, QLabel#muted { color: %(muted)s; }
QLabel#subtitle { font-size: 14px; }
QLabel#muted { font-size: 12px; }
QLabel#fieldLabel, QLabel#eyebrow { color: %(muted)s; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#statusTitle { font-size: 18px; font-weight: 700; }
QLabel#setupTitle { font-size: 26px; font-weight: 750; }
QLabel#steps { color: %(muted)s; font-size: 13px; font-weight: 700; letter-spacing: 2px; }
QFrame#workspace { background: %(workspace)s; border: 1px solid %(border)s; border-radius: 25px; }
QFrame#panel, QFrame#flowCard, QFrame#setupCard, QFrame#settingsSection { background: %(card)s; border: 1px solid %(border)s; border-radius: 20px; }
QFrame#setupCard { border-radius: 26px; }
QFrame#settingsSection { border-radius: 16px; }
QFrame#dropCard { background: %(field)s; border: 1px dashed %(border)s; border-radius: 18px; }
QFrame#dropCard:hover, QFrame#dropCard[dragging="true"] { background: %(hover)s; border: 1px solid %(text)s; }
QLabel#dropIcon { color: %(text)s; font-size: 38px; }
QLabel#dropTitle { font-size: 17px; font-weight: 700; }
QLabel#flowIcon { font-size: 42px; font-weight: 500; }
QComboBox, QLineEdit, QDoubleSpinBox { color: %(text)s; background: %(field)s; border: 1px solid %(border)s; border-radius: 11px; padding: 10px 14px; min-height: 20px; selection-background-color: %(selected)s; selection-color: %(selected_text)s; }
QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover { border-color: %(text)s; }
QComboBox::drop-down { border: none; background: transparent; width: 28px; }
QComboBox::down-arrow { image: none; border: none; width: 0; height: 0; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; border: none; background: transparent; }
QComboBox QAbstractItemView, QAbstractItemView { color: %(text)s; background: %(field)s; alternate-background-color: %(field)s; border: 1px solid %(border)s; outline: 0; selection-background-color: %(selected)s; selection-color: %(selected_text)s; padding: 3px; }
QComboBox QAbstractItemView::item { border: none; min-height: 32px; padding: 4px 10px; }
QPushButton { border: 0; border-radius: 12px; padding: 10px 16px; font-weight: 650; }
QPushButton#primaryButton { color: %(primary_text)s; background: %(primary)s; font-size: 15px; }
QPushButton#primaryButton:hover { background: %(selected)s; color: %(selected_text)s; }
QPushButton#primaryButton:disabled { color: %(disabled_text)s; background: %(disabled)s; }
QPushButton#ghostButton, QPushButton#dangerButton { color: %(text)s; background: %(field)s; border: 1px solid %(border)s; }
QPushButton#ghostButton:hover, QPushButton#dangerButton:hover { background: %(hover)s; border-color: %(text)s; }
QPushButton#dangerButton:disabled { color: %(disabled_text)s; background: %(disabled)s; border-color: %(border)s; }
QPushButton#iconButton { color: %(text)s; background: transparent; font-size: 25px; padding: 5px; min-width: 42px; }
QPushButton#iconButton:hover { background: %(hover)s; }
QProgressBar { background: %(field)s; border: 1px solid %(border)s; border-radius: 7px; height: 13px; }
QProgressBar::chunk { background: %(primary)s; border-radius: 6px; }
QListWidget#queue { color: %(text)s; background: transparent; border: 0; outline: 0; }
QListWidget#queue::item { background: %(field)s; border: 1px solid %(border)s; border-radius: 9px; margin: 3px 0; padding: 9px 5px; }
QListWidget#queue::item:selected { background: %(selected)s; color: %(selected_text)s; }
QMessageBox QPushButton { color: %(text)s; background: %(field)s; border: 1px solid %(border)s; min-width: 74px; }
QMessageBox QPushButton:hover { background: %(hover)s; border-color: %(text)s; }
QMessageBox QLabel#qt_msgboxex_icon_label { min-width: 0; max-width: 0; qproperty-pixmap: none; }
QToolTip { color: %(text)s; background: %(card)s; border: 1px solid %(border)s; padding: 5px; }
QScrollBar:vertical { background: transparent; width: 7px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 3px; min-height: 22px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
""" % c


def apply_theme(app):
    if app is None:
        return
    theme = _effective_theme(app)
    app.setStyleSheet(style_for_theme(theme))
    for widget in app.topLevelWidgets():
        widget.update()


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--network-smoke-test", action="store_true")
    args, qt_args = parser.parse_known_args(argv)
    if args.network_smoke_test:
        # This only verifies that the frozen application can initialize its
        # HTTPS stack. A remote service rate limit must not make packaging
        # nondeterministic (macOS GitHub runners commonly receive HTTP 403).
        from urllib.error import HTTPError, URLError
        from core.network import open_url
        try:
            with open_url("https://api.github.com/zen", timeout=15) as response:
                if not response.read(256):
                    return 1
        except (HTTPError, URLError, OSError):
            pass
        return 0
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("LocallyFPS")
    app.setApplicationDisplayName("LocallyFPS")
    app.setStyle("Fusion")
    paths.ensure_dirs()
    config.load_config()
    apply_theme(app)
    icon = paths.RESOURCE_DIR / "packaging" / "locallyfps.svg"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    if args.smoke_test:
        QTimer.singleShot(250, app.quit)
    return app.exec()
