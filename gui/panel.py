"""Kyros Dynamic Island Panel - PyQt6"""

import math
import time
import threading
from ctypes import c_void_p
from PyQt6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QApplication,
    QMenu,
    QDialog,
    QTextBrowser,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QFrame,
    QMessageBox,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QRectF,
    QPointF,
    QPropertyAnimation,
    QPoint,
    QObject,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QRadialGradient,
    QPainterPath,
    QFont,
    QFontMetrics,
)


MODES = {
    "sesaygiti": {
        "orb1": (120, 160, 190),
        "orb2": (100, 150, 170),
        "orb3": (130, 130, 180),
        "dot": (160, 200, 240),
        "ai_amp": 2.5,
        "mic_amp": 0,
        "label": "SES AYGITI DEĞİŞİYOR",
    },
    "baglaniyor": {
        "orb1": (170, 160, 100),
        "orb2": (120, 140, 200),
        "orb3": (140, 120, 150),
        "dot": (220, 190, 90),
        "ai_amp": 2.5,
        "mic_amp": 0,
        "label": "BAĞLANIYOR",
    },
    "uyguluyor": {
        "orb1": (90, 190, 220),
        "orb2": (100, 220, 180),
        "orb3": (150, 140, 240),
        "dot": (110, 230, 180),
        "ai_amp": 10,
        "mic_amp": 8,
        "label": "UYGULUYOR · DİNLİYOR",
    },
    "kapali": {
        "orb1": (90, 90, 100),
        "orb2": (100, 100, 110),
        "orb3": (100, 90, 100),
        "dot": (160, 160, 160),
        "ai_amp": 0,
        "mic_amp": 0,
        "label": "MİKROFON KAPALI",
    },
    "hata": {
        "orb1": (200, 80, 80),
        "orb2": (160, 100, 100),
        "orb3": (120, 80, 110),
        "dot": (255, 110, 100),
        "ai_amp": 1,
        "mic_amp": 0,
        "label": "BAĞLANTI / SES HATASI",
    },
    "bekliyor": {
        "orb1": (100, 210, 175),
        "orb2": (80, 160, 240),
        "orb3": (160, 140, 255),
        "dot": (140, 210, 180),
        "ai_amp": 2.5,
        "mic_amp": 1.5,
        "label": "BEKLIYOR",
    },
    "dinliyor": {
        "orb1": (60, 190, 255),
        "orb2": (100, 240, 200),
        "orb3": (120, 180, 255),
        "dot": (90, 190, 255),
        "ai_amp": 6.0,
        "mic_amp": 13.0,
        "label": "DINLIYOR",
    },
    "konusuyor": {
        "orb1": (180, 140, 255),
        "orb2": (100, 220, 210),
        "orb3": (220, 160, 200),
        "dot": (200, 160, 255),
        "ai_amp": 17.0,
        "mic_amp": 3.5,
        "label": "KONUSUYOR",
    },
}

PANEL_W = 300
PANEL_H = 100
ORB_COUNT = 3
MIC_BARS = 32
LERP = 0.045


class PanelSignals(QObject):
    mode = pyqtSignal(str)
    level = pyqtSignal(float)
    text = pyqtSignal(str, str)
    error = pyqtSignal(str)
    tool = pyqtSignal(str, str)
    sources = pyqtSignal(object)


def lerp(a, b, t):
    return a + (b - a) * t


