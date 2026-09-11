<div align="center">

# KYROS

### A natural-language desktop assistant for macOS and Linux

Speak normally. Kyros listens through Gemini Live, chooses the appropriate
general-purpose capability, performs the work, and reports the real result.

**macOS 13+** · **Linux / Wayland** · **Hyprland first-class** · **Python 3.10–3.14** · **MIT**

</div>

---

## What Kyros is

Kyros is a local desktop client for Google's Gemini Live API. It combines
full-duplex voice, a lightweight PyQt6 panel, platform-native audio, and
general desktop tools in one conversation.

The macOS path remains native where it matters: Swift `AVAudioEngine`, Apple
voice processing, Accessibility, Quartz, AppleScript, and `zsh`. Linux uses a
separate adapter built around PipeWire, Hyprland/Wayland, AT-SPI2, XDG portals,
and the best available input/output backends.

The central design decision is deliberate: Kyros has no phrase-specific
intent router, application allowlist, or regex command matcher. The model
receives general capabilities and composes them at runtime. Tool results are
read and verified; missing capabilities are returned as real errors instead of
being guessed.

## Contents

- [Highlights](#highlights)
- [Platform support](#platform-support)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Uninstallation](#uninstallation)
- [Running Kyros](#running-kyros)
- [Conversation and session control](#conversation-and-session-control)
- [Tool surface](#tool-surface)
- [Linux and Hyprland](#linux-and-hyprland)
- [macOS](#macos)
- [Audio](#audio)
- [Configuration](#configuration)
- [Diagnostics and testing](#diagnostics-and-testing)
- [Troubleshooting](#troubleshooting)
- [Security and privacy](#security-and-privacy)
- [Repository hygiene](#repository-hygiene)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [License](#license)
- [Türkçe](README.tr.md) · [Русский](README.ru.md)

## Highlights

- **Live voice:** native Gemini audio with microphone input, spoken output,
  interruption support, and session resumption.
- **One conversation:** no separate speech-to-text/text-to-speech orchestration
  and no hardcoded application workflows.
- **General desktop control:** shell, UI inspection, keyboard/mouse input,
  application launching, media, clipboard, notifications, web reading, and
  search.
- **Platform-native audio:** Swift voice processing on macOS; PipeWire is the
  Linux default, with an explicit PortAudio fallback.
- **Hyprland-aware Linux support:** compositor IPC, workspaces, windows,
  screenshots, portals, AT-SPI2, and capability inspection.
- **Cancellable execution:** tool work is bounded, interruptible, and reports
  the actual exit status or UI result.
- **Quiet terminal output:** concise live status events in the terminal;
  detailed diagnostics remain in rotating logs.
- **Ownership-aware lifecycle:** the installer records exactly what it created,
  and the uninstaller uses that record instead of guessing.

## Platform support

| Platform | Primary path | Notes |
| --- | --- | --- |
| macOS 13+ | Swift audio bridge + Accessibility/Quartz | Install Apple Command Line Tools and grant the requested privacy permissions. |
| Linux / Wayland | PipeWire + `linux_desktop` | Hyprland is the primary target. XDG portals and X11/XWayland fallbacks are used when available. |
| Linux distributions | `pacman`, `apt`, `dnf`, `zypper` | `install.sh` uses official repositories and stops on unsupported package managers. |
| Windows | Not supported | No Windows implementation is included. |

## Quick start

~~~bash
git clone https://github.com/rhymezip/kyros-online-desktop-assistant.git
cd kyros-online-desktop-assistant

chmod +x install.sh uninstall.sh
bash install.sh

venv/bin/python main.py
~~~

The installer detects macOS or Linux and selects only that platform's Python
dependencies. On the first run, use the Settings panel to add and test a
direct Google Gemini API key, or provide the key through the environment before
installation.

## Installation

### Recommended installer

~~~bash
bash install.sh
~~~

`install.sh` performs the following platform-aware steps:

1. Detects `Darwin` or `Linux`; other platforms are rejected.
2. Selects `requirements-macos.txt` or `requirements-linux.txt`.
3. On Linux, detects `pacman`, `apt`, `dnf`, or `zypper` and resolves the
   distribution's package names for the complete desktop toolset.
4. Creates a project-local `venv/` with Python 3.10–3.14.
5. Installs Python dependencies inside that environment and runs `pip check`.
6. On macOS, builds and signs the local Swift audio binary.
7. On Linux, records newly installed packages and configures the narrowly
   scoped `uinput`/`ydotoold` integration when it is available.
8. Runs the unit-test suite before reporting success.

Linux packages are installed only from the detected distribution's official
repositories. The installer does not use the AUR, external installer scripts,
`sudo pip`, `--break-system-packages`, or a partial-upgrade `pacman -Sy`.

Preview the plan without changing files, packages, services, or configuration:

~~~bash
bash install.sh --dry-run
~~~

### Linux PortAudio fallback

PipeWire is the Linux default and does not require NumPy or `sounddevice`.
Install the optional PortAudio path only when you need it:

~~~bash
bash install.sh --with-portaudio
venv/bin/python main.py --audio-backend portaudio
~~~

### Why Linux may ask for a password

If Linux packages or the scoped `/dev/uinput` permission setup are missing,
the installer explains the exact operation before requesting administrator
authorization. The password:

- is handled by the system authorization mechanism;
- is never sent to Gemini and is never written to a Kyros file;
- is used only for the package or permission operation being described;
- does not run ordinary Kyros work as root.

The `uinput` rule grants the dedicated `kyros-input` group access to the
virtual input device only; it does not grant general access to physical
keyboard or mouse devices. A logout/login may be required after the group
change.

## Uninstallation

Inspect the cleanup plan first:

~~~bash
bash uninstall.sh --dry-run
~~~

Then remove Kyros-owned resources:

~~~bash
bash uninstall.sh
~~~

The uninstaller is ownership-aware:

- It removes only Linux packages recorded as absent before Kyros installed
  them. Packages that already existed are not selected.
- It never performs a broad `autoremove` and does not use dependency-removal
  modes such as `pacman -Rs`.
- It removes the project `venv` only when Kyros created it.
- It removes the generated macOS audio binary only when Kyros created it.
- It disables/removes only the Kyros-owned `ydotoold` service and unchanged
  Kyros permission files.
- It preserves `config/local.json` by default because it may contain the API
  key.

Use `--yes` to skip confirmation prompts, or explicitly request the local
configuration prompt with:

~~~bash
bash uninstall.sh --purge-config
~~~

If the installation manifest is missing, the safe behavior is to preserve
existing environments and system packages rather than guess.

## Running Kyros

~~~bash
venv/bin/python main.py                  # Panel + Live voice
venv/bin/python main.py --text           # Text-only Live session; no microphone
venv/bin/python main.py --no-panel       # Headless Live session
venv/bin/python main.py --doctor         # Read-only local diagnostics
venv/bin/python main.py --audio-check    # Local audio check; no Gemini call
venv/bin/python main.py --debug          # More detail in the terminal
~~~

For a changed macOS audio source, rebuild the native bridge:

~~~bash
bash build_audio.sh
venv/bin/python main.py --audio-check
~~~

`build_audio.sh` is macOS-only. Linux never builds or uses the Swift bridge.

## Conversation and session control

Kyros is intended to be used conversationally. The model must inspect tool
results before claiming success, and it must not invent a follow-up response
after a completed turn.

- **Wake:** say `Hey Kyros` while in standby. The two-word wake phrase is
  intentional; `Kyros` alone is not a wake request.
- **Standby:** ask Kyros to wait or enter standby explicitly.
- **Stop:** ask Kyros to stop or cancel the current work. The session remains
  active unless the user explicitly requests standby.
- **Interruption:** a new user turn can interrupt spoken output and cancel
  pending work. Cancelled side effects are not automatically rolled back.

After a tool result, Kyros reports success or failure once and waits for the
next user turn. It does not add an unsolicited “shall I wait?” question or a
courtesy closing that the user did not ask for.

## Tool surface

The model receives the following general capabilities. The examples in this
table describe the surface; they are not application-specific dispatch rules.

| Tool | macOS | Linux | Purpose |
| --- | :---: | :---: | --- |
| `run_shell` | ✓ | ✓ | Run general user-level shell code (`zsh` on macOS, `/bin/sh` on Linux). |
| `run_applescript` | ✓ | — | Run AppleScript or JXA through native macOS automation. |
| `computer` | ✓ | ✓ | Inspect and operate the desktop UI through available native backends. |
| `linux_desktop` | — | ✓ | Linux/Wayland/Hyprland windows, workspaces, AT-SPI2, input, screenshots, clipboard, launch, notifications, and capability inspection. |
| `launch_app` | ✓ | ✓ | Launch a real application, desktop entry, URI, path, or explicit argv without a shell. |
| `media_control` | ✓ | ✓ | Control and inspect a selected media player; MPRIS/`playerctl` on Linux. |
| `clipboard` | ✓ | ✓ | Read or write the native clipboard; Linux primary selection where supported. |
| `read_web` | ✓ | ✓ | Fetch readable HTTP(S) content without opening a browser. |
| Google Search | ✓ | ✓ | Gemini's native search tool for current web research. |
| `session_control` | ✓ | ✓ | Explicit wake, standby, and stop transitions. |

There is no fixed Spotify/Notes/Telegram branch in the command path. For
example, launching an application is a general `launch_app` operation; media
actions are sent through `media_control`; visible UI work is inspected and
verified through `computer` or `linux_desktop`.

Elevated shell work is intentionally separate from ordinary work. On macOS it
opens the native administrator dialog; on Linux it uses the visible polkit
`pkexec` dialog when available. Kyros does not ask for a password through
voice and does not run normal commands as root.

## Linux and Hyprland

Linux uses a capability-driven adapter rather than pretending that Wayland has
macOS-style unrestricted input APIs.

`linux_desktop` can expose:

- Hyprland IPC for real windows, monitors, focus, movement, sizing, closing,
  and workspaces;
- AT-SPI2 application trees and actions when the target application exposes
  them;
- screenshots through `grim`/`slurp` or the XDG Screenshot portal;
- Unicode typing through `wtype`, with `ydotool`, portal, and clipboard-paste
  fallbacks where appropriate;
- pointer and low-level keyboard input through `ydotoold`, XDG Remote Desktop,
  or X11 backends when authorized;
- Wayland/X11 clipboard, application launching, notifications, and a
  `capabilities` inspection action.

The model is instructed to inspect first and use the returned PID, accessibility
path, role, label, window address, monitor, or workspace. It must verify
state-changing actions afterwards. If a compositor or desktop security policy
denies a capability, the tool returns the real failure; it does not fabricate
a click, keystroke, screenshot, or application state.

Check the live capability matrix with:

~~~bash
venv/bin/python main.py --doctor
~~~

The full manual Hyprland acceptance checklist is in
[LINUX_TEST.md](LINUX_TEST.md).

## macOS

The macOS path uses the native Swift audio bridge and the existing
Accessibility/Quartz/AppleScript integrations. The Linux adapter and Linux
dependency files are not selected on macOS.

The first real run may request:

- Microphone;
- Accessibility;
- Screen Recording;
- Automation access for applications controlled through AppleScript or
  System Events.

Grant only the permissions needed for the tasks you want Kyros to perform.
The complete macOS checklist is in [MAC_TEST.md](MAC_TEST.md).

## Audio

| Platform | Default backend | Optional path |
| --- | --- | --- |
| macOS | Swift `AVAudioEngine` with Apple voice processing | PortAudio |
| Linux | PipeWire via `pw-record` and `pw-play` | PortAudio with `--with-portaudio` |

The live protocol uses 16 kHz microphone PCM and 24 kHz spoken output. macOS
can use Apple's voice-processing path for speaker echo suppression. Linux has
no Apple voice-processing layer; headphones or a correctly configured
PipeWire/WirePlumber echo-cancellation graph are preferable when speaker echo
is audible.

Audio devices can be selected in Settings or through the environment:
`KYROS_INPUT_DEVICE` and `KYROS_OUTPUT_DEVICE`. Device changes are monitored
and the affected stream is restarted instead of requiring a full application
restart.

## Configuration

### API key and model

The lookup order is:

1. `GEMINI_API_KEY` and `GEMINI_MODEL` environment variables;
2. matching values in `config/local.json`;
3. the built-in default model for `GEMINI_MODEL`.

The installer creates `config/local.json` only when needed and restricts it to
the current user (`0600`). A manual setup can start from the template:

~~~bash
cp config/local.json.example config/local.json
chmod 600 config/local.json
~~~

Edit the copied file locally, or export the key before starting Kyros:

~~~bash
export GEMINI_API_KEY="your-direct-google-gemini-key"
~~~

Kyros requires a direct Google Gemini API key for the Live
`bidiGenerateContent` protocol. An OpenAI-compatible key or proxy is not an
equivalent backend.

### Runtime settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `KYROS_AUDIO_BACKEND` | `native` on macOS; `pipewire` on Linux | Select `native`, `pipewire`, or `portaudio` where supported. |
| `KYROS_INPUT_DEVICE` | System default | Persisted input-device identifier/name override. |
| `KYROS_OUTPUT_DEVICE` | System default | Persisted output-device identifier/name override. |
| `GEMINI_MODEL` | `gemini-2.5-flash-native-audio-latest` | Live voice model; Settings can refresh the available model list. |

The Settings panel can test the API key and selected model before saving and
restarting the Live connection.

## Diagnostics and testing

Run the local suite from the project environment:

~~~bash
venv/bin/python -m unittest discover -s tests -v
~~~

The installer runs the same suite in quiet mode. It contains cross-platform
unit and contract coverage for:

- connection lifecycle, reconnection, cancellation, barge-in, and session
  discipline;
- macOS and Linux audio adapters;
- PipeWire discovery, device routing, and capability reporting;
- tool execution, shell isolation, application launching, media, clipboard,
  UI dispatch, and platform-specific declarations;
- installer/uninstaller ownership rules and permission-file safety;
- logging and panel shutdown behavior.

`--doctor` performs read-only local checks and does not call Gemini.
`--audio-check` starts only the selected local audio backend and does not call
Gemini. `--text` does use the real Live API, but does not open the microphone.

## Troubleshooting

| Symptom | First check |
| --- | --- |
| Stuck on “Connecting” | Open Settings, test the key/model, then inspect `logs/kyros.log`. |
| macOS microphone failure | Grant Microphone access to the application/terminal that runs Kyros; run `--audio-check`. |
| macOS UI action denied | Grant Accessibility, Screen Recording, or Automation permission as appropriate. |
| Linux microphone failure | Run `--audio-check`; verify PipeWire, WirePlumber, `pw-record`, and `pw-play`. |
| Linux typing/clicking fails | Run `--doctor`; verify `wtype`, `ydotoold`, portal consent, and the current session. |
| AT-SPI2 tree is empty | Confirm `at-spi2-core`, PyGObject/typelibs, a running AT-SPI2 bus, and an application that exposes accessibility data. |
| Media control fails | Confirm a running MPRIS player and `playerctl` on Linux; use the inspected application name on macOS. |
| Old package appears during uninstall | Read the manifest plan; only packages newly installed by Kyros are candidates. |
| Terminal is too noisy | Use normal mode for concise events; use `--debug` only while diagnosing. Detailed output is in `logs/kyros.log`. |

Logs are local and rotating:

~~~bash
tail -f logs/kyros.log
~~~

`logs/` is capped at approximately 1 MiB for the active file plus three
rotated files. Installer/package details are kept separately under the
ignored `.kyros/` directory.

## Security and privacy

- API keys live in an ignored `config/local.json` with `0600` permissions or
  in the environment; Kyros does not log them.
- Audio, transcriptions, tool calls, and tool results are sent to Gemini as
  required by the Live session.
- Screenshots are sent to Gemini only when a screenshot-capable tool is used;
  Kyros does not keep them in the repository or a permanent local folder.
- Ordinary tools run as the logged-in user. The project has no hidden root
  daemon and no privileged background command path.
- Installer administrator authorization is limited to package and explicitly
  described Linux permission operations.
- `run_shell` is intentionally general-purpose and should be treated with the
  same trust as a terminal opened by the user.

## Repository hygiene

The repository `.gitignore` covers both macOS and Linux development output:
local credentials, environment files, virtual environments, Python caches,
logs, installer state, native build products, app bundles, editor metadata,
large audio/model artifacts, and temporary files.

Audit the working tree without staging anything:

~~~bash
git status --short --ignored
git check-ignore -v config/local.json .env .kyros logs venv native/kyros-audio
git add -A --dry-run
~~~

An ignore rule affects untracked files only. If a secret has ever been
committed, remove it from the repository history and rotate it;
`.gitignore` cannot untrack an already tracked path.

## Project layout

~~~text
.
├── main.py                         # Application entry point and CLI
├── config/
│   ├── settings.py                 # Key, model, audio, and runtime settings
│   └── local.json.example          # Safe configuration template
├── core/
│   ├── gemini_live.py              # Live session, audio flow, cancellation
│   ├── audio_io.py                 # macOS native/PortAudio path
│   ├── linux_audio.py              # Linux PipeWire/PortAudio path
│   ├── linux_ui.py                 # Wayland, Hyprland, AT-SPI2, X11, portals
│   ├── macos_ui.py                 # macOS Accessibility and screen controls
│   ├── executor.py                 # General tool execution
│   ├── protocol.py                 # System instruction and tool declarations
│   ├── doctor.py                   # Read-only diagnostics
│   ├── bootstrap.py                # Project-environment bootstrap
│   └── web_page.py                 # Readable web-page fetcher
├── gui/panel.py                    # PyQt6 panel and Settings view
├── native/
│   ├── AudioBridge.swift           # macOS AVAudioEngine bridge
│   ├── AudioInfo.plist             # Native usage metadata
│   └── Launcher.c                  # Optional macOS launcher source
├── scripts/kyros-system.sh         # Linux package/permission lifecycle
├── system/                         # Scoped uinput and ydotoold templates
├── tests/                          # Unit, contract, and Linux tests
├── install.sh                      # Platform-aware installer
├── uninstall.sh                    # Ownership-aware uninstaller
├── build_audio.sh                  # macOS audio bridge builder
├── requirements*.txt               # Common and platform-specific Python deps
├── MAC_TEST.md                     # macOS acceptance checklist
├── LINUX_TEST.md                   # Linux/Hyprland acceptance checklist
├── LICENSE                         # MIT License
└── README.tr.md / README.ru.md     # Translations
~~~

Runtime directories such as `venv/`, `logs/`, `.kyros/`, `__pycache__/`, and
the generated `native/kyros-audio` binary are intentionally absent from the
source tree and ignored by Git.

## Contributing

1. Create a focused branch from `main`.
2. Keep platform-specific code behind the appropriate adapter.
3. Do not add phrase-specific or application-specific intent branches.
4. Add or update contract tests for tool, installer, and platform changes.
5. Run the unit suite and `git diff --check`.
6. Never commit API keys, local configuration, logs, build products, or
   generated binaries.

~~~bash
git switch -c feature/short-description
venv/bin/python -m unittest discover -s tests -v
git diff --check
~~~

## License

Kyros is released under the [MIT License](LICENSE).
