#!/usr/bin/env bash

# Shared Linux package, permission and ownership helpers for install.sh and
# uninstall.sh.  This file is sourced; it is intentionally not an executable
# installer by itself.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "This file is a library for install.sh and uninstall.sh."
    exit 1
fi

: "${KYROS_ROOT:?KYROS_ROOT must point to the project root}"

KYROS_STATE_DIR="${KYROS_STATE_DIR:-$KYROS_ROOT/.kyros}"
KYROS_STATE_FILE="$KYROS_STATE_DIR/install-state"
KYROS_SYSTEM_PACKAGES_FILE="$KYROS_STATE_DIR/system-packages.added"
KYROS_SYSTEM_LOG="$KYROS_STATE_DIR/system-packages.log"
KYROS_UDEV_RULE_SOURCE="$KYROS_ROOT/system/99-kyros-uinput.rules"
KYROS_UDEV_RULE_DEST="/etc/udev/rules.d/99-kyros-uinput.rules"
KYROS_UINPUT_MODULE_SOURCE="$KYROS_ROOT/system/kyros-uinput.conf"
KYROS_UINPUT_MODULE_DEST="/etc/modules-load.d/kyros-uinput.conf"
KYROS_INPUT_GROUP="kyros-input"
KYROS_YDOTOOL_UNIT="kyros-ydotoold.service"
KYROS_SUDO_VALIDATED=0
KYROS_SYSTEM_REMOVE_SKIPPED=0
KYROS_PACKAGE_SNAPSHOT_BEFORE=""

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    KYROS_C_RESET=$'\033[0m'
    KYROS_C_DIM=$'\033[2m'
    KYROS_C_GREEN=$'\033[32m'
    KYROS_C_YELLOW=$'\033[33m'
    KYROS_C_RED=$'\033[31m'
    KYROS_C_BLUE=$'\033[36m'
else
    KYROS_C_RESET=""
    KYROS_C_DIM=""
    KYROS_C_GREEN=""
    KYROS_C_YELLOW=""
    KYROS_C_RED=""
    KYROS_C_BLUE=""
fi

kyros_line() {
    printf '%s\n' "────────────────────────────────────────────────────────────"
}

kyros_title() {
    printf '\n%s%sKYROS%s\n' "$KYROS_C_GREEN" "$KYROS_C_BLUE" "$KYROS_C_RESET"
    printf '%s%s\n' "$1" "$KYROS_C_RESET"
    kyros_line
}

kyros_step() {
    printf '%s▸%s %s\n' "$KYROS_C_BLUE" "$KYROS_C_RESET" "$1"
}

kyros_ok() {
    printf '%s✓%s %s\n' "$KYROS_C_GREEN" "$KYROS_C_RESET" "$1"
}

kyros_warn() {
    printf '%s!%s %s\n' "$KYROS_C_YELLOW" "$KYROS_C_RESET" "$1" >&2
}

kyros_fail() {
    printf '%s✗%s %s\n' "$KYROS_C_RED" "$KYROS_C_RESET" "$1" >&2
}

kyros_answer_yes() {
    [[ "$1" =~ ^[Yy]([Ee][Ss])?$ ]]
}

kyros_state_get() {
    local key="$1"
    [[ -f "$KYROS_STATE_FILE" ]] || return 1
    awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' \
        "$KYROS_STATE_FILE"
}

kyros_state_load() {
    KYROS_STATE_VERSION="$(kyros_state_get version 2>/dev/null || printf '1')"
    KYROS_STATE_PLATFORM="$(kyros_state_get platform 2>/dev/null || printf '')"
    KYROS_STATE_DISTRO="$(kyros_state_get distro 2>/dev/null || printf '')"
    KYROS_STATE_PACKAGE_MANAGER="$(kyros_state_get package_manager 2>/dev/null || printf '')"
    KYROS_VENV_CREATED="$(kyros_state_get venv_created 2>/dev/null || printf '0')"
    KYROS_NATIVE_AUDIO_CREATED="$(kyros_state_get native_audio_created 2>/dev/null || printf '0')"
    KYROS_LOCAL_CONFIG_CREATED="$(kyros_state_get local_config_created 2>/dev/null || printf '0')"
    KYROS_UDEV_RULE_CREATED="$(kyros_state_get udev_rule_created 2>/dev/null || printf '0')"
    KYROS_UINPUT_MODULE_CREATED="$(kyros_state_get uinput_module_created 2>/dev/null || printf '0')"
    KYROS_INPUT_GROUP_CREATED="$(kyros_state_get input_group_created 2>/dev/null || printf '0')"
    KYROS_INPUT_GROUP_USER_ADDED="$(kyros_state_get input_group_user_added 2>/dev/null || printf '0')"
    KYROS_YDOTOOL_SERVICE_CREATED="$(kyros_state_get ydotool_service_created 2>/dev/null || printf '0')"
    KYROS_YDOTOOL_SERVICE_ENABLED="$(kyros_state_get ydotool_service_enabled 2>/dev/null || printf '0')"
    KYROS_YDOTOOL_SERVICE_CHECKSUM="$(kyros_state_get ydotool_service_checksum 2>/dev/null || printf '')"
}

