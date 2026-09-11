#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"
KYROS_ROOT="$(pwd -P)"
export KYROS_ROOT
# Keep installer-created state private. It contains package ownership data,
# not credentials, but it is still local installation metadata.
umask 077

# shellcheck source=scripts/kyros-system.sh
source "$KYROS_ROOT/scripts/kyros-system.sh"
trap 'kyros_record_interrupted_package_delta || true' EXIT

KYROS_DRY_RUN=0
KYROS_WITH_PORTAUDIO="${KYROS_INSTALL_PORTAUDIO:-0}"
for argument in "$@"; do
    case "$argument" in
        --dry-run)
            KYROS_DRY_RUN=1
            ;;
        --with-portaudio)
            KYROS_WITH_PORTAUDIO=1
            ;;
        --help|-h)
            cat <<'HELP'
Kyros installer

Usage:
  bash install.sh [--with-portaudio] [--dry-run]

Options:
  --with-portaudio  Also install optional PortAudio fallback dependencies on Linux.
  --dry-run         Show the plan without changing packages, files, services, or configuration.

Linux defaults to PipeWire. System packages are installed from the distribution's
official repositories; no AUR or external installer scripts are used.
HELP
            exit 0
            ;;
        *)
            kyros_fail "Unknown option: $argument (use --help for usage)"
            exit 2
            ;;
    esac
done

kyros_title "Installation • safe platform selection"
printf '%s\n' "Detecting the operating system; only this platform's dependencies will be selected."

PLATFORM="$(uname -s)"
if [[ "$PLATFORM" != Darwin && "$PLATFORM" != Linux ]]; then
    kyros_fail "This installer supports macOS and Linux only: $PLATFORM"
    exit 1
fi

if [[ "$PLATFORM" == Darwin ]]; then
    REQUIREMENTS_FILE="$KYROS_ROOT/requirements-macos.txt"
    KYROS_STATE_PLATFORM="Darwin"
    KYROS_STATE_DISTRO="macOS"
    KYROS_STATE_PACKAGE_MANAGER=""
    if ! xcrun --find swiftc >/dev/null 2>&1; then
        kyros_fail "Apple Command Line Tools are missing. Run this first: xcode-select --install"
        exit 1
    fi
else
    REQUIREMENTS_FILE="$KYROS_ROOT/requirements-linux.txt"
    if [[ "$KYROS_WITH_PORTAUDIO" == 1 ]]; then
        REQUIREMENTS_FILE="$KYROS_ROOT/requirements-linux-portaudio.txt"
    fi
fi

