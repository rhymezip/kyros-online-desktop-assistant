"""Kyros Dynamic Island Panel - PyQt6"""

import logging
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


class AnimatedWidget(QObject):
    """Base for widgets with fade-in animation."""
    def __init__(self, widget, delay=0):
        super().__init__(widget)
        self._widget = widget
        self._opacity = 0.0
        self._delay = delay
        widget.setWindowOpacity(0.0)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_in)
        self._timer.start(delay)

    def _fade_in(self):
        self._anim = QPropertyAnimation(self, b"opacity")
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    @property
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, val):
        self._opacity = val
        self._widget.setWindowOpacity(val)


class GlowEffect(QGraphicsDropShadowEffect):
    """Animated glow effect for buttons on hover."""
    def __init__(self, color="#5b6bff", radius=20, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setColor(self._color)
        self.setBlurRadius(radius)
        self.setOffset(0, 0)
        self._anim = QPropertyAnimation(self, b"blurRadius")
        self._anim.setDuration(200)

    def animate_in(self):
        self._anim.stop()
        self._anim.setStartValue(self.blurRadius())
        self._anim.setEndValue(24)
        self._anim.start()

    def animate_out(self):
        self._anim.stop()
        self._anim.setStartValue(self.blurRadius())
        self._anim.setEndValue(12)
        self._anim.start()


class PulseLabel(QLabel):
    """Label with subtle pulse animation for status updates."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pulse_anim = None

    def pulse(self, color="#5b6bff"):
        if self._pulse_anim:
            self._pulse_anim.stop()
        self._pulse_anim = QPropertyAnimation(self, b"styleSheet")
        self._pulse_anim.setDuration(600)
        base = f"color: {color}; background: transparent;"
        highlight = f"color: {color}; background: transparent; font-weight: 700;"
        self._pulse_anim.setKeyValueAt(0.0, base)
        self._pulse_anim.setKeyValueAt(0.5, highlight)
        self._pulse_anim.setKeyValueAt(1.0, base)
        self._pulse_anim.start()


class SectionCard(QFrame):
    """Glassmorphism card with fade-in animation."""
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setStyleSheet("""
            QFrame#sectionCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(30, 30, 45, 180),
                    stop:1 rgba(20, 20, 30, 160));
                border: 1px solid rgba(90, 100, 160, 60);
                border-radius: 14px;
                padding: 16px;
            }
            QFrame#sectionCard:hover {
                border: 1px solid rgba(90, 100, 160, 120);
            }
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet("""
                font-size: 10px; font-weight: 700; color: #7a82a8;
                letter-spacing: 1.5px; padding: 0 0 4px 0;
                border: none; background: transparent;
            """)
            self._layout.addWidget(lbl)

        # Fade-in
        self._opacity_val = 0.0
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(400)

    def fade_in(self, delay=0):
        self._fade.stop()
        if delay > 0:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(delay, self._start_fade)
        else:
            self._start_fade()

    def _start_fade(self):
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    @property
    def windowOpacity(self):
        return self._opacity_val

    @windowOpacity.setter
    def windowOpacity(self, val):
        self._opacity_val = val
        self.setWindowOpacity(val)