kyros_state_write() {
    mkdir -p "$KYROS_STATE_DIR"
    chmod 700 "$KYROS_STATE_DIR"
    local temporary="$KYROS_STATE_FILE.tmp.$$"
    {
        printf 'version=1\n'
        printf 'platform=%s\n' "${KYROS_STATE_PLATFORM:-}"
        printf 'distro=%s\n' "${KYROS_STATE_DISTRO:-}"
        printf 'package_manager=%s\n' "${KYROS_STATE_PACKAGE_MANAGER:-}"
        printf 'venv_created=%s\n' "${KYROS_VENV_CREATED:-0}"
        printf 'native_audio_created=%s\n' "${KYROS_NATIVE_AUDIO_CREATED:-0}"
        printf 'local_config_created=%s\n' "${KYROS_LOCAL_CONFIG_CREATED:-0}"
        printf 'udev_rule_created=%s\n' "${KYROS_UDEV_RULE_CREATED:-0}"
        printf 'uinput_module_created=%s\n' "${KYROS_UINPUT_MODULE_CREATED:-0}"
        printf 'input_group_created=%s\n' "${KYROS_INPUT_GROUP_CREATED:-0}"
        printf 'input_group_user_added=%s\n' "${KYROS_INPUT_GROUP_USER_ADDED:-0}"
        printf 'ydotool_service_created=%s\n' "${KYROS_YDOTOOL_SERVICE_CREATED:-0}"
        printf 'ydotool_service_enabled=%s\n' "${KYROS_YDOTOOL_SERVICE_ENABLED:-0}"
        printf 'ydotool_service_checksum=%s\n' "${KYROS_YDOTOOL_SERVICE_CHECKSUM:-}"
    } > "$temporary"
    chmod 600 "$temporary"
    mv -f "$temporary" "$KYROS_STATE_FILE"
}

kyros_prepare_state() {
    mkdir -p "$KYROS_STATE_DIR"
    chmod 700 "$KYROS_STATE_DIR"
    touch "$KYROS_SYSTEM_LOG"
    chmod 600 "$KYROS_SYSTEM_LOG"
    if [[ ! -f "$KYROS_SYSTEM_PACKAGES_FILE" ]]; then
        : > "$KYROS_SYSTEM_PACKAGES_FILE"
        chmod 600 "$KYROS_SYSTEM_PACKAGES_FILE"
    fi
}

kyros_detect_linux() {
    if [[ "$(uname -s)" != Linux ]]; then
        kyros_fail "Linux system dependencies can only be managed on Linux."
        return 1
    fi

    KYROS_DISTRO_ID="unknown"
    KYROS_DISTRO_LIKE=""
    KYROS_DISTRO_NAME="Linux"
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        KYROS_DISTRO_ID="${ID:-unknown}"
        KYROS_DISTRO_LIKE="${ID_LIKE:-}"
        KYROS_DISTRO_NAME="${PRETTY_NAME:-${NAME:-Linux}}"
    fi

    local family=""
    case " $KYROS_DISTRO_ID $KYROS_DISTRO_LIKE " in
        *" arch "*|*" manjaro "*|*" endeavouros "*|*" garuda "*) family="pacman" ;;
        *" debian "*|*" ubuntu "*|*" linuxmint "*|*" pop "*) family="apt" ;;
        *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*) family="dnf" ;;
        *" suse "*|*" opensuse "*|*" sles "*) family="zypper" ;;
    esac
    if [[ -z "$family" ]]; then
        if command -v pacman >/dev/null 2>&1; then
            family="pacman"
        elif command -v apt-get >/dev/null 2>&1; then
            family="apt"
        elif command -v dnf >/dev/null 2>&1; then
            family="dnf"
        elif command -v zypper >/dev/null 2>&1; then
            family="zypper"
        fi
    fi
    if [[ -z "$family" ]]; then
        kyros_fail "No supported package manager found (pacman, apt, dnf, or zypper)."
        return 1
    fi
    KYROS_PACKAGE_MANAGER="$family"
    KYROS_STATE_PLATFORM="Linux"
    KYROS_STATE_DISTRO="$KYROS_DISTRO_ID"
    KYROS_STATE_PACKAGE_MANAGER="$KYROS_PACKAGE_MANAGER"
}

kyros_package_installed() {
    local package="$1"
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            pacman -Qq -- "$package" >/dev/null 2>&1
            ;;
        apt)
            dpkg-query -W -f='${Status}' -- "$package" 2>/dev/null \
                | grep -q '^install ok installed$'
            ;;
        dnf|zypper)
            rpm -q -- "$package" >/dev/null 2>&1
            ;;
        *)
            return 1
            ;;
    esac
}

kyros_package_available() {
    local package="$1"
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            pacman -Si -- "$package" >/dev/null 2>&1
            ;;
        apt)
            apt-cache show -- "$package" 2>/dev/null | grep -q '^Package:'
            ;;
        dnf)
            dnf -q info -- "$package" >/dev/null 2>&1
            ;;
        zypper)
            zypper --quiet search --match-exact --type package -- "$package" \
                >/dev/null 2>&1
            ;;
        *)
            return 1
            ;;
    esac
}

kyros_pick_package() {
    local candidate
    for candidate in "$@"; do
        if kyros_package_installed "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    for candidate in "$@"; do
        if kyros_package_available "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    # Let the package manager emit its precise error if no repository metadata
    # is available.  This is safer than silently dropping a required feature.
    printf '%s\n' "$1"
}

kyros_pick_command_package() {
    local binary="$1"
    shift
    local candidate
    # An installed alternative is acceptable only when it actually exposes
    # the command Kyros needs.  Package names such as Debian's libnotify and
    # libnotify-bin are not interchangeable merely because both exist.
    for candidate in "$@"; do
        if kyros_package_installed "$candidate" \
            && command -v "$binary" >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    for candidate in "$@"; do
        if kyros_package_available "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    printf '%s\n' "$1"
}

