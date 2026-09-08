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
    handler = RotatingFileHandler(
        folder / "kyros.log", maxBytes=1_000_000, backupCount=3
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log = logging.getLogger("kyros")
    log.setLevel(logging.DEBUG if debug else logging.INFO)
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler())


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
        print(
            "Kyros uygulaması macOS içindir. Yerel testler: python3 -m unittest discover -s tests -v"
        )
        return 1
    if not config.GEMINI_API_KEY and (args.text or args.no_panel):
        print("Gemini API anahtarı eksik. Paneli açıp sağ üst ⚙ ile ekleyin veya bash install.sh çalıştırın.")
        return 1
    if not config.GEMINI_API_KEY:
        print("API anahtarı yok — panel açılacak, sağ üst ⚙ ile ekleyin.")
    configure_logging(args.debug)
    kyros = Kyros(args.debug, args.text, args.audio_backend)
    if args.text or args.no_panel:
        kyros.gemini.on_state_change = lambda mode: print(f"[KYROS] {mode}", flush=True)
        kyros.gemini.on_text = lambda who, text: print(f"{who}: {text}", flush=True)
        kyros.gemini.on_error = lambda error: print(f"[HATA] {error}", flush=True)
        kyros.gemini.on_sources = lambda sources: print(
            "Kaynaklar:", sources, flush=True
        )
        signal.signal(signal.SIGTERM, lambda *_: kyros.stop())
        try:
            kyros.start()
            if args.text:
                while kyros.gemini.is_running and not kyros.gemini.connected:
                    time.sleep(0.05)
                print('"Hey Kyros" yaz. Çıkış: Ctrl+C veya Ctrl+D.')
                while kyros.gemini.is_running:
                    value = input("> ")
                    kyros.send_text(value)
            else:
                while kyros.gemini.is_running:
                    time.sleep(0.1)
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            kyros.stop()
        return 0

    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        from gui.panel import KyrosPanel
    except ModuleNotFoundError as exc:
        print(
            f"Eksik bağımlılık: {exc.name}. Proje klasöründe bash install.sh çalıştırın."
        )
        return 1

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
