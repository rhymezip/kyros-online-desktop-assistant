"""Credentials live in ignored config/local.json or the environment."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "config/local.json"
_local = json.loads(LOCAL.read_text()) if LOCAL.exists() else {}
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", _local.get("GEMINI_API_KEY", ""))
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL", _local.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")
)

# Sadece voice-native (Live) modeller — panelden seçilir, gerçekten çalışanlar (API'den doğrulandı)
# Fallback liste — API girilince dinamik olarak yenilenir (bidiGenerateContent destekleyenler)
VOICE_NATIVE_MODELS = [
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-09-2025",
]


def fetch_voice_models(api_key, timeout=8):
    """API ile /v1beta/models listesini çekip bidiGenerateContent destekleyen voice-native'leri döndürür."""
    if not api_key or len(api_key.strip()) < 20:
        return list(VOICE_NATIVE_MODELS)
    try:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            out = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if name.startswith("models/"):
                    name = name[7:]
                methods = m.get("supportedGenerationMethods", [])
                # sadece Live (bidi) destekleyenler
                if "bidiGenerateContent" in methods:
                    # voice-native olanlar: native-audio veya live-transcribe
                    if "native-audio" in name or "transcribe" in name or "live" in name:
                        out.append(name)
            # native-audio olanları öne al
            out.sort(key=lambda x: (0 if "native-audio-latest" in x else 1 if "native-audio" in x else 2))
            return out if out else list(VOICE_NATIVE_MODELS)
    except Exception:
        return list(VOICE_NATIVE_MODELS)


def save_config(api_key=None, model=None):
    """local.json'a yazar ve bellekteki GEMINI_*'ı günceller. None ise değiştirmez."""
    global GEMINI_API_KEY, GEMINI_MODEL, _local
    data = {}
    if LOCAL.exists():
        try:
            data = json.loads(LOCAL.read_text())
        except Exception:
            data = {}
    if api_key is not None:
        api_key = api_key.strip()
        if api_key:
            data["GEMINI_API_KEY"] = api_key
            GEMINI_API_KEY = api_key
        else:
            data.pop("GEMINI_API_KEY", None)
            GEMINI_API_KEY = ""
    if model is not None:
        model = model.strip()
        if model:
            data["GEMINI_MODEL"] = model
            GEMINI_MODEL = model
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    try:
        LOCAL.chmod(0o600)
    except Exception:
        pass
    _local = dict(data)
    # config paketi `from .settings import *` ile kopya tuttuğu için senkronize et
    try:
        import sys as _sys

        if "config" in _sys.modules:
            _sys.modules["config"].GEMINI_API_KEY = GEMINI_API_KEY
            _sys.modules["config"].GEMINI_MODEL = GEMINI_MODEL
            _sys.modules["config"]._local = _local
        if "config.settings" in _sys.modules:
            _sys.modules["config.settings"].GEMINI_API_KEY = GEMINI_API_KEY
            _sys.modules["config.settings"].GEMINI_MODEL = GEMINI_MODEL
    except Exception:
        pass
    return True


def validate_api_key(api_key, model=None, timeout=8):
    """Gerçek Gemini API'ye küçük bir istek atar. (model verilirse o model test edilir)
    Returns (ok: bool, message: str)"""
    if not api_key or len(api_key.strip()) < 20:
        return False, "API anahtarı çok kısa."
    api_key = api_key.strip()
    # 1) Genel anahtar geçerliliği: models list
    try:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            data = json.loads(body)
            if "models" not in data:
                return False, "API yanıtı beklenmedik."
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            err = json.loads(body).get("error", {}).get("message", body[:200])
        except Exception:
            err = str(e)
        if e.code in (400, 403):
            return False, f"API reddedildi ({e.code}): {err[:120]}"
        return False, f"API hatası ({e.code}): {err[:120]}"
    except Exception as e:
        return False, f"Ağ hatası: {e}"
    # 2) Model var mı?
    if model:
        model = model.strip()
        if model.startswith("models/"):
            model = model[7:]
        try:
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}?key={api_key}",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                return True, f"Model hazır: {data.get('displayName', model)}"
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode()
                err = json.loads(body).get("error", {}).get("message", body[:200])
            except Exception:
                err = str(e)
            if e.code == 404:
                return False, f"Model bulunamadı: {model} — {err[:100]}"
            return False, f"Model hatası ({e.code}): {err[:120]}"
        except Exception as e:
            return False, f"Model kontrol ağı hatası: {e}"
    return True, "API geçerli."


AUDIO_BACKEND = os.environ.get("KYROS_AUDIO_BACKEND", "native")
SILENCE_DURATION_MS = 350
TOOL_TIMEOUT = 60
MAX_TOOL_TIMEOUT = 300
MAX_TOOL_OUTPUT = 24000
MAX_AUDIO_BUFFER_SECONDS = 30
# Gate mic while TTS is playing to avoid self-echo interrupting without AEC (Intel fallback)
MIC_GATE_RMS = 1100
MIC_GATE_HANGOVER_MS = 400
MIC_GATE_BLOCK_MS = 600
