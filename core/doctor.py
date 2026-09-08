"""Read-only installation checks; no Gemini calls or system mutations."""

import importlib.util
import platform
import subprocess
import sys
import config


def audio_check():
    binary = config.ROOT / "native/kyros-audio"
    if sys.platform != "darwin" or not binary.exists():
        print("Mac üzerinde önce bash build_audio.sh çalıştırın.")
        return 1
    print("Yerel ses motoru deneniyor; Gemini'ye bağlanılmıyor.", flush=True)
    import os

    args = [str(binary), "--check"]
    # Avoid VP fallback delay on Intel where VP is known to produce no audio
    if os.environ.get("KYROS_NO_VP") == "1" or platform.machine() == "x86_64":
        args.append("--no-vp")
    try:
        result = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            timeout=65,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print(
            "Ses kontrolü zaman aşımına uğradı. Mikrofon izin penceresini kontrol edin."
        )
        return 1


def doctor():
    checks = []

    def check(name, ok, detail=""):
        checks.append(bool(ok))
        print(f"{'OK' if ok else 'EKSİK'}: {name}" + (f" — {detail}" if detail else ""))

    check("macOS", sys.platform == "darwin", platform.platform())
    check("Python 3.10+", sys.version_info >= (3, 10), platform.python_version())
    check(
        "Gemini anahtarı",
        bool(config.GEMINI_API_KEY),
        "Anahtar gösterilmez; geçerliliği API ile test edilmedi.",
    )
    print("Ses modeli:", config.GEMINI_MODEL)
    for module in ("websockets", "PyQt6", "numpy", "sounddevice", "PIL"):
        check(module, importlib.util.find_spec(module) is not None)
    binary = config.ROOT / "native/kyros-audio"
    check(
        "Yerel ses motoru",
        binary.exists(),
        "bash install.sh ile Mac üzerinde derlenir.",
    )
    if sys.platform == "darwin":
        if binary.exists():
            subprocess.run(
                [str(binary), "--diagnose"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                timeout=10,
            )
        try:
            import ApplicationServices as AX
            import Quartz as Q

            check("Erişilebilirlik izni", AX.AXIsProcessTrusted())
            check("Ekran Kaydı izni", Q.CGPreflightScreenCaptureAccess())
        except ImportError as exc:
            check("macOS köprüsü", False, str(exc))
        print(
            "Mikrofon izni ses motoru ilk açıldığında; uygulama Otomasyon izinleri ilk kullanımda sorulur."
        )
    return 0 if all(checks) else 1
