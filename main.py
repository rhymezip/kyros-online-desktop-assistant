#!/usr/bin/env python3
"""Kyros macOS live assistant."""

import argparse
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.bootstrap import use_project_environment

if __name__ == "__main__":
    use_project_environment(Path(__file__).resolve().parent)

import config
from core.gemini_live import GeminiLive

COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

LEVEL_LABELS = {
    "DEBUG": "DETAY",
    "INFO": "BİLGİ",
    "WARNING": "UYARI",
    "ERROR": "HATA",
    "CRITICAL": "KRİTİK",
}
COMPONENT_LABELS = {
    "kyros.app": "SİSTEM",
    "kyros.audio": "SES",
    "kyros.live": "CANLI",
    "kyros.tool": "ARAÇ",
    "kyros.ui": "ARAYÜZ",
}


class ColorFormatter(logging.Formatter):
    """Compact, readable terminal output with optional ANSI color."""

    def __init__(self, use_color=True):
        super().__init__()
        self.use_color = use_color

    def _paint(self, value, *styles):
        if not self.use_color:
            return value
        return "".join(styles) + value + RESET

    def format(self, record):
        levelname = record.levelname
        level = LEVEL_LABELS.get(levelname, levelname)
        component = COMPONENT_LABELS.get(
            record.name, record.name.removeprefix("kyros.").upper()
        )
        message = record.getMessage()
        ts = self.formatTime(record, "%H:%M:%S")
        color = COLORS.get(levelname, "")
        style = (color, BOLD) if levelname in ("ERROR", "CRITICAL") else (color,)
        prefix = "  ".join(
            (
                self._paint(ts, DIM),
                self._paint(f"{level:<6}", *style),
                self._paint(f"{component:<7}", DIM),
            )
        )
        continuation = " " * (8 + 2 + 6 + 2 + 7 + 2)
        return prefix + "  " + message.replace("\n", "\n" + continuation)


def banner(use_color=True):
    green = COLORS["INFO"] if use_color else ""
    bold = BOLD if use_color else ""
    dim = DIM if use_color else ""
    reset = RESET if use_color else ""
    return (
        f"\n{bold}{green}  ╭─ KYROS 3.0 ─────────────────────────╮\n"
        "  │ Canlı masaüstü asistanı              │\n"
        f"  ╰──────────────────────────────────────╯{reset}\n"
        f"{dim}  macOS • Python {sys.version.split()[0]} • Çıkış: Ctrl+C{reset}\n"
    )


class Kyros:
    def __init__(self, debug=False, text_only=False, audio_backend=None):
        self.gemini = GeminiLive(text_only=text_only, audio_backend=audio_backend)
        self.panel = None
        self.debug = debug

    def start(self):
        self.gemini.start()

    def stop(self):
        self.gemini.stop()

    def control(self, action):
        self.gemini.control(action)

    def send_text(self, text):
        self.gemini.send_text(text)

    def set_mic_muted(self, muted):
        self.gemini.set_mic_muted(muted)


def configure_logging(debug):
    folder = config.ROOT / "logs"
    folder.mkdir(exist_ok=True, mode=0o700)

    file_handler = RotatingFileHandler(
        folder / "kyros.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s:%(funcName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    stream_handler.setFormatter(
        ColorFormatter(use_color=stream_handler.stream.isatty())
    )

    log = logging.getLogger("kyros")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    for handler in log.handlers[:]:
        handler.close()
        log.removeHandler(handler)
    log.addHandler(file_handler)
    log.addHandler(stream_handler)


def main():
    parser = argparse.ArgumentParser(
        description="Kyros — canlı ses ve genel Mac erişimi"
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-panel", action="store_true")
    parser.add_argument(
        "--text",
        "--test",
        dest="text",
        action="store_true",
        help="Mikrofonsuz yazılı API denemesi",
    )
    parser.add_argument(
        "--audio-backend", choices=["native", "portaudio"], default=config.AUDIO_BACKEND
    )
    parser.add_argument(
        "--audio-check",
        action="store_true",
        help="Yerel ses motorunu API'ye bağlanmadan başlatıp kontrol eder",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Yerel kurulum/izin kontrolü; API çağrısı yapmaz",
    )
    args = parser.parse_args()
    if args.audio_check:
        from core.doctor import audio_check
        return audio_check()
    if args.doctor:
        from core.doctor import doctor
        return doctor()
    if sys.platform != "darwin":
        print("Kyros uygulaması macOS içindir.")
        return 1
    if not config.GEMINI_API_KEY and (args.text or args.no_panel):
        print("Gemini API anahtarı eksik. Paneli açıp sağ üstteki Ayarlar düğmesinden ekleyin.")
        return 1

    configure_logging(args.debug)
    log = logging.getLogger("kyros.app")

    if not config.GEMINI_API_KEY:
        log.warning("API anahtarı yok — panel açılacak, sağ üstteki Ayarlar düğmesinden ekleyin.")
    else:
        print(banner(sys.stdout.isatty()))

    kyros = Kyros(args.debug, args.text, args.audio_backend)

    if args.text or args.no_panel:
        log.info("Metin modu hazırlanıyor.")
        kyros.gemini.on_text = lambda who, text: print(f"  {who}: {text}")
        kyros.gemini.on_sources = lambda sources: log.debug("Kaynaklar: %s", sources)
        signal.signal(signal.SIGTERM, lambda *_: kyros.stop())
        try:
            kyros.start()
            if args.text:
                while kyros.gemini.is_running and not kyros.gemini.connected:
                    time.sleep(0.05)
                print(f"\n{DIM}Komut bekleniyor... Çıkış: Ctrl+C{RESET}\n")
                while kyros.gemini.is_running:
                    try:
                        value = input(f"{COLORS['INFO']}› {RESET}")
                        if value.strip():
                            kyros.send_text(value)
                    except EOFError:
                        break
            else:
                while kyros.gemini.is_running:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            log.info("Kyros kapatılıyor.")
        finally:
            kyros.stop()
        return 0

    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        from gui.panel import KyrosPanel
    except ModuleNotFoundError as exc:
        log.error("Eksik bağımlılık: %s. bash install.sh çalıştırın.", exc.name)
        return 1

    log.info("Arayüz hazırlanıyor.")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    panel = KyrosPanel(kyros)
    kyros.panel = panel
    panel.bind(kyros.gemini)
    app.aboutToQuit.connect(kyros.stop)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)
    panel.slide_in()
    QTimer.singleShot(400, panel._fix_macos_window)
    QTimer.singleShot(0, kyros.start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