kyros_configure_system_packages() {
    local audio_tools notify_tool polkit_tool python_gi portal_backend atspi_typelib
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            audio_tools="pipewire"
            notify_tool="libnotify"
            polkit_tool="polkit"
            python_gi="python-gobject"
            atspi_typelib=""
            ;;
        apt)
            audio_tools="$(kyros_pick_command_package pw-record pipewire-bin pipewire)"
            notify_tool="$(kyros_pick_command_package notify-send libnotify-bin libnotify)"
            polkit_tool="$(kyros_pick_command_package pkexec policykit-1 polkit)"
            python_gi="$(kyros_pick_package python3-gi python-gobject)"
            atspi_typelib="$(kyros_pick_package gir1.2-atspi-2.0)"
            ;;
        dnf)
            audio_tools="$(kyros_pick_command_package pw-record pipewire-utils pipewire)"
            notify_tool="$(kyros_pick_command_package notify-send libnotify)"
            polkit_tool="$(kyros_pick_command_package pkexec polkit)"
            python_gi="$(kyros_pick_package python3-gobject python-gobject)"
            atspi_typelib="$(kyros_pick_package at-spi2-core)"
            ;;
        zypper)
            audio_tools="$(kyros_pick_command_package pw-record pipewire-tools pipewire)"
            notify_tool="$(kyros_pick_command_package notify-send libnotify-tools libnotify)"
            polkit_tool="$(kyros_pick_command_package pkexec polkit)"
            python_gi="$(kyros_pick_package python3-gobject python-gobject)"
            atspi_typelib="$(kyros_pick_package at-spi2-core)"
            ;;
        *)
            kyros_fail "Could not prepare the Linux package list."
            return 1
            ;;
    esac

    portal_backend="$(kyros_pick_package xdg-desktop-portal-hyprland xdg-desktop-portal-wlr)"
    KYROS_SYSTEM_PACKAGES=(
        "$audio_tools"
        wireplumber
        kmod
        grim
        slurp
        wtype
        ydotool
        wl-clipboard
        playerctl
        "$notify_tool"
        "$polkit_tool"
        at-spi2-core
        "$python_gi"
        xdg-desktop-portal
        xdg-desktop-portal-gtk
        "$portal_backend"
        xdg-utils
    )
    if [[ -n "$atspi_typelib" && "$atspi_typelib" != at-spi2-core ]]; then
        KYROS_SYSTEM_PACKAGES+=("$atspi_typelib")
    fi

    # Remove duplicate aliases selected on distributions where one package
    # provides two capabilities.
    mapfile -t KYROS_SYSTEM_PACKAGES < <(printf '%s\n' "${KYROS_SYSTEM_PACKAGES[@]}" | awk 'NF && !seen[$0]++')
}

kyros_capture_installed_packages() {
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            pacman -Qq 2>/dev/null | LC_ALL=C sort -u
            ;;
        apt)
            dpkg-query -W -f='${binary:Package} ${Status}\n' 2>/dev/null \
                | awk '$2 == "install" && $3 == "ok" && $4 == "installed" {print $1}' \
                | LC_ALL=C sort -u
            ;;
        dnf|zypper)
            rpm -qa --qf='%{NAME}\n' 2>/dev/null | LC_ALL=C sort -u
            ;;
        *)
            return 1
            ;;
    esac
}

kyros_compute_missing_packages() {
    KYROS_MISSING_PACKAGES=()
    local package
    for package in "${KYROS_SYSTEM_PACKAGES[@]}"; do
        if ! kyros_package_installed "$package"; then
            KYROS_MISSING_PACKAGES+=("$package")
        fi
    done
}

kyros_verify_system_commands() {
    local missing=() command
    for command in pw-record pw-play wpctl grim slurp wtype ydotool ydotoold \
        wl-copy wl-paste playerctl notify-send pkexec modprobe; do
        if ! command -v "$command" >/dev/null 2>&1; then
            missing+=("$command")
        fi
    done
    if (( ${#missing[@]} )); then
        kyros_fail "Expected Linux tools are missing after installation: ${missing[*]}"
        return 1
    fi
}

kyros_refresh_package_metadata() {
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            # Avoid `pacman -Sy`, which can create a partial-upgrade system.
            kyros_warn "The pacman database was not refreshed; the existing sync database is used to avoid a partial upgrade."
            ;;
        apt)
            kyros_step "Refreshing Debian/Ubuntu package lists"
            kyros_privileged_logged env DEBIAN_FRONTEND=noninteractive apt-get \
                -o Dpkg::Use-Pty=0 -o APT::Color=0 -qq update
            ;;
        dnf)
            kyros_step "Preparing the Fedora/RHEL package cache"
            kyros_privileged_logged dnf -q makecache --timer
            ;;
        zypper)
            kyros_step "Refreshing openSUSE package lists"
            kyros_privileged_logged zypper --non-interactive --quiet refresh
            ;;
    esac
}

kyros_sudo_password() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        return 0
    fi
    if [[ "$KYROS_SUDO_VALIDATED" == 1 ]]; then
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        kyros_fail "sudo is required for this operation, but sudo was not found."
        return 1
    fi
    local prompt='[Kyros] Enter your sudo password to authorize this operation: '
    if ! sudo -p "$prompt" -v; then
        kyros_fail "sudo validation failed."
        return 1
    fi
    KYROS_SUDO_VALIDATED=1
}

kyros_request_sudo() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        return 0
    fi
    if [[ "$KYROS_SUDO_VALIDATED" == 1 ]]; then
        kyros_step "Administrator permission already validated; ${KYROS_SUDO_CONTEXT:-performing the required Linux operation}"
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        kyros_fail "sudo is required for this operation, but sudo was not found."
        return 1
    fi
    printf '\n'
    kyros_line
    printf '%s%sWhy is administrator permission required?%s\n' "$KYROS_C_BLUE" "$KYROS_C_BLUE" "$KYROS_C_RESET"
    printf '%s\n' "${KYROS_SUDO_CONTEXT:-Kyros will perform only the required Linux system operation.}"
    printf 'This password will:\n'
    printf "  • not be sent to Gemini or saved to any file;\n"
    printf "  • not grant Kyros general root access;\n"
    printf "  • only authorize sudo package or permission operations.\n"
    kyros_line
    local answer
    if [[ "${KYROS_ASSUME_YES:-0}" == 1 ]]; then
        answer="y"
    else
        printf 'Continue? [Y/n] '
        read -r answer
    fi
    if [[ -n "$answer" ]] && ! kyros_answer_yes "$answer"; then
        kyros_fail "Administrator permission was not approved; the complete Linux installation was stopped."
        return 1
    fi
    kyros_sudo_password
}