if [[ "$KYROS_DRY_RUN" == 1 ]]; then
    kyros_step "Dry run: no files, packages, services, or configuration will be changed"
    printf '  Python requirements file: %s\n' "$(basename "$REQUIREMENTS_FILE")"
    if [[ "$PLATFORM" == Linux ]]; then
        kyros_detect_linux
        kyros_configure_system_packages
        kyros_print_package_plan
        kyros_compute_missing_packages
        if (( ${#KYROS_MISSING_PACKAGES[@]} )); then
            printf '\nMissing system packages: %s\n' "${KYROS_MISSING_PACKAGES[*]}"
        else
            kyros_ok "Linux system packages are already complete."
        fi
        if [[ "$KYROS_WITH_PORTAUDIO" == 1 ]]; then
            printf '  Linux PortAudio fallback: enabled\n'
        else
            printf '  Linux PortAudio fallback: optional (PipeWire is the default)\n'
        fi
    else
        printf '  macOS Swift audio engine: built with build_audio.sh\n'
    fi
    exit 0
fi

kyros_prepare_state
kyros_state_load
KYROS_PREVIOUS_PACKAGE_MANAGER="${KYROS_STATE_PACKAGE_MANAGER:-}"
KYROS_STATE_PLATFORM="$([[ "$PLATFORM" == Darwin ]] && printf 'Darwin' || printf 'Linux')"
if [[ "$PLATFORM" == Darwin ]]; then
    KYROS_STATE_DISTRO="macOS"
    KYROS_STATE_PACKAGE_MANAGER=""
else
    # This also records the exact package manager used for uninstall.
    kyros_detect_linux
    if [[ -n "$KYROS_PREVIOUS_PACKAGE_MANAGER" \
        && "$KYROS_PREVIOUS_PACKAGE_MANAGER" != "$KYROS_PACKAGE_MANAGER" \
        && -s "$KYROS_SYSTEM_PACKAGES_FILE" ]]; then
        kyros_fail "This installation manifest was created with $KYROS_PREVIOUS_PACKAGE_MANAGER, but the current package manager is $KYROS_PACKAGE_MANAGER. Installation stopped to avoid ownership confusion."
        kyros_fail "Run uninstall with the original distribution/package manager first, or manage the .kyros manifest deliberately."
        exit 1
    fi
fi
kyros_state_write

if [[ "$PLATFORM" == Linux ]]; then
    kyros_install_system_dependencies
    kyros_setup_uinput
fi

KYROS_PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys; raise SystemExit(not ((3,10) <= sys.version_info[:2] <= (3,14)))'; then
        KYROS_PYTHON="$(command -v "$candidate")"
        break
    fi
done
if [[ -z "$KYROS_PYTHON" ]]; then
    kyros_fail "Python 3.10–3.14 is required. Recommended version: Python 3.12."
    exit 1
fi

if [[ -x "$KYROS_ROOT/venv/bin/python" ]]; then
    # Preserve ownership from an earlier Kyros install when reinstalling.
    KYROS_VENV_CREATED="${KYROS_VENV_CREATED:-0}"
    if ! "$KYROS_ROOT/venv/bin/python" -c 'import sys; raise SystemExit(not ((3,10) <= sys.version_info[:2] <= (3,14)))'; then
        kyros_fail "The existing venv does not use Python 3.10–3.14; it was not removed automatically."
        kyros_fail "Move or remove the existing venv yourself, then run install.sh again."
        exit 1
    fi
    kyros_ok "Existing project venv preserved: venv/"
else
    kyros_step "Creating the Python project environment"
    "$KYROS_PYTHON" -m venv "$KYROS_ROOT/venv"
    KYROS_VENV_CREATED=1
    kyros_state_write
fi

KYROS_INSTALL_LOG="$KYROS_STATE_DIR/install.log"
touch "$KYROS_INSTALL_LOG"
chmod 600 "$KYROS_INSTALL_LOG"

run_logged() {
    local label="$1"
    shift
    kyros_step "$label"
    if "$@" >>"$KYROS_INSTALL_LOG" 2>&1; then
        kyros_ok "$label completed"
        return 0
    fi
    kyros_fail "$label failed"
    printf '\n%sRecent installation log:%s\n' "$KYROS_C_DIM" "$KYROS_C_RESET" >&2
    tail -n 45 "$KYROS_INSTALL_LOG" >&2
    return 1
}

run_logged "Updating Python pip" \
    "$KYROS_ROOT/venv/bin/python" -m pip install --disable-pip-version-check \
    --progress-bar off --upgrade pip
run_logged "Installing platform dependencies ($(basename "$REQUIREMENTS_FILE"))" \
    "$KYROS_ROOT/venv/bin/python" -m pip install --disable-pip-version-check \
    --progress-bar off -r "$REQUIREMENTS_FILE"
run_logged "Verifying Python dependencies" \
    "$KYROS_ROOT/venv/bin/python" -m pip check

if [[ ! -e "$KYROS_ROOT/config/local.json" ]]; then
    KYROS_LOCAL_CONFIG_CREATED=1
fi
kyros_state_write

"$KYROS_ROOT/venv/bin/python" - <<'PY'
import getpass
import json
import os
from pathlib import Path

path = Path("config/local.json")
settings = json.loads(path.read_text()) if path.exists() else {}
if not os.environ.get("GEMINI_API_KEY") and not settings.get("GEMINI_API_KEY"):
    print("\nA Gemini API key is required for Kyros' online voice connection.")
    print("The key will not be displayed and will only be saved to config/local.json.")
    key = getpass.getpass("Gemini API key: ").strip()
    if not key:
        raise SystemExit("No API key was provided.")
    settings["GEMINI_API_KEY"] = key
    path.write_text(json.dumps(settings, indent=2) + "\n")
    path.chmod(0o600)
print("Gemini API key is ready; the default voice model is preserved.")
PY

if [[ "$PLATFORM" == Darwin ]]; then
    if [[ ! -e "$KYROS_ROOT/native/kyros-audio" ]]; then
        KYROS_NATIVE_AUDIO_CREATED=1
        kyros_state_write
    fi
    run_logged "Building the macOS Swift audio engine" bash "$KYROS_ROOT/build_audio.sh"
else
    kyros_ok "Linux PipeWire audio path ready; macOS Swift build skipped"
fi

run_logged "Running Kyros tests" \
    "$KYROS_ROOT/venv/bin/python" -m unittest discover -s tests -q

# These are transaction snapshots, not ownership records. The ownership
# manifest is retained; stale snapshots from an interrupted install are not.
rm -f -- "$KYROS_STATE_DIR/packages.before" "$KYROS_STATE_DIR/packages.after"
kyros_state_write
kyros_title "Installation complete"
kyros_ok "Kyros is ready."
printf '  Start: venv/bin/python main.py\n'
printf '  Diagnostics: venv/bin/python main.py --doctor\n'
if [[ "$PLATFORM" == Darwin ]]; then
    printf '  First use: grant Microphone, Accessibility, Screen Recording, and Automation permissions.\n'
    if [[ -x "$KYROS_ROOT/create_app_bundle.sh" ]]; then
        printf '  Optional app bundle: bash create_app_bundle.sh && open Kyros.app\n'
    fi
else
    printf '  First use: log out and back in if needed for group changes to take effect.\n'
    printf '  The desktop may ask for portal screen/input permissions on first use.\n'
    if [[ "$KYROS_WITH_PORTAUDIO" != 1 ]]; then
        printf '  If PortAudio fallback is needed: bash install.sh --with-portaudio\n'
    fi
fi
printf '  Uninstall: bash uninstall.sh\n'
