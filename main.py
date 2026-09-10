#!/usr/bin/env python3
"""Kyros macOS live assistant."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys
import time
from pathlib import Path
from core.bootstrap import use_project_environment

if __name__ == "__main__":
    use_project_environment(Path(__file__).resolve().parent)

import config
from core.gemini_live import GeminiLive


# ─── Renkli Log Formatı ──────────────────────────────────────────────
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


class ColorFormatter(logging.Formatter):
    """Terminal için renkli log formatı."""

    def format(self, record):
        levelname = record.levelname
        color = COLORS.get(levelname, "")
        module = record.module
        msg = record.getMessage()
        ts = self.formatTime(record, "%H:%M:%S")

        if levelname == "ERROR":
            icon = f"{color}{BOLD}✗"
            prefix = f"{icon} {levelname}{RESET}"
        elif levelname == "WARNING":
            prefix = f"{color}⚠ {levelname}{RESET}"
        elif levelname == "DEBUG":
            prefix = f"{color}{DIM}▸ {levelname}{RESET}"
        else:
            prefix = f"{color}● {levelname}{RESET}"

        return f"{DIM}{ts}{RESET} {prefix} {DIM}[{module}]{RESET} {msg}"


BANNER = f"""
{BOLD}{COLORS['INFO']}  ╭───────────────────────────────────────╮
  │            ◉  KYROS  v3.0               │
  │       Canlı Ses Asistanı — macOS         │
  ╰───────────────────────────────────────╯{RESET}
{DIM}  Python {sys.version.split()[0]} • Ctrl+C ile çıkış{RESET}
"""


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

    # Dosya handler'ı (renksiz, detaylı)
    file_handler = RotatingFileHandler(
        folder / "kyros.log", maxBytes=1_000_000, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(module)s.%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Terminal handler'ı (renkli, düzenli)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(ColorFormatter())

    log = logging.getLogger("kyros")
    log.setLevel(logging.DEBUG if debug else logging.INFO)
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
        print("Gemini API anahtarı eksik. Paneli açıp sağ üst ⚙ ile ekleyin.")
        return 1

    configure_logging(args.debug)
    log = logging.getLogger("kyros")

    if not config.GEMINI_API_KEY:
        log.warning("API anahtarı yok — panel açılacak, sağ üst ⚙ ile ekleyin.")
    else:
        print(BANNER)

    kyros = Kyros(args.debug, args.text, args.audio_backend)

    if args.text or args.no_panel:
        log.info("Metin modu başlatılıyor...")
        kyros.gemini.on_state_change = lambda mode: log.info("Durum: %s", mode)
        kyros.gemini.on_text = lambda who, text: print(f"  {who}: {text}")
        kyros.gemini.on_error = lambda error: log.error(error)
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
            log.info("Kullanıcı çıkışı")
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

    log.info("Panel modu başlatılıyor...")
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