kyros_privileged_logged() {
    mkdir -p "$KYROS_STATE_DIR"
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        "$@" >>"$KYROS_SYSTEM_LOG" 2>&1
    else
        sudo -n "$@" >>"$KYROS_SYSTEM_LOG" 2>&1
    fi
}

kyros_show_log_tail() {
    if [[ -s "$KYROS_SYSTEM_LOG" ]]; then
        printf '\n%sRecent system package log:%s\n' "$KYROS_C_DIM" "$KYROS_C_RESET" >&2
        tail -n 35 "$KYROS_SYSTEM_LOG" >&2
    fi
}

kyros_install_package_transaction() {
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            kyros_privileged_logged pacman -S --needed --noconfirm \
                "${KYROS_SYSTEM_PACKAGES[@]}"
            ;;
        apt)
            kyros_privileged_logged env DEBIAN_FRONTEND=noninteractive apt-get \
                -o Dpkg::Use-Pty=0 -o APT::Color=0 -o Dpkg::Options::=--force-confold \
                -y --no-install-recommends -qq install "${KYROS_SYSTEM_PACKAGES[@]}"
            ;;
        dnf)
            kyros_privileged_logged dnf -q install -y --setopt=install_weak_deps=False \
                "${KYROS_SYSTEM_PACKAGES[@]}"
            ;;
        zypper)
            kyros_privileged_logged zypper --non-interactive --quiet install \
                --no-recommends "${KYROS_SYSTEM_PACKAGES[@]}"
            ;;
        *)
            return 1
            ;;
    esac
}

kyros_record_package_delta() {
    local before="$1" after="$2" delta="$KYROS_STATE_DIR/packages.delta.$$"
    [[ -f "$before" && -f "$after" ]] || return 0
    LC_ALL=C comm -13 <(LC_ALL=C sort -u "$before") <(LC_ALL=C sort -u "$after") \
        > "$delta"
    if [[ -s "$delta" ]]; then
        cat "$delta" >> "$KYROS_SYSTEM_PACKAGES_FILE"
        LC_ALL=C sort -u "$KYROS_SYSTEM_PACKAGES_FILE" \
            -o "$KYROS_SYSTEM_PACKAGES_FILE"
    fi
    rm -f "$delta"
}

kyros_record_interrupted_package_delta() {
    [[ -n "${KYROS_PACKAGE_SNAPSHOT_BEFORE:-}" \
        && -f "$KYROS_PACKAGE_SNAPSHOT_BEFORE" ]] || return 0
    local after="$KYROS_STATE_DIR/packages.interrupted.$$"
    if kyros_capture_installed_packages > "$after" 2>/dev/null; then
        kyros_record_package_delta "$KYROS_PACKAGE_SNAPSHOT_BEFORE" "$after" || true
    fi
    rm -f "$KYROS_PACKAGE_SNAPSHOT_BEFORE" "$after"
    KYROS_PACKAGE_SNAPSHOT_BEFORE=""
}

kyros_print_package_plan() {
    kyros_step "Linux package plan: $KYROS_DISTRO_NAME"
    printf '  Package manager: %s\n' "$KYROS_PACKAGE_MANAGER"
    printf '  Kyros desktop tools:\n'
    local package
    for package in "${KYROS_SYSTEM_PACKAGES[@]}"; do
        if kyros_package_installed "$package"; then
            printf '    %s✓%s %s (already installed)\n' "$KYROS_C_GREEN" "$KYROS_C_RESET" "$package"
        else
            printf '    %s+%s %s (Kyros will install)\n' "$KYROS_C_YELLOW" "$KYROS_C_RESET" "$package"
        fi
    done
}

