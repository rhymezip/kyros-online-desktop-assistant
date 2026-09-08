#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
    echo "Ses motoru Mac üzerinde derlenmeli."
    exit 1
fi
if ! xcrun --find swiftc >/dev/null 2>&1; then
    echo "Apple Command Line Tools eksik: xcode-select --install"
    exit 1
fi
# Replace the working binary only after compilation and signing both succeed.
KYROS_AUDIO_BUILD="$(mktemp -d native/.audio-build.XXXXXX)"
trap 'rm -rf "$KYROS_AUDIO_BUILD"' EXIT
xcrun swiftc -O native/AudioBridge.swift -o "$KYROS_AUDIO_BUILD/kyros-audio" \
    -framework AVFoundation -framework CoreAudio \
    -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$PWD/native/AudioInfo.plist"
codesign --force --sign - --identifier com.kyros.audio "$KYROS_AUDIO_BUILD/kyros-audio"
mv "$KYROS_AUDIO_BUILD/kyros-audio" native/kyros-audio
echo "Güncel ses motoru hazır. Kontrol: venv/bin/python main.py --audio-check"