class ApiSettingsDialog(QDialog):
    """Modern API + Voice Model ayar dialogu — mevcut akışı bozmaz."""

    _test_result = pyqtSignal(bool, str)
    _save_result = pyqtSignal(bool, str)
    _models_fetched = pyqtSignal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kyros Ayarları")
        self.setFixedSize(460, 400)
        self.setModal(True)
        # Frameless modern look ama native close kalsın
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(self._style())
        self._test_result.connect(self._on_test_result)
        self._models_fetched.connect(self._on_models_fetched)
        self._build_ui()
        self._load_current()

    def _style(self):
        return """
        QDialog {
            background-color: #0f0f13;
            color: #e8e8ec;
            border-radius: 16px;
        }
        QLabel {
            color: #e8e8ec;
            background: transparent;
        }
        QLabel#title {
            font-size: 17px;
            font-weight: 700;
            color: #ffffff;
        }
        QLabel#subtitle {
            font-size: 11px;
            color: #9aa0b5;
        }
        QLabel#fieldLabel {
            font-size: 11px;
            font-weight: 600;
            color: #aab0c3;
            letter-spacing: 0.3px;
        }
        QLineEdit, QComboBox {
            background-color: #1a1a20;
            color: #f0f0f5;
            border: 1px solid #2a2a34;
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 12px;
            selection-background-color: #3a3a4a;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #5b6bff;
            background-color: #1e1e28;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox::down-arrow {
            width: 0;
            height: 0;
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #1a1a20;
            color: #e8e8ec;
            border: 1px solid #2a2a34;
            selection-background-color: #2e2e42;
            padding: 4px;
        }
        QPushButton {
            border: none;
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton#primary {
            background-color: #5b6bff;
            color: white;
        }
        QPushButton#primary:hover {
            background-color: #6a7aff;
        }
        QPushButton#primary:disabled {
            background-color: #2a2a3a;
            color: #6a6a7a;
        }
        QPushButton#secondary {
            background-color: #1e1e28;
            color: #c8c8d5;
            border: 1px solid #2a2a34;
        }
        QPushButton#secondary:hover {
            background-color: #252535;
        }
        QPushButton#ghost {
            background: transparent;
            color: #8a8aa0;
            font-size: 18px;
            padding: 4px 8px;
        }
        QPushButton#ghost:hover {
            color: #e0e0ff;
            background-color: #1e1e28;
        }
        QLabel#status {
            font-size: 11px;
            padding: 6px 10px;
            border-radius: 8px;
        }
        """

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(13)

        # Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Kyros Ayarları")
        title.setObjectName("title")
        subtitle = QLabel("API anahtarı ve voice-native model — değişiklik anında aktif olur")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        # close hint
        header.addStretch()
        root.addLayout(header)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #222230; max-height: 1px; border: none;")
        line.setFixedHeight(1)
        root.addWidget(line)

        # API Key
        api_label = QLabel("GEMINI API ANAHTARI")
        api_label.setObjectName("fieldLabel")
        root.addWidget(api_label)
        api_row = QHBoxLayout()
        api_row.setSpacing(8)
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Gemini API — boş bırakırsan mevcut korunur")
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.setClearButtonEnabled(True)
        api_row.addWidget(self.api_input, 1)
        self.toggle_btn = QPushButton("Göster")
        self.toggle_btn.setObjectName("ghost")
        self.toggle_btn.setFixedSize(68, 36)
        self.toggle_btn.setMinimumWidth(68)
        self.toggle_btn.setToolTip("Göster / gizle")
        self.toggle_btn.clicked.connect(self._toggle_api)
        api_row.addWidget(self.toggle_btn)
        root.addLayout(api_row)

        # Model — sadece doğrulanmış voice-native'ler, silinemez
        model_label = QLabel("VOICE-NATIVE MODEL — sadece listedekiler çalışır")
        model_label.setObjectName("fieldLabel")
        root.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)
        # Sadece gerçekten çalışan voice-native modeller (API'den doğrulanmış)
        try:
            import config
            models = getattr(config, "VOICE_NATIVE_MODELS", [])
        except Exception:
            models = []
        if not models:
            models = [
                "gemini-2.5-flash-native-audio-latest",
                "gemini-2.5-flash-native-audio-preview-09-2025",
            ]
        for m in models:
            self.model_combo.addItem(m)
        root.addWidget(self.model_combo)

        # Status
        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        root.addWidget(self.status_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.test_btn = QPushButton("Test Et")
        self.test_btn.setObjectName("secondary")
        self.test_btn.setToolTip("API + model gerçekten çalışıyor mu kontrol et")
        self.test_btn.clicked.connect(self._on_test)
        btn_row.addWidget(self.test_btn)

        btn_row.addStretch()
        cancel = QPushButton("İptal")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self.save_btn = QPushButton("Kaydet ve Uygula")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        # Hint
        hint = QLabel("Değişiklik local.json'a yazılır, bağlantı otomatik yenilenir. Geçersiz API uyarı verir ama engellemez.")
        hint.setStyleSheet("color: #6a6a80; font-size: 10px; background: transparent;")
        hint.setWordWrap(True)
        root.addWidget(hint)

    def _load_current(self):
        try:
            import config
            cur_key = getattr(config, "GEMINI_API_KEY", "") or ""
            cur_model = getattr(config, "GEMINI_MODEL", "") or ""
            if cur_key:
                self.api_input.setPlaceholderText(f"Mevcut: {cur_key[:4]}...{cur_key[-4:]} — boş bırak=koru")
            # model — listede yoksa ekle (eski custom)
            idx = self.model_combo.findText(cur_model)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                if cur_model:
                    self.model_combo.addItem(cur_model)
                    self.model_combo.setCurrentIndex(self.model_combo.count() - 1)
            # API varsa dinamik voice-native listesini sessizce yenile (doğru isimler)
            if cur_key:
                self._refresh_models_async(cur_key, cur_model)
        except Exception:
            pass

    def _on_models_fetched(self, models, select_model):
        cur = select_model or self.model_combo.currentText()
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)
        idx = self.model_combo.findText(cur)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        elif cur:
            self.model_combo.addItem(cur)
            self.model_combo.setCurrentIndex(self.model_combo.count() - 1)

    def _refresh_models_async(self, api_key, select_model=None):
        # Arkaplanda /v1beta/models çek, sadece bidiGenerateContent olanları göster
        def run():
            try:
                import config
                models = config.fetch_voice_models(api_key)
                self._models_fetched.emit(models, select_model or "")
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def _toggle_api(self):
        if self.api_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_btn.setText("Gizle")
        else:
            self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_btn.setText("Göster")

    def _set_status(self, text, kind="info"):
        # kind: info, success, error
        colors = {
            "info": "background-color: #1a1a20; color: #aab0c3; border: 1px solid #2a2a34;",
            "success": "background-color: #0f2a1a; color: #7ee0a0; border: 1px solid #1a4a2a;",
            "error": "background-color: #2a0f13; color: #ff8a8a; border: 1px solid #4a1a20;",
        }
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"QLabel#status {{ {colors.get(kind, colors['info'])} }}")
        self.status_label.show()

    def _on_test_result(self, ok, msg):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test Et")
        self._set_status(msg, "success" if ok else "error")

    def _on_test(self):
        api_input = self.api_input.text().strip()
        model = self.model_combo.currentText().strip()
        using_existing = False
        if not api_input:
            try:
                import config
                api = getattr(config, "GEMINI_API_KEY", "")
                using_existing = True
            except Exception:
                api = ""
        else:
            api = api_input
        if not api:
            self._set_status("Önce bir API anahtarı girin.", "error")
            return
        if not model:
            self._set_status("Model seçin.", "error")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Test ediliyor…")
        prefix = "Mevcut API ile " if using_existing else "Yeni API ile "
        self._set_status(f"{prefix}doğrulanıyor…", "info")
        def run():
            try:
                import config
                ok, msg = config.validate_api_key(api, model)
                # mesajı netleştir
                if using_existing and ok:
                    msg = f"Mevcut API ile {msg}"
                elif not using_existing and ok:
                    msg = f"Yeni API ile {msg}"
                self._test_result.emit(ok, msg)
            except Exception as e:
                self._test_result.emit(False, f"Hata: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _handle_save_after_validate(self, api, model, ok, msg):
        self.save_btn.setEnabled(True)
        self.save_btn.setText("Kaydet ve Uygula")
        if not ok:
            ret = QMessageBox.warning(
                self,
                "Doğrulama Başarısız",
                f"{msg}\n\nAPI veya model çalışmayabilir. Yine de kaydetmek istiyor musunuz?\n(Geçersiz API ile bağlantı kopacak)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                self._set_status(msg, "error")
                return
            self._set_status(f"Uyarı ile kaydedildi: {msg}", "error")
        else:
            self._set_status(msg, "success")
        self._do_save(api, model)

    def _on_save(self):
        api = self.api_input.text().strip()
        model = self.model_combo.currentText().strip()
        if not model:
            self._set_status("Model boş olamaz.", "error")
            return
        if api:
            # Gemini anahtarları AIza... veya AQ. ile başlar, 20+ karakter — çok katı olma
            if len(api) < 20 or not (api.startswith("AIza") or api.startswith("AQ.")):
                ret = QMessageBox.warning(
                    self,
                    "API Şüpheli",
                    f"Girdiğiniz anahtar '{api[:12]}...' Gemini formatına benzemiyor (genelde AIza... veya AQ. ile başlar).\nYine de kaydetmek istiyor musunuz?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret != QMessageBox.StandardButton.Yes:
                    return
            self.save_btn.setEnabled(False)
            self.save_btn.setText("Doğrulanıyor…")
            self._set_status("Kaydetmeden önce doğrulanıyor…", "info")
            def validate_and_save():
                try:
                    import config
                    ok, msg = config.validate_api_key(api, model)
                    # ana thread'e sinyal ile dön
                    self._save_result.emit(ok, msg)
                except Exception as e:
                    self._save_result.emit(False, f"Doğrulama hatası: {e}")
            # tek seferlik bağlantı
            try:
                self._save_result.disconnect()
            except Exception:
                pass
            self._save_result.connect(lambda ok, msg, a=api, m=model: self._handle_save_after_validate(a, m, ok, msg))
            threading.Thread(target=validate_and_save, daemon=True).start()
        else:
            # sadece model değişti, API korunuyor
            self._do_save(None, model)

    def _do_save(self, api, model):
        try:
            import config
            # api None ise mevcut korunur, model her zaman kaydedilir
            config.save_config(api_key=api if api else None, model=model)
            # parent panel'e haber ver — canlı bağlantıyı yenile
            parent = self.parent()
            # KyrosPanel ise
            if parent and hasattr(parent, "_apply_api_change"):
                parent._apply_api_change(api if api else None, model)
            QMessageBox.information(self, "Kaydedildi", f"Model: {model}\nAPI: {'değişti' if api else 'korundu'}\nBağlantı yenileniyor…")
            self.accept()
        except Exception as e:
            self._set_status(f"Kaydetme hatası: {e}", "error")
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi: {e}")


class KyrosPanel(QMainWindow):
    def __init__(self, kyros=None):
        super().__init__()
        self.kyros = kyros
        self.current_mode = "bekliyor"
        self.t0 = time.time()
        self._mic_level = 0.0
        self._label_font = QFont(QApplication.font())
        self._label_font.setPointSize(9)
        self._label_font.setWeight(QFont.Weight.DemiBold)
        self.signals = PanelSignals(self)
        self.signals.mode.connect(self.set_mode)
        self.signals.level.connect(self.set_mic_level)
        self.signals.text.connect(self._add_text)
        self.signals.error.connect(lambda text: self._add_text("Hata", text))
        self.signals.tool.connect(
            lambda name, state: self._add_text("İşlem", f"{name}: {state}")
        )
        self.signals.sources.connect(self._add_sources)
        self._mic_muted = False
        self._history = QDialog(self)
        self._history.setWindowTitle("Kyros · Konuşma ve kontroller")
        self._history.resize(580, 450)
        # The panel is intentionally allowed to sit at the top edge; the history
        # window must still be placed fully inside the current usable screen.
        screen = QApplication.primaryScreen().availableGeometry()
        self._history.move(screen.center() - self._history.rect().center())
        layout = QVBoxLayout(self._history)
        self._transcript = QTextBrowser()
        self._transcript.setOpenExternalLinks(True)
        self._transcript.document().setMaximumBlockCount(500)
        layout.addWidget(self._transcript)
        entry_row = QHBoxLayout()
        self._entry = QLineEdit()
        self._entry.setPlaceholderText("Kyros'a yaz…")
        self._entry.returnPressed.connect(self._send_entry)
        entry_row.addWidget(self._entry)
        send = QPushButton("Gönder")
        send.clicked.connect(self._send_entry)
        entry_row.addWidget(send)
        layout.addLayout(entry_row)
        controls = QHBoxLayout()
        for label, action in (
            ("Uyandır", "wake"),
            ("Durdur", "stop"),
            ("Beklemeye al", "standby"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, action=action: self.kyros.control(action)
            )
            controls.addWidget(button)
        layout.addLayout(controls)

        self._cur_orb = [
            list(MODES["bekliyor"][f"orb{i + 1}"]) for i in range(ORB_COUNT)
        ]
        self._tgt_orb = [
            list(MODES["bekliyor"][f"orb{i + 1}"]) for i in range(ORB_COUNT)
        ]
        self._cur_ai_amp = MODES["bekliyor"]["ai_amp"]
        self._tgt_ai_amp = MODES["bekliyor"]["ai_amp"]
        self._cur_mic_amp = MODES["bekliyor"]["mic_amp"]
        self._tgt_mic_amp = MODES["bekliyor"]["mic_amp"]
        self._cur_dot = list(MODES["bekliyor"]["dot"])
        self._tgt_dot = list(MODES["bekliyor"]["dot"])

        self._setup_window()
        self._setup_gear()
        self._init_timer()
        self.setToolTip(
            "Tıkla: konuşma ve kontroller · Sağ tık: durdur / bekleme / mikrofon · ⚙: API / model"
        )
        # İlk kurulum: API yoksa otomatik ayar ekranı (git'ten klonlayınca)
        QTimer.singleShot(900, self._check_api_on_startup)

    def bind(self, gemini):
        gemini.on_state_change = self.signals.mode.emit
        gemini.on_mic_level = self.signals.level.emit
        gemini.on_text = self.signals.text.emit
        gemini.on_error = self.signals.error.emit
        gemini.on_tool = self.signals.tool.emit
        gemini.on_sources = self.signals.sources.emit

    def _add_text(self, who, text):
        import html

        self._transcript.append(f"<b>{html.escape(who)}:</b> {html.escape(text)}")
        if who == "Hata":
            self.setToolTip(text)

    def _add_sources(self, sources):
        import html

        for source in sources:
            url = source.get("uri", "")
            if url.startswith(("https://", "http://")):
                self._transcript.append(
                    f'<a href="{html.escape(url, quote=True)}">{html.escape(source.get("title", url))}</a>'
                )

    def _send_entry(self):
        text = self._entry.text().strip()
        if text and self.kyros:
            self.kyros.send_text(text)
            self._entry.clear()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFixedSize(PANEL_W, PANEL_H)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - PANEL_W) // 2
        self.move(x, -PANEL_H)

    def _setup_gear(self):
        # Sağ üst çark — panel boyası üstünde duran gerçek buton
        self._gear_btn = QPushButton("⚙", self)
        self._gear_btn.setFixedSize(24, 24)
        self._gear_btn.move(PANEL_W - 28, 6)
        self._gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gear_btn.setToolTip("Ayarlar — API anahtarı ve voice-native model")
        self._gear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,18);
                color: #c8c8d5;
                border: 1px solid rgba(255,255,255,22);
                border-radius: 12px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(91,107,255,180);
                color: white;
                border: 1px solid rgba(91,107,255,220);
            }
            QPushButton:pressed {
                background-color: rgba(91,107,255,220);
            }
        """)
        # gölge
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 2)
        self._gear_btn.setGraphicsEffect(shadow)
        self._gear_btn.clicked.connect(self._open_api_settings)
        self._gear_btn.show()
        self._gear_btn.raise_()

    def _check_api_on_startup(self):
        try:
            import config

            if not getattr(config, "GEMINI_API_KEY", ""):
                # modern uyarı + ayar aç
                self._add_text("Sistem", "API anahtarı yok — sağ üst ⚙ ile Gemini API ekleyin.")
                QTimer.singleShot(400, self._open_api_settings)
        except Exception:
            pass

    def _open_api_settings(self):
        # Panel tıkını yutma — history yerine ayar aç
        dlg = ApiSettingsDialog(self)
        dlg.exec()

    def _apply_api_change(self, new_api, new_model):
        """Dialog'dan çağrılır — dosyaya zaten yazıldı, canlı bağlantıyı yenile."""
        try:
            import config
            # Bellekteki config zaten save_config ile güncellendi
            # Çalışan GeminiLive'ı güncelle
            if self.kyros and hasattr(self.kyros, "gemini") and self.kyros.gemini:
                g = self.kyros.gemini
                # Eğer API değiştiyse güncelle
                if new_api:
                    g.api_key = new_api
                    config.GEMINI_API_KEY = new_api
                if new_model:
                    g.model = new_model
                    config.GEMINI_MODEL = new_model
                # Bağlantıyı yeniden kur — mevcut akışı bozmadan soft restart
                # stop/start, _handle korunur, state korunur
                def restart():
                    try:
                        g.stop()
                        # kısa bekle
                        time.sleep(0.6)
                        g.start()
                    except Exception as e:
                        print(f"[PANEL] restart failed: {e}")
                threading.Thread(target=restart, daemon=True).start()
                self._add_text("Sistem", f"Model: {new_model}" + (" · API güncellendi" if new_api else ""))
        except Exception as e:
            print(f"[PANEL] _apply_api_change failed: {e}")

    def _init_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def slide_in(self):
        self.show()
        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(300)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - PANEL_W) // 2
        self._slide_anim.setStartValue(QPoint(x, -PANEL_H))
        self._slide_anim.setEndValue(QPoint(x, 0))
        self._slide_anim.start()

    def _fix_macos_window(self):
        try:
            import objc
            from AppKit import (
                NSFloatingWindowLevel,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorIgnoresCycle,
            )

            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_window = ns_view.window()
            ns_window.setLevel_(NSFloatingWindowLevel + 1)
            ns_window.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorIgnoresCycle
            )
            ns_window.setHidesOnDeactivate_(False)
        except Exception as e:
            print(f"[PANEL] macOS fix failed: {e}")

    def focusOutEvent(self, e):
        pass

    def changeEvent(self, e):
        self.show()

    def set_mode(self, mode: str):
        if mode not in MODES:
            return
        self.current_mode = mode
        m = MODES[mode]
        self._tgt_orb = [list(m[f"orb{i + 1}"]) for i in range(ORB_COUNT)]
        self._tgt_ai_amp = m["ai_amp"]
        self._tgt_mic_amp = m["mic_amp"]
        self._tgt_dot = list(m["dot"])

    def set_mic_level(self, level: float):
        self._mic_level = min(1.0, max(0.0, level))

    def _tick(self):
        t = LERP
        for i in range(ORB_COUNT):
            for j in range(3):
                self._cur_orb[i][j] = lerp(self._cur_orb[i][j], self._tgt_orb[i][j], t)
        self._cur_ai_amp = lerp(self._cur_ai_amp, self._tgt_ai_amp, t)
        self._cur_mic_amp = lerp(self._cur_mic_amp, self._tgt_mic_amp, t)
        for j in range(3):
            self._cur_dot[j] = lerp(self._cur_dot[j], self._tgt_dot[j], t)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        elapsed = time.time() - self.t0
        self._draw_background(p)
        self._draw_orbs(p, elapsed)
        self._draw_mic_bars(p, elapsed)
        self._draw_label(p)
        p.end()

    def _draw_background(self, p):
        p.save()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, PANEL_W, PANEL_H), 20, 20)
        p.setClipPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 12, 16, 210))
        p.drawRoundedRect(QRectF(0, 0, PANEL_W, PANEL_H), 20, 20)
        border_pen = QPen(QColor(255, 255, 255, 35), 1)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0, 0, PANEL_W, PANEL_H), 20, 20)
        p.restore()

    def _draw_orbs(self, p, t):
        p.save()
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, PANEL_W - 2, PANEL_H - 2), 19, 19)
        p.setClipPath(path)
        cx = PANEL_W / 2
        cy = PANEL_H / 2
        radii = [55, 40, 28]
        for i in range(ORB_COUNT):
            ox = cx + math.sin(t * 0.3 + i * 2.1) * 35
            oy = cy + math.cos(t * 0.22 + i * 1.7) * 12
            r = radii[i]
            c = self._cur_orb[i]
            grad = QRadialGradient(QPointF(ox, oy), r)
            grad.setColorAt(0, QColor(int(c[0]), int(c[1]), int(c[2]), 70))
            grad.setColorAt(0.5, QColor(int(c[0]), int(c[1]), int(c[2]), 30))
            grad.setColorAt(1.0, QColor(int(c[0]), int(c[1]), int(c[2]), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(ox, oy), r, r)
        p.restore()

    def _draw_mic_bars(self, p, t):
        p.save()
        path_clip = QPainterPath()
        path_clip.addRoundedRect(QRectF(1, 1, PANEL_W - 2, PANEL_H - 2), 19, 19)
        p.setClipPath(path_clip)

        W = 244
        ox = (PANEL_W - W) / 2
        oy = 64
        bar_h = 18
        gap = W / MIC_BARS

        for i in range(MIC_BARS):
            noise = math.sin(i * 0.65 + t * 3.5) * math.cos(i * 0.3 + t * 1.7)
            base = abs(noise) * self._cur_mic_amp * self._mic_level
            extra = self._mic_level * 8 * abs(math.sin(i * 0.5 + t * 2))
            h = max(1.5, base + extra)
            h = min(h, bar_h)

            x = ox + i * gap
            y = oy + (bar_h - h) / 2

            brightness = 0.2 + (h / bar_h) * 0.55
            alpha = int(brightness * 255)
            alpha = min(alpha, 191)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, alpha))
            p.drawRoundedRect(QRectF(x, y, 2.5, h), 1.2, 1.2)
        p.restore()

    def _draw_label(self, p):
        p.save()
        label = MODES[self.current_mode]["label"]
        font = self._label_font
        p.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(label)
        th = fm.height()

        lx = (PANEL_W - tw - 14) / 2
        ly = PANEL_H - 16

        c = self._cur_dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(int(c[0]), int(c[1]), int(c[2]), 200))
        p.drawEllipse(QPointF(lx - 6, ly + th / 2 - 1), 2.5, 2.5)

        p.setPen(QColor(255, 255, 255, 115))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawText(QPointF(lx, ly + th - 2), label)
        p.restore()

    def mousePressEvent(self, event):
        # çarkın üstüne tıklanırsa ayar aç, panele düşmesin
        if hasattr(self, "_gear_btn") and self._gear_btn.geometry().contains(event.pos()):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_settings()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            for label, action in (
                ("Uyandır", "wake"),
                ("Şimdi durdur", "stop"),
                ("Beklemeye al", "standby"),
            ):
                item = menu.addAction(label)
                item.triggered.connect(
                    lambda checked=False, action=action: self.kyros.control(action)
                )
            menu.addSeparator()
            mute = menu.addAction(
                "Mikrofonu aç" if self._mic_muted else "Mikrofonu kapat"
            )
            mute.triggered.connect(self._toggle_mic)
            menu.addAction("Ayarlar ⚙", self._open_api_settings)
            menu.addAction("Konuşma ve kontroller", self._open_settings)
            menu.addAction("Çıkış", QApplication.instance().quit)
            menu.exec(event.globalPosition().toPoint())

    def _toggle_mic(self):
        self._mic_muted = not self._mic_muted
        self.kyros.set_mic_muted(self._mic_muted)

    def _open_settings(self):
        self._history.show()
        self._history.raise_()
        self._history.activateWindow()

    def closeEvent(self, event):
        if self.kyros and hasattr(self.kyros, "stop"):
            self.kyros.stop()
        event.accept()
        QApplication.instance().quit()

    def close(self):
        self.timer.stop()
        super().close()
