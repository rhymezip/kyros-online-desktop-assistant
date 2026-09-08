#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
    echo "Bu kurulum Mac üzerinde çalıştırılmalı."
    exit 1
fi
if ! xcrun --find swiftc >/dev/null 2>&1; then
    echo "Apple Command Line Tools eksik. xcode-select --install çalıştırıp kurulumdan sonra tekrar deneyin."
    exit 1
fi
KYROS_PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(not ((3,10) <= sys.version_info[:2] <= (3,14)))'; then
        KYROS_PYTHON="$(command -v "$candidate")"
        break
    fi
done
if [[ -z "$KYROS_PYTHON" ]]; then
    echo "Python 3.10–3.14 gerekiyor. Önerilen: Python 3.12."
    exit 1
fi
if [[ ! -x venv/bin/python ]]; then
    "$KYROS_PYTHON" -m venv venv
fi
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
venv/bin/python - <<'PY'
import getpass, json, os
from pathlib import Path
p = Path('config/local.json')
settings = json.loads(p.read_text()) if p.exists() else {}
if not os.environ.get('GEMINI_API_KEY') and not settings.get('GEMINI_API_KEY'):
    key = getpass.getpass('Gemini API anahtarı: ').strip()
    if not key:
        raise SystemExit('API anahtarı girilmedi.')
    settings['GEMINI_API_KEY'] = key
    p.write_text(json.dumps(settings, indent=2) + '\n')
    p.chmod(0o600)
print('Gemini anahtarı hazır; mevcut ses modeli korunuyor.')
PY
bash build_audio.sh
venv/bin/python -m unittest discover -s tests -v
echo "Kurulum tamamlandı."
echo "Çalıştır: venv/bin/python main.py  (veya python3 main.py)"
echo "İsteğe bağlı .app paketi için: bash create_app_bundle.sh && open Kyros.app"
echo "İlk kullanımda Mikrofon, Erişilebilirlik, Ekran Kaydı ve uygulama Otomasyon izinlerini verin."
echo "Durum kontrolü: venv/bin/python main.py --doctor"