class ModernComboBox(QComboBox):
    """ComboBox with animated hover and focus effects."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(38)
        self.setStyleSheet("""
            QComboBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e1e2a, stop:1 #181822);
                color: #e8e8f0;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 12px;
                font-weight: 500;
                selection-background-color: #3a3a5a;
            }
            QComboBox:hover {
                border: 1px solid #4a5080;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #22223a, stop:1 #1c1c2c);
            }
            QComboBox:focus {
                border: 1px solid #6b7bff;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #242440, stop:1 #1e1e32);
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
                subcontrol-position: center right;
            }
            QComboBox::down-arrow {
                width: 0; height: 0; border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a28;
                color: #e8e8f0;
                border: 1px solid #3a3a50;
                border-radius: 8px;
                selection-background-color: #2e2e4a;
                padding: 6px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 12px;
                border-radius: 6px;
                min-height: 24px;
            }
            QComboBox QAbstractItemView::item:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2a2a4a, stop:1 #32325a);
            }
        """)


class ModernLineEdit(QLineEdit):
    """LineEdit with animated border glow on focus."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet("""
            QLineEdit {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e1e2a, stop:1 #181822);
                color: #e8e8f0;
                border: 1px solid #2a2a3a;
                border-radius: 10px;
                padding: 11px 14px;
                font-size: 12px;
                font-weight: 500;
                selection-background-color: #4a4a6a;
            }
            QLineEdit:hover {
                border: 1px solid #4a5080;
            }
            QLineEdit:focus {
                border: 1px solid #6b7bff;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #242440, stop:1 #1e1e32);
            }
        """)


class ModernButton(QPushButton):
    """Button with animated glow and press effects."""
    def __init__(self, text="", variant="primary", parent=None):
        super().__init__(text, parent)
        self._variant = variant
        self._glow = GlowEffect(
            color="#6b7bff" if variant == "primary" else "#5a6a8a",
            radius=12,
            parent=self,
        )
        self.setGraphicsEffect(self._glow)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _update_style(self):
        if self._variant == "primary":
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #5b6bff, stop:1 #7b5bff);
                    color: white;
                    border: none;
                    border-radius: 11px;
                    padding: 11px 22px;
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 0.3px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #6b7bff, stop:1 #8b6bff);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #4b5bef, stop:1 #6b4bef);
                    padding-top: 12px; padding-bottom: 10px;
                }
                QPushButton:disabled {
                    background: #2a2a3a;
                    color: #5a5a6a;
                }
            """)
        elif self._variant == "secondary":
            self.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #1e1e2a, stop:1 #181822);
                    color: #c0c0d0;
                    border: 1px solid #2a2a3a;
                    border-radius: 11px;
                    padding: 10px 20px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    border: 1px solid #4a5080;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #24243a, stop:1 #1e1e2e);
                }
                QPushButton:pressed {
                    background: #1a1a28;
                    padding-top: 11px; padding-bottom: 9px;
                }
            """)
        else:  # ghost
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #7a7a90;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    color: #b0b0d0;
                    background: rgba(90, 100, 160, 40);
                }
            """)

    def enterEvent(self, event):
        self._glow.animate_in()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._glow.animate_out()
        super().leaveEvent(event)


class LoadingSpinner(QLabel):
    """Animated loading spinner."""
    def __init__(self, parent=None):
        super().__init__("⟳", parent)
        self.setStyleSheet("""
            font-size: 16px; color: #6b7bff;
            background: transparent; border: none;
        """)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self.hide()

    def start(self):
        self._angle = 0
        self.show()
        self._timer.start(16)

    def stop(self):
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 12) % 360
        self.setStyleSheet(f"""
            font-size: 16px; color: #6b7bff;
            background: transparent; border: none;
            transform: rotate({self._angle}deg);
        """)