kyros_install_system_dependencies() {
    kyros_prepare_state
    kyros_detect_linux
    kyros_configure_system_packages
    kyros_compute_missing_packages

    if (( ${#KYROS_MISSING_PACKAGES[@]} == 0 )); then
        kyros_print_package_plan
        kyros_verify_system_commands
        kyros_ok "Required Linux system packages are already installed; nothing will be downloaded."
        return 0
    fi

    kyros_print_package_plan
    KYROS_SUDO_CONTEXT="Kyros will install these missing official packages for Linux desktop, audio, and input capabilities: ${KYROS_MISSING_PACKAGES[*]}."
    kyros_request_sudo
    kyros_refresh_package_metadata
    # Refreshing metadata may make a better portal/audio provider available.
    kyros_configure_system_packages
    kyros_compute_missing_packages

    local before="$KYROS_STATE_DIR/packages.before" after="$KYROS_STATE_DIR/packages.after"
    kyros_capture_installed_packages > "$before"
    KYROS_PACKAGE_SNAPSHOT_BEFORE="$before"
    kyros_step "Installing Linux desktop packages (details are written to .kyros/system-packages.log)"
    local result=0
    if ! kyros_install_package_transaction; then
        result=1
    fi
    kyros_capture_installed_packages > "$after" || true
    kyros_record_package_delta "$before" "$after"
    rm -f "$before" "$after"
    KYROS_PACKAGE_SNAPSHOT_BEFORE=""
    if (( result != 0 )); then
        kyros_fail "Linux system packages could not be installed completely."
        kyros_show_log_tail
        return 1
    fi
    kyros_compute_missing_packages
    if (( ${#KYROS_MISSING_PACKAGES[@]} != 0 )); then
        kyros_fail "The package manager succeeded, but these packages are still missing: ${KYROS_MISSING_PACKAGES[*]}"
        return 1
    fi
    kyros_verify_system_commands
    kyros_ok "Linux system packages are ready."
}

kyros_user_unit_dir() {
    printf '%s/systemd/user\n' "${XDG_CONFIG_HOME:-$HOME/.config}"
}

kyros_user_systemd_available() {
    command -v systemctl >/dev/null 2>&1 \
        && systemctl --user show-environment >/dev/null 2>&1
}

kyros_setup_uinput() {
    [[ "$(uname -s)" == Linux ]] || return 0
    command -v ydotool >/dev/null 2>&1 || return 0
    command -v ydotoold >/dev/null 2>&1 || {
        kyros_warn "The ydotool package appears installed, but ydotoold was not found."
        return 0
    }

    local user_name="${USER:-$(id -un)}"
    local uinput_ready=0
    if [[ -r /dev/uinput && -w /dev/uinput ]]; then
        uinput_ready=1
    fi

    if [[ ! -e /dev/uinput ]] && command -v modprobe >/dev/null 2>&1; then
        kyros_step "Enabling the Linux uinput kernel module"
        KYROS_SUDO_CONTEXT="The Linux uinput kernel module must be enabled and loaded at boot for ydotool mouse and keyboard control."
        if ! kyros_request_sudo; then
            kyros_warn "uinput could not be enabled; ydotool may be limited to the portal fallback."
            return 0
        fi
        if kyros_privileged_logged modprobe uinput; then
            if [[ ! -e "$KYROS_UINPUT_MODULE_DEST" ]]; then
                if kyros_privileged_logged install -D -o root -g root -m 0644 \
                    "$KYROS_UINPUT_MODULE_SOURCE" "$KYROS_UINPUT_MODULE_DEST"; then
                    KYROS_UINPUT_MODULE_CREATED=1
                    kyros_state_write
                fi
            elif cmp -s "$KYROS_UINPUT_MODULE_SOURCE" "$KYROS_UINPUT_MODULE_DEST"; then
                # Preserve a previous Kyros ownership flag on reinstall. An
                # identical file can be Kyros' own earlier installation.
                KYROS_UINPUT_MODULE_CREATED="${KYROS_UINPUT_MODULE_CREATED:-0}"
            fi
        fi
        [[ -r /dev/uinput && -w /dev/uinput ]] && uinput_ready=1
    fi

    if (( uinput_ready == 0 )); then
        KYROS_SUDO_CONTEXT="Kyros will add a dedicated udev rule and kyros-input group for /dev/uinput only; physical keyboard and mouse devices will not receive general access."
        if [[ -e "$KYROS_UDEV_RULE_DEST" ]] \
            && ! cmp -s "$KYROS_UDEV_RULE_SOURCE" "$KYROS_UDEV_RULE_DEST"; then
            kyros_fail "$KYROS_UDEV_RULE_DEST already exists with different contents; it was not overwritten."
            return 1
        fi
        printf '\n'
        kyros_line
        printf '%s%sydotool mouse/keyboard permission%s\n' "$KYROS_C_BLUE" "$KYROS_C_BLUE" "$KYROS_C_RESET"
        printf "Linux uses /dev/uinput for mouse and low-level keyboard control.\n"
        printf 'Kyros will create a dedicated "%s" group that can access only this virtual device;\n' "$KYROS_INPUT_GROUP"
        printf 'it will not grant general access to physical keyboard or mouse devices.\n'
        printf 'You may need to log out and back in once after this change.\n'
        printf 'Install this scoped permission rule? [Y/n] '
        local answer
        read -r answer
        if [[ -n "$answer" ]] && ! kyros_answer_yes "$answer"; then
            kyros_warn "uinput permission was not installed; XDG Remote Desktop may be used instead."
            return 0
        fi
        kyros_sudo_password
        if [[ ! -e "$KYROS_UDEV_RULE_DEST" ]]; then
            if ! kyros_privileged_logged groupadd --system "$KYROS_INPUT_GROUP"; then
                # Another process may have created it between the check and now.
                getent group "$KYROS_INPUT_GROUP" >/dev/null 2>&1 || {
                    kyros_fail "Could not create the Kyros uinput group."
                    return 1
                }
            else
                KYROS_INPUT_GROUP_CREATED=1
                kyros_state_write
            fi
        elif ! getent group "$KYROS_INPUT_GROUP" >/dev/null 2>&1; then
            if ! kyros_privileged_logged groupadd --system "$KYROS_INPUT_GROUP"; then
                kyros_fail "The uinput rule exists, but the kyros-input group could not be created."
                return 1
            fi
            KYROS_INPUT_GROUP_CREATED=1
            kyros_state_write
        fi
        if ! id -nG "$user_name" | tr ' ' '\n' | grep -Fxq "$KYROS_INPUT_GROUP"; then
            if kyros_privileged_logged usermod -aG "$KYROS_INPUT_GROUP" "$user_name"; then
                KYROS_INPUT_GROUP_USER_ADDED=1
                kyros_state_write
            else
                kyros_fail "Could not add the user to the kyros-input group."
                return 1
            fi
        fi
        if [[ -e "$KYROS_UDEV_RULE_DEST" ]]; then
            # The contents were checked before touching the user's group.
            :
        else
            if ! kyros_privileged_logged install -D -o root -g root -m 0644 \
                "$KYROS_UDEV_RULE_SOURCE" "$KYROS_UDEV_RULE_DEST"; then
                kyros_fail "Could not install the uinput udev rule."
                return 1
            fi
            KYROS_UDEV_RULE_CREATED=1
        fi
        kyros_privileged_logged udevadm control --reload-rules || true
        kyros_privileged_logged udevadm trigger --name-match=uinput || true
        kyros_state_write
        kyros_ok "Kyros-scoped uinput permission rule is ready. It takes effect after logout/login."
    fi

    local unit_dir unit_file ydotoold_path temporary service_owned
    unit_dir="$(kyros_user_unit_dir)"
    unit_file="$unit_dir/$KYROS_YDOTOOL_UNIT"
    service_owned="${KYROS_YDOTOOL_SERVICE_CREATED:-0}"
    ydotoold_path="$(command -v ydotoold)"
    mkdir -p "$unit_dir"
    temporary="$KYROS_STATE_DIR/ydotoold.service.$$"
    sed "s|/usr/bin/ydotoold|$ydotoold_path|g" \
        "$KYROS_ROOT/system/kyros-ydotoold.service" > "$temporary"
    chmod 600 "$temporary"

    local manage_unit=1
    if [[ -e "$unit_file" ]]; then
        if ! cmp -s "$temporary" "$unit_file"; then
            kyros_warn "$unit_file already exists as a different user service; it was not overwritten."
            manage_unit=0
        else
            KYROS_YDOTOOL_SERVICE_CHECKSUM="$(sha256sum "$unit_file" | awk '{print $1}')"
            if [[ "$service_owned" != 1 ]]; then
                manage_unit=0
                kyros_warn "$unit_file already belongs to the user; service settings were not changed."
            fi
        fi
    else
        install -D -m 0644 "$temporary" "$unit_file"
        KYROS_YDOTOOL_SERVICE_CREATED=1
        KYROS_YDOTOOL_SERVICE_CHECKSUM="$(sha256sum "$unit_file" | awk '{print $1}')"
    fi
    rm -f "$temporary"

    if (( manage_unit == 1 )) && kyros_user_systemd_available; then
        systemctl --user daemon-reload >/dev/null 2>&1 || true
        if systemctl --user enable "$KYROS_YDOTOOL_UNIT" >/dev/null 2>&1; then
            KYROS_YDOTOOL_SERVICE_ENABLED=1
        fi
        if [[ -r /dev/uinput && -w /dev/uinput ]]; then
            if systemctl --user restart "$KYROS_YDOTOOL_UNIT" >/dev/null 2>&1; then
                kyros_ok "The ydotoold user service is enabled and ready."
            else
                kyros_warn "The ydotoold service was installed but could not start now; doctor will show details."
            fi
        else
            kyros_warn "The ydotoold service was installed; group permission will take effect after logout/login."
        fi
    elif (( manage_unit == 1 )); then
        kyros_warn "No systemd user session was found; ydotoold was installed but may need to be started manually."
    fi
    kyros_state_write
}

kyros_read_added_packages() {
    KYROS_REMOVE_PACKAGES=()
    [[ -f "$KYROS_SYSTEM_PACKAGES_FILE" ]] || return 0
    local package
    while IFS= read -r package; do
        [[ -z "$package" ]] && continue
        # Package names come from the package manager snapshot. Reject anything
        # unexpected before it can ever become a command argument.
        if [[ ! "$package" =~ ^[A-Za-z0-9][A-Za-z0-9+_.:@-]*$ ]]; then
            kyros_warn "Invalid package name found in the manifest; skipped: $package"
            continue
        fi
        if kyros_package_installed "$package"; then
            KYROS_REMOVE_PACKAGES+=("$package")
        fi
    done < "$KYROS_SYSTEM_PACKAGES_FILE"
}

kyros_update_added_package_manifest() {
    local temporary="$KYROS_SYSTEM_PACKAGES_FILE.tmp.$$" package
    : > "$temporary"
    for package in "${KYROS_REMOVE_PACKAGES[@]}"; do
        if kyros_package_installed "$package"; then
            printf '%s\n' "$package" >> "$temporary"
        fi
    done
    LC_ALL=C sort -u "$temporary" -o "$temporary"
    mv -f "$temporary" "$KYROS_SYSTEM_PACKAGES_FILE"
}

kyros_apt_remove_transaction() {
    local plan="$KYROS_STATE_DIR/apt-remove.plan.$$"
    local planned="$KYROS_STATE_DIR/apt-remove.planned.$$"
    local extras="$KYROS_STATE_DIR/apt-remove.extras.$$"
    if ! kyros_privileged_logged env LC_ALL=C apt-get -s -o APT::Color=0 \
        remove --auto-remove "${KYROS_REMOVE_PACKAGES[@]}"; then
        rm -f "$plan" "$planned" "$extras"
        return 1
    fi
    # Repeat the simulation into a file for the safety check.  It is not
    # enough to trust a package manager's auto-remove set blindly.
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        env LC_ALL=C apt-get -s -o APT::Color=0 remove --auto-remove \
            "${KYROS_REMOVE_PACKAGES[@]}" > "$plan" 2>&1
    else
        sudo -n env LC_ALL=C apt-get -s -o APT::Color=0 remove --auto-remove \
            "${KYROS_REMOVE_PACKAGES[@]}" > "$plan" 2>&1
    fi
    awk '$1 == "Remv" {print $2}' "$plan" | LC_ALL=C sort -u > "$planned"
    LC_ALL=C comm -23 "$planned" <(printf '%s\n' "${KYROS_REMOVE_PACKAGES[@]}" | LC_ALL=C sort -u) \
        > "$extras"
    if [[ -s "$extras" ]]; then
        kyros_warn "apt wants to remove automatic packages outside the Kyros manifest; only direct Kyros packages will be removed for safety."
        kyros_privileged_logged env DEBIAN_FRONTEND=noninteractive apt-get \
            -o Dpkg::Use-Pty=0 -o APT::Color=0 -y -qq remove \
            "${KYROS_REMOVE_PACKAGES[@]}"
    else
        kyros_privileged_logged env DEBIAN_FRONTEND=noninteractive apt-get \
            -o Dpkg::Use-Pty=0 -o APT::Color=0 -y -qq remove --auto-remove \
            "${KYROS_REMOVE_PACKAGES[@]}"
    fi
    rm -f "$plan" "$planned" "$extras"
}

kyros_remove_package_transaction() {
    case "$KYROS_PACKAGE_MANAGER" in
        pacman)
            # Do not use `-s`: pacman's dependency cleanup can remove a
            # package that was already installed before Kyros. The manifest
            # is the complete ownership boundary; remove only its exact
            # package names and let the package manager preserve everything
            # outside that boundary.
            kyros_privileged_logged pacman -R --noconfirm "${KYROS_REMOVE_PACKAGES[@]}"
            ;;
        apt)
            kyros_apt_remove_transaction
            ;;
        dnf)
            kyros_privileged_logged dnf -q remove -y --noautoremove \
                "${KYROS_REMOVE_PACKAGES[@]}"
            ;;
        zypper)
            kyros_privileged_logged zypper --non-interactive --quiet remove \
                --no-recommends "${KYROS_REMOVE_PACKAGES[@]}"
            ;;
        *)
            return 1
            ;;
    esac
}

kyros_remove_system_dependencies() {
    [[ "$(uname -s)" == Linux ]] || return 0
    [[ -f "$KYROS_SYSTEM_PACKAGES_FILE" ]] || {
        kyros_warn "The Kyros package manifest was not found; system packages will not be guessed or removed."
        return 0
    }
    local recorded_manager="${KYROS_STATE_PACKAGE_MANAGER:-}"
    kyros_detect_linux
    if [[ -n "$recorded_manager" && "$recorded_manager" != "$KYROS_PACKAGE_MANAGER" ]]; then
        kyros_fail "The installation package manager ($recorded_manager) differs from the current package manager ($KYROS_PACKAGE_MANAGER); packages will not be guessed or removed."
        return 1
    fi
    kyros_read_added_packages
    if (( ${#KYROS_REMOVE_PACKAGES[@]} == 0 )); then
        kyros_ok "No Kyros-installed system packages are still present."
        return 0
    fi

    printf '\n'
    kyros_line
    printf '%s%sKyros will remove its system dependencies%s\n' "$KYROS_C_YELLOW" "$KYROS_C_YELLOW" "$KYROS_C_RESET"
    printf 'The following packages were not installed before Kyros:\n'
    local package
    for package in "${KYROS_REMOVE_PACKAGES[@]}"; do
        printf '  • %s\n' "$package"
    done
    printf 'Packages that existed before installation are not in this list and will not be removed.\n'
    local answer
    if [[ "${KYROS_ASSUME_YES:-0}" == 1 ]]; then
        answer="y"
    else
        printf 'Continue? [y/N] '
        read -r answer
    fi
    kyros_answer_yes "$answer" || {
        kyros_warn "System packages are being preserved."
        KYROS_SYSTEM_REMOVE_SKIPPED=1
        return 0
    }
    KYROS_SUDO_CONTEXT="Kyros will remove only the new system packages recorded in its installation manifest; packages present before installation will not be touched."
    kyros_sudo_password
    kyros_step "Removing Kyros-installed system packages (details are written to .kyros/system-packages.log)"
    if ! kyros_remove_package_transaction; then
        kyros_fail "An error occurred while removing some system packages."
        kyros_show_log_tail
        kyros_update_added_package_manifest
        return 1
    fi
    kyros_update_added_package_manifest
    if [[ -s "$KYROS_SYSTEM_PACKAGES_FILE" ]]; then
        kyros_warn "Some packages were kept because of dependencies or other use; the manifest is retained for another attempt."
    else
        kyros_ok "Kyros-installed system packages were removed."
    fi
}

kyros_remove_uinput_setup() {
    [[ "$(uname -s)" == Linux ]] || return 0
    kyros_state_load
    local needs_privilege=0
    local user_name="${USER:-$(id -un)}"

    # Reconcile already-removed resources before asking for sudo. A previous
    # uninstall may have been interrupted, or an administrator may have
    # removed a Kyros-owned resource manually. Changed resources remain
    # owned-but-preserved and are intentionally handled below.
    if [[ "${KYROS_UDEV_RULE_CREATED:-0}" == 1 ]]; then
        if [[ ! -e "$KYROS_UDEV_RULE_DEST" ]]; then
            KYROS_UDEV_RULE_CREATED=0
        elif cmp -s "$KYROS_UDEV_RULE_SOURCE" "$KYROS_UDEV_RULE_DEST"; then
            needs_privilege=1
        else
            kyros_warn "$KYROS_UDEV_RULE_DEST was changed after Kyros installation; it will be preserved."
        fi
    fi
    if [[ "${KYROS_UINPUT_MODULE_CREATED:-0}" == 1 ]]; then
        if [[ ! -e "$KYROS_UINPUT_MODULE_DEST" ]]; then
            KYROS_UINPUT_MODULE_CREATED=0
        elif cmp -s "$KYROS_UINPUT_MODULE_SOURCE" "$KYROS_UINPUT_MODULE_DEST"; then
            needs_privilege=1
        else
            kyros_warn "$KYROS_UINPUT_MODULE_DEST was changed after Kyros installation; it will be preserved."
        fi
    fi
    if [[ "${KYROS_INPUT_GROUP_USER_ADDED:-0}" == 1 ]]; then
        if ! getent group "$KYROS_INPUT_GROUP" >/dev/null 2>&1; then
            KYROS_INPUT_GROUP_USER_ADDED=0
        elif id -nG "$user_name" | tr ' ' '\n' | grep -Fxq "$KYROS_INPUT_GROUP"; then
            needs_privilege=1
        else
            KYROS_INPUT_GROUP_USER_ADDED=0
        fi
    fi
    if [[ "${KYROS_INPUT_GROUP_CREATED:-0}" == 1 ]]; then
        if ! getent group "$KYROS_INPUT_GROUP" >/dev/null 2>&1; then
            KYROS_INPUT_GROUP_CREATED=0
        else
            local existing_members
            existing_members="$(getent group "$KYROS_INPUT_GROUP" | awk -F: '{print $4}')"
            if [[ -z "$existing_members" ]]; then
                needs_privilege=1
            else
                kyros_warn "The $KYROS_INPUT_GROUP group has other members; the group will be preserved."
            fi
        fi
    fi

    if [[ "${KYROS_YDOTOOL_SERVICE_CREATED:-0}" == 1 ]]; then
        local unit_file="$(kyros_user_unit_dir)/$KYROS_YDOTOOL_UNIT"
        local remove_unit=0
        if [[ -e "$unit_file" && -n "${KYROS_YDOTOOL_SERVICE_CHECKSUM:-}" ]] \
            && [[ "$(sha256sum "$unit_file" | awk '{print $1}')" == "$KYROS_YDOTOOL_SERVICE_CHECKSUM" ]]; then
            remove_unit=1
        fi
        if (( remove_unit == 1 )); then
            if kyros_user_systemd_available; then
                systemctl --user disable --now "$KYROS_YDOTOOL_UNIT" >/dev/null 2>&1 || true
                systemctl --user daemon-reload >/dev/null 2>&1 || true
            fi
            # `systemctl --user` can be unavailable during a text-only
            # uninstall even though enable previously created this exact
            # Kyros-owned link. Remove only a link that resolves to the
            # unchanged Kyros unit; never touch an unrelated wants entry.
            if [[ "${KYROS_YDOTOOL_SERVICE_ENABLED:-0}" == 1 ]]; then
                local wants_link="$(kyros_user_unit_dir)/default.target.wants/$KYROS_YDOTOOL_UNIT"
                if [[ -L "$wants_link" ]] \
                    && [[ "$(readlink -f "$wants_link" 2>/dev/null || true)" == "$(readlink -f "$unit_file" 2>/dev/null || true)" ]]; then
                    rm -f -- "$wants_link"
                fi
            fi
            rm -f "$unit_file"
            KYROS_YDOTOOL_SERVICE_CREATED=0
            KYROS_YDOTOOL_SERVICE_ENABLED=0
            KYROS_YDOTOOL_SERVICE_CHECKSUM=""
        elif [[ -e "$unit_file" ]]; then
            kyros_warn "$unit_file was changed after Kyros installation; it was preserved."
        else
            KYROS_YDOTOOL_SERVICE_CREATED=0
            KYROS_YDOTOOL_SERVICE_ENABLED=0
            KYROS_YDOTOOL_SERVICE_CHECKSUM=""
        fi
    fi

    if (( needs_privilege == 0 )); then
        return 0
    fi
    KYROS_SUDO_CONTEXT="Kyros will remove only its own udev/module permission files and its own kyros-input group membership."
    kyros_request_sudo
    if [[ "${KYROS_UDEV_RULE_CREATED:-0}" == 1 && -e "$KYROS_UDEV_RULE_DEST" ]] \
        && cmp -s "$KYROS_UDEV_RULE_SOURCE" "$KYROS_UDEV_RULE_DEST"; then
        if kyros_privileged_logged rm -f -- "$KYROS_UDEV_RULE_DEST"; then
            kyros_privileged_logged udevadm control --reload-rules || true
            kyros_privileged_logged udevadm trigger --name-match=uinput || true
            KYROS_UDEV_RULE_CREATED=0
        else
            kyros_warn "The Kyros udev rule could not be removed; the manifest is preserved."
        fi
    fi
    if [[ "${KYROS_UINPUT_MODULE_CREATED:-0}" == 1 && -e "$KYROS_UINPUT_MODULE_DEST" ]] \
        && cmp -s "$KYROS_UINPUT_MODULE_SOURCE" "$KYROS_UINPUT_MODULE_DEST"; then
        if kyros_privileged_logged rm -f -- "$KYROS_UINPUT_MODULE_DEST"; then
            KYROS_UINPUT_MODULE_CREATED=0
        else
            kyros_warn "The Kyros uinput module file could not be removed; the manifest is preserved."
        fi
    fi
    if [[ "${KYROS_INPUT_GROUP_USER_ADDED:-0}" == 1 ]] \
        && getent group "$KYROS_INPUT_GROUP" >/dev/null 2>&1; then
        if kyros_privileged_logged gpasswd -d "$user_name" "$KYROS_INPUT_GROUP"; then
            KYROS_INPUT_GROUP_USER_ADDED=0
        else
            kyros_warn "The user's kyros-input membership could not be removed; the manifest is preserved."
        fi
    elif [[ "${KYROS_INPUT_GROUP_USER_ADDED:-0}" == 1 ]]; then
        KYROS_INPUT_GROUP_USER_ADDED=0
    fi
    if [[ "${KYROS_INPUT_GROUP_CREATED:-0}" == 1 ]] \
        && getent group "$KYROS_INPUT_GROUP" >/dev/null 2>&1; then
        local members
        members="$(getent group "$KYROS_INPUT_GROUP" | awk -F: '{print $4}')"
        if [[ -z "$members" ]]; then
            kyros_privileged_logged groupdel "$KYROS_INPUT_GROUP" || true
            KYROS_INPUT_GROUP_CREATED=0
        else
            kyros_warn "The $KYROS_INPUT_GROUP group has other members; the group is preserved."
        fi
    fi
    kyros_state_write
}
