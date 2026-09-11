"""Read-only installation checks; no Gemini calls or system mutations."""

import importlib.util
import platform
import subprocess
import sys
import config


def audio_check(backend=None):
    binary = config.ROOT / "native/kyros-audio"
    if sys.platform == "linux":
        from core.linux_audio import check_pipewire_audio, check_portaudio_audio

        backend = backend or config.AUDIO_BACKEND
        if backend == "portaudio":
            print("PortAudio ses motoru deneniyor; Gemini'ye bağlanılmıyor.", flush=True)
            ok, detail = check_portaudio_audio(
                input_device_id=config.AUDIO_INPUT_DEVICE or None
            )
        else:
            print("PipeWire ses motoru deneniyor; Gemini'ye bağlanılmıyor.", flush=True)
            ok, detail = check_pipewire_audio(
                input_device_id=config.AUDIO_INPUT_DEVICE or None
            )
        print(detail)
        return 0 if ok else 1
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

    if sys.platform == "darwin":
        check("macOS", True, platform.platform())
    elif sys.platform == "linux":
        check("Linux", True, platform.platform())
    else:
        check("Desteklenen platform", False, platform.platform())
    check("Python 3.10+", sys.version_info >= (3, 10), platform.python_version())
    check(
        "Gemini anahtarı",
        bool(config.GEMINI_API_KEY),
        "Anahtar gösterilmez; geçerliliği API ile test edilmedi.",
    )
    print("Ses modeli:", config.GEMINI_MODEL)
    if sys.platform == "darwin":
        required_modules = ("websockets", "PyQt6", "numpy", "sounddevice", "PIL")
    else:
        required_modules = ("websockets", "PyQt6", "PIL")
    for module in required_modules:
        check(module, importlib.util.find_spec(module) is not None)
    if sys.platform == "linux":
        for module in ("numpy", "sounddevice"):
            if importlib.util.find_spec(module) is None:
                print(f"BİLGİ: {module} — PipeWire için zorunlu değil; PortAudio fallbackinde gerekir.")
        from core.linux_ui import capabilities

        caps = capabilities()
        session = caps["session"]
        check(
            "Wayland/Hyprland oturumu",
            bool(session["wayland_display"] and session["compositor"] == "Hyprland"),
            f"{session['compositor']} / {session['session_type']}",
        )
        check(
            "PipeWire giriş/çıkış araçları",
            caps["audio"]["pipewire"],
            "pw-record + pw-play gerekir; PortAudio fallback seçilebilir.",
        )
        check(
            "Ekran görüntüsü",
            bool(caps["screen"]["grim"] or caps["screen"]["portal_screenshot"]),
            "grim veya çalışan XDG Screenshot portalı gerekir.",
        )
        check(
            "Klavye girdisi",
            bool(
                caps["keyboard"]["wtype"]
                or caps["keyboard"]["ydotool"]
                or caps["keyboard"]["hyprland_sendshortcut"]
                or caps["keyboard"]["xdotool"]
                or caps["keyboard"]["xdg_remote_desktop"]
            ),
            "wtype, ydotool, Hyprland sendshortcut veya xdotool gerekir.",
        )
        check(
            "Mouse girdisi",
            bool(
                caps["pointer"]["ydotool"]
                or caps["pointer"]["xdotool"]
                or caps["pointer"]["xdg_remote_desktop"]
            ),
            "Wayland için ydotool/ydotoold veya XDG Remote Desktop, X11 için xdotool gerekir.",
        )
        check(
            "AT-SPI2 bindings",
            caps["accessibility"]["atspi2"],
            "python-gobject + at-spi2-core gerekir; uygulama ayrıca erişilebilirlik ağacı sunmalıdır.",
        )
        check(
            "Clipboard backend",
            bool(
                caps["clipboard"]["wayland"]
                or caps["clipboard"]["xclip"]
                or caps["clipboard"]["xsel"]
            ),
            "wl-clipboard, xclip veya xsel gerekir.",
        )
        check(
            "Media control",
            caps["media"]["playerctl"],
            "playerctl gerekir; running MPRIS players are discovered at request time.",
        )
        print(
            "Linux notu: Wayland input enjeksiyonu dağıtım/portal politikasına bağlıdır; "
            "doctor yalnızca yerel capability durumunu gösterir."
        )
        return 0 if all(checks) else 1

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