class ApiSettingsDialog(QDialog):
    """Modern 2026 API + Voice Model + Audio Devices settings dialog with animations."""

    _test_result = pyqtSignal(bool, str)
    _save_result = pyqtSignal(bool, str)
    _models_fetched = pyqtSignal(list, str)
    _devices_fetched = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kyros Ayarları")
        self.setMinimumSize(480, 400)
        self.resize(480, 520)
        self.setModal(True)
        self._input_devices = []
        self._output_devices = []
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(self._style())
        self._test_result.connect(self._on_test_result)
        self._save_result.connect(self._on_save_result)
        self._models_fetched.connect(self._on_models_fetched)
        self._devices_fetched.connect(self._on_devices_fetched)
        self._build_ui()
        self._load_current()
        self._animate_open()

    def _style(self):
        return """
        QDialog {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0a0a10, stop:0.5 #0f0f18, stop:1 #0a0a12);
            color: #e8e8ec;
            border-radius: 18px;
            border: 1px solid rgba(80, 90, 140, 50);
        }
        QLabel {
            color: #e8e8ec;
            background: transparent;
            border: none;
        }
        QLabel#dialogTitle {
            font-size: 20px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: -0.3px;
        }
        QLabel#dialogSubtitle {
            font-size: 11px;
            color: #6a7294;
            letter-spacing: 0.2px;
        }
        QLabel#sectionTitle {
            font-size: 10px;
            font-weight: 700;
            color: #7a82a8;
            letter-spacing: 1.5px;
        }
        QLabel#fieldLabel {
            font-size: 11px;
            font-weight: 600;
            color: #8a90b0;
            letter-spacing: 0.3px;
        }
        QLabel#status {
            font-size: 11px;
            padding: 8px 12px;
            border-radius: 10px;
            font-weight: 500;
        }
        QFrame#divider {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.5 rgba(80, 90, 160, 80), stop:1 transparent);
            max-height: 1px;
            border: none;
        }
        QFrame#sectionCard {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(25, 25, 40, 200), stop:1 rgba(18, 18, 28, 180));
            border: 1px solid rgba(70, 80, 130, 50);
            border-radius: 14px;
        }
        QFrame#sectionCard:hover {
            border: 1px solid rgba(90, 100, 160, 90);
        }
        """

    def _build_ui(self):
        from PyQt6.QtWidgets import QScrollArea, QWidget

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (sabit üst kısım)
        header_widget = QWidget()
        header_widget.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(28, 20, 28, 12)
        header_layout.setSpacing(12)
        icon_label = QLabel("⚡")
        icon_label.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        header_layout.addWidget(icon_label)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Kyros Ayarları")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("API, model ve ses aygıt yapılandırması")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box, 1)
        root.addWidget(header_widget)

        # Divider
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        root.addWidget(line)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(30, 30, 50, 100);
                width: 8px;
                border-radius: 4px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 110, 180, 120);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(100, 110, 180, 180);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent; border: none;")
        content = QVBoxLayout(content_widget)
        content.setContentsMargins(28, 16, 28, 16)
        content.setSpacing(12)

        # API Key Section Card
        api_card = QFrame()
        api_card.setObjectName("sectionCard")
        api_card_layout = QVBoxLayout(api_card)
        api_card_layout.setContentsMargins(16, 14, 16, 14)
        api_card_layout.setSpacing(8)

        api_section_title = QLabel("API ANAHTARI")
        api_section_title.setObjectName("sectionTitle")
        api_card_layout.addWidget(api_section_title)

        api_desc = QLabel("Gemini API erişimi için anahtarınızı girin")
        api_desc.setStyleSheet("font-size: 10px; color: #5a6080; padding: 0 0 4px 0; border: none;")
        api_card_layout.addWidget(api_desc)

        api_row = QHBoxLayout()
        api_row.setSpacing(8)
        self.api_input = ModernLineEdit()
        self.api_input.setPlaceholderText("AIza... veya AQ. ile başlar")
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.setClearButtonEnabled(True)
        api_row.addWidget(self.api_input, 1)
        self.toggle_btn = ModernButton("Göster", "ghost")
        self.toggle_btn.setFixedSize(72, 38)
        self.toggle_btn.clicked.connect(self._toggle_api)
        api_row.addWidget(self.toggle_btn)
        api_card_layout.addLayout(api_row)
        content.addWidget(api_card)

        # Model Section Card
        model_card = QFrame()
        model_card.setObjectName("sectionCard")
        model_card_layout = QVBoxLayout(model_card)
        model_card_layout.setContentsMargins(16, 14, 16, 14)
        model_card_layout.setSpacing(8)

        model_section_title = QLabel("VOICE-NATIVE MODEL")
        model_section_title.setObjectName("sectionTitle")
        model_card_layout.addWidget(model_section_title)

        model_desc = QLabel("Sadece listedeki modeller çalışır — API ile doğrulanmış")
        model_desc.setStyleSheet("font-size: 10px; color: #5a6080; padding: 0 0 4px 0; border: none;")
        model_card_layout.addWidget(model_desc)

        self.model_combo = ModernComboBox()
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
        model_card_layout.addWidget(self.model_combo)
        content.addWidget(model_card)

        # Audio Devices Section Card
        audio_card = QFrame()
        audio_card.setObjectName("sectionCard")
        audio_card_layout = QVBoxLayout(audio_card)
        audio_card_layout.setContentsMargins(16, 14, 16, 14)
        audio_card_layout.setSpacing(8)

        audio_header = QHBoxLayout()
        audio_section_title = QLabel("SES AYGITLARI")
        audio_section_title.setObjectName("sectionTitle")
        audio_header.addWidget(audio_section_title)
        audio_header.addStretch()
        self.spinner = LoadingSpinner()
        audio_header.addWidget(self.spinner)
        self.refresh_devices_btn = ModernButton("↻ Yenile", "ghost")
        self.refresh_devices_btn.setFixedSize(80, 30)
        self.refresh_devices_btn.setToolTip("Mevcut ses aygıtlarını yeniden listele")
        self.refresh_devices_btn.clicked.connect(self._refresh_devices_async)
        audio_header.addWidget(self.refresh_devices_btn)
        audio_card_layout.addLayout(audio_header)

        audio_desc = QLabel("Varsayılan olarak sistem aygıtları kullanılır")
        audio_desc.setStyleSheet("font-size: 10px; color: #5a6080; padding: 0 0 4px 0; border: none;")
        audio_card_layout.addWidget(audio_desc)

        # Input Device
        input_label = QLabel("GİRİŞ (Mikrofon)")
        input_label.setObjectName("fieldLabel")
        audio_card_layout.addWidget(input_label)
        self.input_combo = ModernComboBox()
        audio_card_layout.addWidget(self.input_combo)

        # Output Device
        output_label = QLabel("ÇIKIŞ (Hoparlör)")
        output_label.setObjectName("fieldLabel")
        audio_card_layout.addWidget(output_label)
        self.output_combo = ModernComboBox()
        audio_card_layout.addWidget(self.output_combo)
        content.addWidget(audio_card)

        content.addStretch()
        scroll.setWidget(content_widget)
        root.addWidget(scroll, 1)

        # Status (sabit alt kısım)
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("background: transparent; border: none;")
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(28, 0, 28, 16)
        bottom_layout.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        bottom_layout.addWidget(self.status_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.test_btn = ModernButton("Test Et", "secondary")
        self.test_btn.setToolTip("API + model gerçekten çalışıyor mu kontrol et")
        self.test_btn.clicked.connect(self._on_test)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        self.save_btn = ModernButton("Kaydet ve Uygula", "primary")
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        bottom_layout.addLayout(btn_row)

        # Hint
        hint = QLabel("Değişiklikler anında aktif olur • Geçersiz API uyarı verir")
        hint.setStyleSheet("color: #4a5070; font-size: 10px; background: transparent; border: none; letter-spacing: 0.2px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom_layout.addWidget(hint)

        root.addWidget(bottom_widget)

        # Store cards for animation
        self._cards = [api_card, model_card, audio_card]

    def _animate_open(self):
        """Staggered fade-in animation for all cards."""
        from PyQt6.QtCore import QSequentialAnimationGroup, QEasingCurve
        self._fade_group = QSequentialAnimationGroup(self)
        for card in self._cards:
            card.setWindowOpacity(0.0)
            anim = QPropertyAnimation(card, b"windowOpacity")
            anim.setDuration(350)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade_group.addAnimation(anim)
        self._fade_group.start()

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
            # Ses aygıtlarını arka planda listele
            self._refresh_devices_async()
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

    def _refresh_devices_async(self):
        self.refresh_devices_btn.setEnabled(False)
        self.spinner.start()
        def run():
            try:
                from core.audio_io import list_audio_devices
                devices = list_audio_devices()
                self._devices_fetched.emit(devices)
            except Exception:
                self._devices_fetched.emit({"input_devices": [], "output_devices": []})
        threading.Thread(target=run, daemon=True).start()

    def _on_devices_fetched(self, devices):
        self.refresh_devices_btn.setEnabled(True)
        self.spinner.stop()
        self._input_devices = devices.get("input_devices", [])
        self._output_devices = devices.get("output_devices", [])
        self._populate_device_combos()

    def _populate_device_combos(self):
        try:
            import config
            cur_input = str(getattr(config, "AUDIO_INPUT_DEVICE", "") or "")
            cur_output = str(getattr(config, "AUDIO_OUTPUT_DEVICE", "") or "")
        except Exception:
            cur_input, cur_output = "", ""

        self.input_combo.clear()
        self.input_combo.addItem("Varsayılan (Sistem)", "")
        for dev in self._input_devices:
            name = dev.get("name", "Unknown")
            dev_id = str(dev.get("id", ""))
            is_default = dev.get("is_default", False)
            display = f"● {name}" if is_default else f"  {name}"
            self.input_combo.addItem(display, dev_id)
        if cur_input:
            idx = self.input_combo.findData(cur_input)
            if idx >= 0:
                self.input_combo.setCurrentIndex(idx)

        self.output_combo.clear()
        self.output_combo.addItem("Varsayılan (Sistem)", "")
        for dev in self._output_devices:
            name = dev.get("name", "Unknown")
            dev_id = str(dev.get("id", ""))
            is_default = dev.get("is_default", False)
            display = f"● {name}" if is_default else f"  {name}"
            self.output_combo.addItem(display, dev_id)
        if cur_output:
            idx = self.output_combo.findData(cur_output)
            if idx >= 0:
                self.output_combo.setCurrentIndex(idx)

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
            "info": "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(30, 35, 60, 200), stop:1 rgba(25, 30, 50, 180)); color: #8090c0; border: 1px solid rgba(80, 100, 180, 60);",
            "success": "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(15, 50, 30, 220), stop:1 rgba(10, 40, 25, 200)); color: #7ee0a0; border: 1px solid rgba(80, 200, 120, 60);",
            "error": "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(60, 15, 20, 220), stop:1 rgba(50, 10, 15, 200)); color: #ff8a8a; border: 1px solid rgba(200, 80, 80, 60);",
        }
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"QLabel#status {{ {colors.get(kind, colors['info'])} border-radius: 10px; padding: 8px 12px; font-size: 11px; }}")
        # Animate in
        self.status_label.setWindowOpacity(0.0)
        self.status_label.show()
        self._status_anim = QPropertyAnimation(self.status_label, b"windowOpacity")
        self._status_anim.setDuration(300)
        self._status_anim.setStartValue(0.0)
        self._status_anim.setEndValue(1.0)
        self._status_anim.start()

    def _on_test_result(self, ok, msg):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test Et")
        self._set_status(msg, "success" if ok else "error")

    def _on_save_result(self, ok, msg):
        self._handle_save_after_validate(
            self.api_input.text().strip(),
            self.model_combo.currentText().strip(),
            ok, msg
        )

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
            input_device = self.input_combo.currentData() or ""
            output_device = self.output_combo.currentData() or ""
            config.save_config(
                api_key=api if api else None,
                model=model,
                input_device=input_device,
                output_device=output_device,
            )
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


