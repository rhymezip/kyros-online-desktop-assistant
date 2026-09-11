#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"
KYROS_ROOT="$(pwd -P)"
export KYROS_ROOT
umask 077

# shellcheck source=scripts/kyros-system.sh
source "$KYROS_ROOT/scripts/kyros-system.sh"

KYROS_DRY_RUN=0
KYROS_PURGE_CONFIG=0
for argument in "$@"; do
    case "$argument" in
        --dry-run)
            KYROS_DRY_RUN=1
            ;;
        --yes|-y)
            KYROS_ASSUME_YES=1
            ;;
        --purge-config)
            KYROS_PURGE_CONFIG=1
            ;;
        --help|-h)
            cat <<'HELP'
Kyros uninstaller

Usage:
  bash uninstall.sh [--yes] [--purge-config] [--dry-run]

Options:
  --yes            Skip confirmation prompts; sudo may still ask for your password.
  --purge-config   Ask to remove config/local.json, which may contain your API key.
  --dry-run        Show the cleanup plan without changing anything.

The uninstaller targets only system packages recorded as absent before Kyros
installation. It never runs a broad autoremove.
HELP
            exit 0
            ;;
        *)
            kyros_fail "Unknown option: $argument (use --help for usage)"
            exit 2
            ;;
    esac
done

kyros_title "Uninstall • only Kyros-owned resources"

if [[ ! -f "$KYROS_STATE_FILE" ]]; then
    kyros_warn "Kyros installation manifest not found. Safe mode: system packages and an existing venv will not be guessed or removed."
    if [[ "$KYROS_DRY_RUN" == 1 ]]; then
        printf '  No changes will be made.\n'
    else
        printf '  Source code preserved; no Kyros-owned file record is available for removal.\n'
    fi
    exit 0
fi

kyros_state_load
PLATFORM="$(uname -s)"

if [[ "$KYROS_DRY_RUN" == 1 ]]; then
    kyros_step "Dry run: no files, packages, services, or configuration will be changed"
    printf "  Project venv: %s\n" "$([[ "${KYROS_VENV_CREATED:-0}" == 1 ]] && printf 'remove only if created by Kyros' || printf 'preserve')"
    printf "  macOS native audio binary: %s\n" "$([[ "${KYROS_NATIVE_AUDIO_CREATED:-0}" == 1 ]] && printf 'remove only if created by Kyros' || printf 'preserve')"
    printf '  config/local.json: %s\n' "$([[ "$KYROS_PURGE_CONFIG" == 1 ]] && printf 'can be removed after explicit confirmation' || printf 'preserve')"
    if [[ "$PLATFORM" == Linux ]]; then
        kyros_detect_linux
        kyros_read_added_packages
        if (( ${#KYROS_REMOVE_PACKAGES[@]} )); then
            printf '  Kyros-owned system packages:\n'
            for package in "${KYROS_REMOVE_PACKAGES[@]}"; do
                printf '    • %s\n' "$package"
            done
        else
            printf '  No Kyros-owned system packages are still installed.\n'
        fi
        printf '  Kyros uinput/ydotool service and permission records will be cleaned using manifest ownership.\n'
    fi
    exit 0
fi

if [[ "$PLATFORM" == Linux ]]; then
    # Stop the user daemon before removing its package or uinput access.
    kyros_remove_uinput_setup
    kyros_remove_system_dependencies
fi

if [[ "${KYROS_VENV_CREATED:-0}" == 1 && -d "$KYROS_ROOT/venv" ]]; then
    kyros_step "Removing the project venv created by Kyros"
    rm -rf -- "$KYROS_ROOT/venv"
    KYROS_VENV_CREATED=0
    kyros_ok "Kyros-created venv removed."
else
    kyros_ok "Existing/user-owned venv preserved."
fi

if [[ "$PLATFORM" == Darwin && "${KYROS_NATIVE_AUDIO_CREATED:-0}" == 1 \
    && -f "$KYROS_ROOT/native/kyros-audio" ]]; then
    rm -f -- "$KYROS_ROOT/native/kyros-audio"
    KYROS_NATIVE_AUDIO_CREATED=0
    kyros_ok "Kyros-created macOS audio binary removed."
fi

if [[ "$KYROS_PURGE_CONFIG" == 1 && -f "$KYROS_ROOT/config/local.json" ]]; then
    local_answer=""
    if [[ "${KYROS_ASSUME_YES:-0}" == 1 ]]; then
        local_answer="y"
    else
        printf '\nconfig/local.json may contain your Gemini API key and user settings.\n'
        printf 'Remove this file? [y/N] '
        read -r local_answer
    fi
    if kyros_answer_yes "$local_answer"; then
        rm -f -- "$KYROS_ROOT/config/local.json"
        KYROS_LOCAL_CONFIG_CREATED=0
        kyros_ok "Local configuration removed."
    else
        kyros_warn "config/local.json preserved."
    fi
else
    kyros_ok "config/local.json preserved (to avoid losing your API key)."
fi

kyros_state_write

remaining_state=0
if [[ -s "$KYROS_SYSTEM_PACKAGES_FILE" \
    || "${KYROS_UDEV_RULE_CREATED:-0}" == 1 \
    || "${KYROS_UINPUT_MODULE_CREATED:-0}" == 1 \
    || "${KYROS_INPUT_GROUP_CREATED:-0}" == 1 \
    || "${KYROS_INPUT_GROUP_USER_ADDED:-0}" == 1 \
    || "${KYROS_YDOTOOL_SERVICE_CREATED:-0}" == 1 ]]; then
    remaining_state=1
fi

if (( remaining_state == 0 )); then
    rm -f -- "$KYROS_STATE_FILE" "$KYROS_SYSTEM_PACKAGES_FILE" "$KYROS_SYSTEM_LOG" \
        "$KYROS_STATE_DIR/install.log" "$KYROS_STATE_DIR/packages.before" \
        "$KYROS_STATE_DIR/packages.after"
    rmdir "$KYROS_STATE_DIR" 2>/dev/null || true
    kyros_title "Uninstall complete"
    kyros_ok "Kyros-owned resources were cleaned up."
else
    kyros_state_write
    kyros_title "Uninstall partially complete"
    kyros_warn "Preserved or incomplete ownership records remain in .kyros/; you can run bash uninstall.sh again."
fi
printf 'Source code and user settings were preserved.\n'
