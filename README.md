<div align="center">

# KYROS

### Your AI-Powered Desktop Voice Assistant for macOS

*Speak naturally. Kyros listens, understands, and acts.*

[![macOS](https://img.shields.io/badge/macOS-13+-000000?style=for-the-badge&logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3.10--3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/Gemini-Live-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge)](https://github.com/rhymezip/kyros-online-desktop-assistant/pulls)
[![Issues](https://img.shields.io/github/issues/rhymezip/kyros-online-desktop-assistant?style=for-the-badge)](https://github.com/rhymezip/kyros-online-desktop-assistant/issues)
[![Stars](https://img.shields.io/github/stars/rhymezip/kyros-online-desktop-assistant?style=for-the-badge)](https://github.com/rhymezip/kyros-online-desktop-assistant/stargazers)
[![Forks](https://img.shields.io/github/forks/rhymezip/kyros-online-desktop-assistant?style=for-the-badge)](https://github.com/rhymezip/kyros-online-desktop-assistant/network/members)

<br>

**Kyros** is a real-time voice assistant that lives on your Mac and connects to Google's Gemini Live API. It features a full-duplex audio engine built in Swift, a Dynamic Island-style floating panel, and a powerful tool system that lets you control your entire Mac — with your voice.

No hardcoded commands. No separate STT/TTS pipeline. No regex matching.
**One model. One audio path. Pure conversation.**

<br>

![Screenshots](assets/1.png)

</div>

---

## Table of Contents

- [Features](#-features)
- [Demo](#-demo)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Usage](#-usage)
- [Voice Commands](#voice-commands)
- [Session States](#session-states)
- [Panel & Settings](#panel--settings)
- [Tools & Capabilities](#tools--capabilities)
- [Live Audio Engine](#live-audio-engine)
- [Configuration](#configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Security & Privacy](#security--privacy)
- [Project Structure](#project-structure)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)
- [Turkish](README.tr.md)

---

## Features

<table>
<tr>
<td width="50%">

**Live Audio**
Full-duplex voice with echo cancellation. 16 kHz mic input, 24 kHz TTS output, 20 ms chunks, 350 ms VAD.

**Gemini Native Audio**
Uses `gemini-2.5-flash-native-audio` — a single model handles conversation, tool calling, and voice synthesis natively.

**Full Mac Control**
Shell commands, AppleScript/JXA, Accessibility API (click, drag, scroll, type, screenshot), app automation.

**Google Search**
Built-in web search tool bound directly to the Live session — no browser needed.

</td>
<td width="50%">

**Smart Session Management**
Wake with *Hey Kyros*, standby with *you can wait*, stop with *stop*. The model decides.

**Resilient Connection**
Session resumption, buffer recovery, automatic reconnection. Survives network hiccups.

**Dynamic Island UI**
Floating 300×100 panel with transcript, mic level, settings, and right-click controls.

**Secure by Design**
API keys stored with `0600` permissions, never logged. Elevated commands use native macOS auth dialogs.

</td>
</tr>
</table>

> **Design Principle:** Kyros uses general-purpose tools composed at runtime. Example commands like *"open Notes"* or *"search Fenerbahçe"* have no hard-coded branches — the model orchestrates everything.

---

## Demo

<p align="center">
  <img src="assets/2.png" alt="Kyros in action" width="800">
</p>
<p align="center">
  <img src="assets/3.png" alt="Kyros settings" width="600">
</p>

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Gemini Live (WSS)               │
                    │     gemini-2.5-flash-native-audio            │
                    └──────────┬──────────────────┬───────────────┘
                               │  PCM 24k (TTS)   │  Tool Calls
                               ▼                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                         macOS Desktop                            │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │  AVAudioEngine│    │  PyQt6 Panel │    │  Tool Executor    │  │
│  │  (Swift)      │    │  (Dynamic    │    │  ┌─────────────┐ │  │
│  │  • Mic 16kHz  │    │   Island)    │    │  │ run_shell    │ │  │
│  │  • Speaker    │    │  • Transcript│    │  │ run_apple-   │ │  │
│  │  • Echo CXL   │    │  • Mic Level │    │  │   script     │ │  │
│  │  • VAD        │    │  • Settings  │    │  │ computer     │ │  │
│  └──────┬───────┘    │  • Controls  │    │  │  (AX/API/    │ │  │
│         │ PCM 16k     └──────────────┘    │  │   screenshot)│ │  │
│         └────────────────────────────────▶│  │ read_web     │ │  │
│                                           │  │ google_search│ │  │
│                                           │  └─────────────┘ │  │
│                                           └───────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Single model architecture** — No secondary STT/TTS. Gemini handles voice natively.
- **Full duplex** — Mic and speaker share the same `AVAudioEngine` with Apple's voice processing.
- **Cancellable tools** — Every tool runs as an `asyncio` task. Interruption clears the queue instantly.
- **Composable tools** — No intent matching or regex. The model decides which tools to call.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/rhymezip/kyros-online-desktop-assistant.git
cd kyros-online-desktop-assistant

# 2. Install (creates venv, installs deps, builds audio engine)
bash install.sh

# 3. Run
venv/bin/python main.py
```

That's it. The panel opens, you paste your Gemini API key in Settings, and you're live.

---

## Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| **macOS** | 13+ | Recommended: 15.x (Sequoia) |
| **Python** | 3.10 – 3.14 | Recommended: **3.12** |
| **Apple CLI Tools** | Latest | `xcode-select --install` |
| **Gemini API Key** | — | Get one at [aistudio.google.com](https://aistudio.google.com) |

> Python code is cross-platform testable; Swift audio engine and Live API require macOS.

---

## Installation

### Option A: Automated (recommended)

```bash
git clone https://github.com/rhymezip/kyros-online-desktop-assistant.git
cd kyros-online-desktop-assistant
bash install.sh
```

**What `install.sh` does:**
1. Finds a compatible Python (3.10–3.14), creates `venv/`
2. Installs all dependencies from `requirements.txt`
3. Prompts for your Gemini API key (if not set) → writes `config/local.json` with `0600` perms
4. Builds the Swift audio engine (`native/kyros-audio`)
5. Runs the test suite automatically

### Option B: Manual

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
bash build_audio.sh
```

Then set your API key:

```bash
export GEMINI_API_KEY="your-key-here"
```

Or copy the example config:

```bash
cp config/local.json.example config/local.json
# Edit config/local.json and add your key
```

### First Run Without API Key

On first launch without an API key, Kyros opens the **Settings** panel automatically after 900ms. Paste your key, click **Test**, then **Save and Apply** — connection starts in ~0.6s.

---

## Usage

### Run Commands

```bash
venv/bin/python main.py                  # Panel + Live (recommended)
venv/bin/python main.py --text           # Text-only mode, no mic
venv/bin/python main.py --no-panel       # Headless, no GUI
venv/bin/python main.py --audio-check    # Test audio engine only
venv/bin/python main.py --doctor         # Diagnostic checks
venv/bin/python main.py --debug          # Verbose logging
```

### Voice Commands

Just talk naturally. Kyros understands context and composes tools on the fly:

```text
Hey Kyros, open Notes and create a new note titled "Meeting Notes"

Hey Kyros, research the latest news about Fenerbahçe and summarize it

Hey Kyros, find Ali in Telegram and send him "See you tomorrow"

Hey Kyros, look at my Desktop and organize these files by type

Hey Kyros, what's the weather like in Istanbul right now?
```

### Session Control

| Say This | What Happens |
|----------|-------------|
| **Hey Kyros** | Wakes from standby, starts listening |
| **you can wait** | Goes to standby, waits for next wake |
| **stop / cancel** | Cancels current tasks, stays active |
| **Microphone off** | Mutes mic via right-click menu |

> **Note:** Only *"Hey Kyros"* wakes the assistant — saying *"Kyros"* alone in standby does nothing. The model handles wake/standby/stop decisions via `session_control`.

---

## Session States

| Panel State | Meaning |
|-------------|---------|
| `WAITING` | Standby — mic active but tools/TTS off. Waiting for *Hey Kyros*. |
| `LISTENING` | Active — mic open, VAD listening, ready for commands. |
| `SPEAKING` | TTS playing — interruptible with *stop/silence/one minute*. |
| `APPLYING · LISTENING` | Tool executing, but mic and connection stay live. |
| `AUDIO DEVICE CHANGING` | Default input/output changed, auto-reconnecting. |

---

## Panel & Settings

### Panel

- **Left click** — Opens conversation view (transcript, source links, text input, controls)
- **Right click** — Context menu (Wake / Stop / Wait / Mic toggle / Settings / Quit)
- **Settings button** — API key, voice model selection, connection test

### Settings Panel

| Setting | Description |
|---------|-------------|
| **API Key** | Your Gemini API key (`AIza...` or `AQ...`). Show/hide toggle. |
| **Voice Model** | Dropdown of available native audio models (fetched live from API). |
| **Test** | Validates API key and model availability. Green = ready. |
| **Save & Apply** | Saves to `config/local.json`, restarts connection in ~0.6s. |

> **Important:** Kyros only works with direct Google Gemini API keys. OpenAI-compatible proxies (`sk-...`) do not support the Live protocol.

---

## Tools & Capabilities

Kyros provides general-purpose tools that the model composes at runtime:

| Tool | Description |
|------|-------------|
| `run_shell` | Execute any `zsh` command. Supports `elevated=true` for admin (shows macOS password dialog). |
| `run_applescript` | Run AppleScript or JXA code for app automation. |
| `computer` | Full GUI interaction: `inspect` (AX tree), `screenshot`, `click`, `drag`, `scroll`, `key`, `type_text`. |
| `read_web` | Fetch and read web page content. |
| `google_search` | Search the web directly from the Live session. |
| `session_control` | Wake, standby, and stop actions. |

### What You Can Do

- **App Control:** Open any app, navigate menus, fill forms
- **File Management:** Create, edit, organize files and folders
- **Web Research:** Search, read articles, summarize content
- **Messaging:** Send messages via Telegram, Notes, or any automation-supported app
- **System Admin:** Run shell commands with optional elevated privileges
- **Screen Awareness:** Take screenshots, read UI elements, interact with any visible content

---

## Live Audio Engine

Kyros ships with a custom Swift audio engine (`native/AudioBridge.swift`) built on `AVAudioEngine`:

| Feature | Detail |
|---------|--------|
| **Mic Input** | 16 kHz PCM, 20 ms chunks |
| **TTS Output** | 24 kHz PCM via `AVAudioSourceNode` |
| **Echo Cancellation** | Apple Voice Processing (`setVoiceProcessingEnabled`) |
| **VAD** | 350 ms silence detection, 40 ms prefix padding |
| **Barge-in** | 2 consecutive RMS > 1150 for interruption |
| **Device Hot-swap** | Auto-detects default input/output changes, reconnects in ~75ms |
| **Fallback** | PortAudio backend for headphones (`--audio-backend portaudio`) |

### Rebuild After Changes

```bash
bash build_audio.sh
venv/bin/python main.py --audio-check   # Verify: "Standard started" + frame stats
```

---

## Configuration

### Priority Order

| Source | Priority | Description |
|--------|----------|-------------|
| `GEMINI_API_KEY` env | 1 | `export GEMINI_API_KEY=...` |
| `GEMINI_MODEL` env | 1 | Override model selection |
| `config/local.json` | 2 | `{"GEMINI_API_KEY":"...","GEMINI_MODEL":"..."}` |

### Settings in `config/settings.py`

| Setting | Default | Description |
|---------|---------|-------------|
| `AUDIO_BACKEND` | `native` | `native` (Swift) or `portaudio` |
| `SILENCE_DURATION_MS` | `350` | VAD silence threshold |
| `TOOL_TIMEOUT` | `60` | Tool execution timeout (seconds) |
| `MAX_TOOL_OUTPUT` | `24000` | Max tool output bytes |
| `MIC_GATE_RMS` | `1100` | Mic gate RMS threshold during TTS |
| `MIC_GATE_HANGOVER_MS` | `400` | Post-TTS mic gate hold |
| `MIC_GATE_BLOCK_MS` | `600` | Post-TTS mic block duration |

### Supported Models

| Model | Status |
|-------|--------|
| `gemini-2.5-flash-native-audio-latest` | Stable, recommended |
| `gemini-2.5-flash-native-audio-preview-09-2025` | Preview |

---

## Testing

```bash
# Run all unit tests (38 tests, no API required)
venv/bin/python -m unittest discover -s tests -v

# Run diagnostics (permissions, audio, API key)
venv/bin/python main.py --doctor

# Text-only mode (real API, no mic)
venv/bin/python main.py --text

# Audio engine check (no API)
venv/bin/python main.py --audio-check
```

### Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| `test_live.py` | Standby, wake, barge-in, device routing |
| `test_audio.py` | Audio generation, buffer clearing |
| `test_connection.py` | WebSocket connection lifecycle |
| `test_executor.py` | Tool execution, shell/AppleScript |

### Acceptance Testing

See [`MAC_TEST.md`](MAC_TEST.md) for the full manual acceptance test checklist covering setup, wake/standby, barge-in, system capabilities, cancel/connection, and admin privileges.

---

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| `Microphone failed to start` | System Settings → Privacy → Microphone → grant access to Kyros/Terminal/Python |
| Stuck on `Connecting` | Check API key (Settings → Test), verify network, check `logs/kyros.log` |
| `Received 1008 policy violation` | Model/API mismatch — select correct model in Settings |
| `User location is not supported` | Google regional restriction — try VPN or different network |
| Audio device changing loop | Bridge v5 debounce handles this; ensure latest `build_audio.sh` |
| `0 bytes read` after Ctrl+C | Normal WebSocket close — not an error |
| Barge-in not working | Ensure 2 clear RMS spikes > 1150; check mic gain settings |
| Wake word not detected | Only *"Hey Kyros"* works — *"Kyros"* alone does not wake from standby |

### Logs

The terminal shows concise status, audio-device, connection, and tool-result events.
Low-level audio and connection diagnostics stay in the rotating log file; use
`--debug` when you also want to see them live in the terminal.

```bash
tail -f logs/kyros.log    # Rotating: 1MB × 3 files
```

---

## Security & Privacy

- **API keys** stored in `config/local.json` with `0600` permissions or environment variables — never logged or committed.
- **Tools run as the logged-in user** — no sandboxing, no allowlist. Use with the same caution as Terminal.
- **Elevated commands** (`elevated=true`) trigger macOS native password dialogs. Passwords are never requested via voice or stored.
- **Screenshots** are sent as JPEG to Gemini for `computer` tool context. Not stored locally.
- **Standby mode** still streams audio to Gemini (no offline wake-word). Use *Microphone off* to cut the stream.
- **No root execution** — Kyros never runs as root.

---

## Project Structure

```
kyros/
├── main.py                    # Entry point, CLI args, logging
├── config/
│   ├── settings.py            # Gemini config, model list, API validation
│   ├── local.json             # (gitignored) Your API key & model
│   └── local.json.example     # Template
├── core/
│   ├── gemini_live.py         # Gemini Live session, mic gate, barge-in
│   ├── audio_io.py            # Audio engine bridge (Swift / PortAudio)
│   ├── protocol.py            # System prompt, tool definitions
│   ├── executor.py            # Tool execution (shell, AS, AX, web)
│   ├── doctor.py              # Diagnostics (--doctor, --audio-check)
│   ├── bootstrap.py           # Auto-venv activation
│   ├── macos_ui.py            # macOS UI helpers
│   └── web_page.py            # Web content fetching
├── gui/
│   └── panel.py               # Dynamic Island panel + Settings dialog
├── native/
│   ├── AudioBridge.swift      # Swift audio engine (AVAudioEngine)
│   ├── Launcher.c             # Kyros.app launcher
│   └── AudioInfo.plist        # Microphone usage description
├── assets/
│   ├── 1.png                  # Screenshot
│   ├── 2.png                  # Screenshot
│   └── 3.png                  # Screenshot
├── tests/                     # 38 unit tests
├── logs/                      # (gitignored) Rotating logs
├── install.sh                 # One-command setup
├── build_audio.sh             # Swift audio engine builder
├── requirements.txt           # Python dependencies
├── LICENSE                    # MIT License
└── README.tr.md               # Turkish documentation
```

---

## FAQ

<details>
<summary><strong>Does Kyros work with OpenAI API keys?</strong></summary>
No. Kyros requires a direct Google Gemini API key (`AIza...` or `AQ...`) for the Live (BidiGenerateContent) protocol. OpenAI-compatible proxies don't support real-time voice.
</details>

<details>
<summary><strong>Can I use Kyros with headphones?</strong></summary>
Yes. Use `--audio-backend portaudio` for headphone mode. The native Swift engine is optimized for speakers with echo cancellation.
</details>

<details>
<summary><strong>Does it work on Intel Macs?</strong></summary>
Yes, with a fallback. The 3-channel voice processing produces no frames on Intel, so Kyros auto-switches to Standard 1-channel mode.
</details>

<details>
<summary><strong>Is my data sent to Google?</strong></summary>
Audio and tool results are sent to Gemini Live for processing. Screenshots are sent as JPEG when the `computer` tool is used. No data is stored by Kyros locally beyond session transcripts in RAM.
</details>

<details>
<summary><strong>Can I use Kyros on Linux or Windows?</strong></summary>
The Python logic is cross-platform testable, but the Swift audio engine and macOS-specific tools (Accessibility, AppleScript) require macOS 13+.
</details>

<details>
<summary><strong>How much does it cost?</strong></summary>
Kyros is free and open-source (MIT). You pay only for Gemini API usage at Google's [pricing](https://ai.google.dev/pricing).
</details>

---

## Contributing

Contributions are welcome! Here's how:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Setup

```bash
git clone https://github.com/rhymezip/kyros-online-desktop-assistant.git
cd kyros-online-desktop-assistant
bash install.sh
venv/bin/python -m unittest discover -s tests -v
```

### Code Style

- Python: Follow existing conventions, no external linters required
- Swift: Follow existing patterns in `native/AudioBridge.swift`
- Tests: Add tests for new tools or significant changes

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with care for macOS**

*Kyros — because your desktop should listen.*

<br>

[![GitHub](https://img.shields.io/badge/GitHub-rhymezip-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/rhymezip)

</div>