def _make_statusbar_handler(panel):
    """pyobjc NSObject subclass ile statusbar handler olustur."""
    import objc
    from AppKit import NSObject

    class StatusBarHandler(NSObject):
        panel = objc.ivar('panel')

        @objc.selector(signature=b"v@:@")
        def click_(self, sender):
            try:
                if self.panel._panel_visible:
                    self.panel._hide_panel()
                else:
                    self.panel.slide_in()
            except Exception:
                pass

        @objc.selector(signature=b"v@:@")
        def togglePanel_(self, sender):
            try:
                if self.panel._panel_visible:
                    self.panel._hide_panel()
                else:
                    self.panel.slide_in()
            except Exception:
                pass

        @objc.selector(signature=b"v@:@")
        def openSettings_(self, sender):
            try:
                QTimer.singleShot(0, self.panel._open_api_settings)
            except Exception:
                pass

        @objc.selector(signature=b"v@:@")
        def quitApp_(self, sender):
            try:
                QTimer.singleShot(0, QApplication.instance().quit)
            except Exception:
                pass

    handler = StatusBarHandler.alloc().init()
    handler.panel = panel
    return handler


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
        self._panel_visible = False

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
        self._init_timer()
        self._setup_statusbar_item()
        self.setToolTip(
            "Tıkla: konuşma ve kontroller · Sağ tık: durdur / bekleme / mikrofon · ⚙: API / model"
        )
        QTimer.singleShot(900, self._check_api_on_startup)

    def bind(self, gemini):
        gemini.on_state_change = self.signals.mode.emit
        gemini.on_mic_level = self.signals.level.emit
        gemini.on_text = self.signals.text.emit
        gemini.on_error = self.signals.error.emit
        gemini.on_tool = self.signals.tool.emit
        gemini.on_sources = self.signals.sources.emit

    def _add_text(self, who, text):
        # Chat penceresi kaldırıldı — sadece log
        if who == "Hata":
            self.setToolTip(text)

    def _add_sources(self, sources):
        pass  # Chat penceresi kaldırıldı

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

    def _setup_statusbar_item(self):
        """Menubar'da status bar item olustur (Textream gibi)."""
        try:
            import objc
            from AppKit import NSStatusBar, NSImage, NSMenu, NSMenuItem

            self._statusbar = NSStatusBar.systemStatusBar()
            self._statusitem = self._statusbar.statusItemWithLength_(-2)

            img = NSImage.imageNamed_("NSComputer")
            img.setSize_((18, 18))
            img.setTemplate_(True)
            self._statusitem.button().setImage_(img)
            self._statusitem.button().setToolTip_("Kyros Asistani")

            handler = _make_statusbar_handler(self)
            self._statusbar_handler = handler

            self._statusitem.button().setTarget_(handler)
            self._statusitem.button().setAction_(objc.selector(handler.click_, signature=b"v@:@"))

            menu = NSMenu.alloc().init()

            toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Paneli Goster/Gizle", "togglePanel:", ""
            )
            toggle_item.setTarget_(handler)
            toggle_item.setAction_(objc.selector(handler.togglePanel_, signature=b"v@:@"))
            menu.addItem_(toggle_item)

            menu.addItem_(NSMenuItem.separatorItem())

            settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Ayarlar", "openSettings:", ""
            )
            settings_item.setTarget_(handler)
            settings_item.setAction_(objc.selector(handler.openSettings_, signature=b"v@:@"))
            menu.addItem_(settings_item)

            menu.addItem_(NSMenuItem.separatorItem())

            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Cikis", "quitApp:", ""
            )
            quit_item.setTarget_(handler)
            quit_item.setAction_(objc.selector(handler.quitApp_, signature=b"v@:@"))
            menu.addItem_(quit_item)

            self._statusitem.setMenu_(menu)

        except Exception as e:
            logging.getLogger("kyros").warning("Status bar item olusturulamadi: %s", e)

    def _check_api_on_startup(self):
        try:
            import config

            if not getattr(config, "GEMINI_API_KEY", ""):
                self._add_text("Sistem", "API anahtarı yok — menubar ⚙ ile Gemini API ekleyin.")
                QTimer.singleShot(400, self._open_api_settings)
        except Exception:
            pass

    def _open_api_settings(self):
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
                        logging.getLogger("kyros").error("Panel restart failed: %s", e)
                threading.Thread(target=restart, daemon=True).start()
                self._add_text("Sistem", f"Model: {new_model}" + (" · API güncellendi" if new_api else ""))
        except Exception as e:
            logging.getLogger("kyros").error("_apply_api_change failed: %s", e)

    def _init_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def slide_in(self):
        self.show()
        self._panel_visible = True
        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(300)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - PANEL_W) // 2
        notch_y = self._detect_notch_bottom()
        self._slide_anim.setStartValue(QPoint(x, -PANEL_H))
        self._slide_anim.setEndValue(QPoint(x, notch_y))
        self._slide_anim.start()
        self._fix_macos_window()

    def _hide_panel(self):
        self._panel_visible = False
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - PANEL_W) // 2
        self._hide_anim = QPropertyAnimation(self, b"pos")
        self._hide_anim.setDuration(250)
        self._hide_anim.setStartValue(self.pos())
        self._hide_anim.setEndValue(QPoint(x, -PANEL_H))
        self._hide_anim.start()
        self._hide_anim.finished.connect(self.hide)

    def _has_dynamic_island(self):
        """Dynamic Island (çentik) olup olmadığını tespit et.
        NSScreen.safeAreaInsets.top > 0 veya auxiliaryTopLeftArea/RightArea mevcutsa
        Dynamic Island vardır."""
        try:
            from AppKit import NSScreen
            ns_screen = NSScreen.mainScreen()
            if ns_screen is None:
                return False, 0
            safe_insets = ns_screen.safeAreaInsets()
            if safe_insets.top > 0:
                return True, int(safe_insets.top)
            left_area = ns_screen.auxiliaryTopLeftArea()
            right_area = ns_screen.auxiliaryTopRightArea()
            if left_area is not None and right_area is not None:
                notch_height = ns_screen.frame().size.height - ns_screen.visibleFrame().size.height
                if notch_height > 0:
                    return True, int(notch_height)
        except Exception:
            pass
        return False, 0

    def _detect_notch_bottom(self):
        """Dynamic Island / menubar alt kenarını tespit et.
        Dynamic Island varsa safeAreaInsets.top, yoksa visibleFrame.origin.y kullanır."""
        try:
            from AppKit import NSScreen
            ns_screen = NSScreen.mainScreen()
            if ns_screen is None:
                screen = QApplication.primaryScreen().availableGeometry()
                return screen.y()
            safe_insets = ns_screen.safeAreaInsets()
            if safe_insets.top > 0:
                return int(safe_insets.top)
            visible = ns_screen.visibleFrame()
            return int(visible.origin.y)
        except Exception:
            pass
        screen = QApplication.primaryScreen().availableGeometry()
        return screen.y()

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
            logging.getLogger("kyros").warning("macOS window fix failed: %s", e)

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
        # Daha opak arka plan (240/255 ≈ %94)
        p.setBrush(QColor(14, 14, 20, 240))
        p.drawRoundedRect(QRectF(0, 0, PANEL_W, PANEL_H), 20, 20)
        # Daha belirgin kenarlık
        border_pen = QPen(QColor(100, 110, 180, 120), 1.5)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0, 0, PANEL_W, PANEL_H), 20, 20)
        # Dış glow efekti
        glow_pen = QPen(QColor(80, 90, 200, 40), 3)
        p.setPen(glow_pen)
        p.drawRoundedRect(QRectF(-1, -1, PANEL_W + 2, PANEL_H + 2), 21, 21)
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
            # Daha canlı orb'lar (alpha 120/90/50)
            grad.setColorAt(0, QColor(int(c[0]), int(c[1]), int(c[2]), 120))
            grad.setColorAt(0.5, QColor(int(c[0]), int(c[1]), int(c[2]), 90))
            grad.setColorAt(1.0, QColor(int(c[0]), int(c[1]), int(c[2]), 50))
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

            brightness = 0.3 + (h / bar_h) * 0.65
            alpha = int(brightness * 255)
            alpha = min(alpha, 230)

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

        p.setPen(QColor(255, 255, 255, 180))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawText(QPointF(lx, ly + th - 2), label)
        p.restore()

    def mousePressEvent(self, event):
        # çarkın üstüne tıklanırsa ayar aç, panele düşmesin
        if hasattr(self, "_gear_btn") and self._gear_btn.geometry().contains(event.pos()):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pass  # Sol tık - sadece görsel, pencere açma
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
            menu.addAction("Çıkış", QApplication.instance().quit)
            menu.exec(event.globalPosition().toPoint())

    def _toggle_mic(self):
        self._mic_muted = not self._mic_muted
        self.kyros.set_mic_muted(self._mic_muted)

    def closeEvent(self, event):
        if self.kyros and hasattr(self.kyros, "stop"):
            self.kyros.stop()
        event.accept()
        QApplication.instance().quit()

    def close(self):
        self.timer.stop()
        super().close()
