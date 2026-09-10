// Full-duplex macOS audio. Wire: type byte + UInt32LE length + payload.
// Default: standard input (1 ch) for maximum compatibility. Voice processing (AEC) is attempted
// when enabled, but if it produces no audio within 1.5s we automatically fall back to standard.
import Foundation
import AVFoundation
import CoreAudio
import Darwin

func diagnostic(_ text: String) {
    FileHandle.standardError.write(Data(("[KYROS AUDIO] " + text + "\n").utf8))
    // Ensure Python's _stderr sees it before potential early exit
    try? FileHandle.standardError.synchronize()
}

func defaultDevice(_ selector: AudioObjectPropertySelector) -> AudioDeviceID {
    var address = AudioObjectPropertyAddress(mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var device = AudioDeviceID(0)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    let status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address,
                                          0, nil, &size, &device)
    return status == noErr ? device : 0
}

func deviceDescription(_ device: AudioDeviceID) -> String {
    guard device != 0 else { return "No default device" }
    var address = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName,
        mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var name: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &name)
    let value = status == noErr ? (name?.takeUnretainedValue() as String? ?? "Unknown") : "Unknown"
    return "\(value) (id=\(device))"
}

func deviceName(_ device: AudioDeviceID) -> String {
    guard device != 0 else { return "Unknown" }
    var address = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName,
        mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var name: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &name)
    return status == noErr ? (name?.takeUnretainedValue() as String? ?? "Unknown") : "Unknown"
}

func hasChannels(_ device: AudioDeviceID, scope: AudioObjectPropertyScope) -> Bool {
    var address = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreamConfiguration,
        mScope: scope, mElement: kAudioObjectPropertyElementMain)
    var dataSize: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(device), &address, 0, nil, &dataSize) == noErr else { return false }
    let bufferList = UnsafeMutablePointer<AudioBufferList>.allocate(capacity: 1)
    defer { bufferList.deallocate() }
    guard AudioObjectGetPropertyData(AudioObjectID(device), &address, 0, nil, &dataSize, bufferList) == noErr else { return false }
    let bufCount = Int(bufferList.pointee.mNumberBuffers)
    var channelCount: UInt32 = 0
    for i in 0..<bufCount {
        channelCount += bufferList.pointee.mBuffers.mNumberChannels
    }
    return channelCount > 0
}

func printDevices() {
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var dataSize: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &dataSize)
    let deviceCount = Int(dataSize) / MemoryLayout<AudioDeviceID>.size
    var devices = [AudioDeviceID](repeating: 0, count: deviceCount)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &dataSize, &devices)
    
    let defaultInput = defaultDevice(kAudioHardwarePropertyDefaultInputDevice)
    let defaultOutput = defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)
    
    var inputList: [[String: Any]] = []
    var outputList: [[String: Any]] = []
    
    for device in devices {
        guard device != 0 else { continue }
        let name = deviceName(device)
        let id = Int(device)
        let hasInput = hasChannels(device, scope: kAudioDevicePropertyScopeInput)
        let hasOutput = hasChannels(device, scope: kAudioDevicePropertyScopeOutput)
        
        if hasInput {
            inputList.append([
                "id": id,
                "name": name,
                "is_default": device == defaultInput
            ])
        }
        if hasOutput {
            outputList.append([
                "id": id,
                "name": name,
                "is_default": device == defaultOutput
            ])
        }
    }
    
    let result: [String: Any] = [
        "input_devices": inputList,
        "output_devices": outputList
    ]
    
    if let jsonData = try? JSONSerialization.data(withJSONObject: result),
       let jsonString = String(data: jsonData, encoding: .utf8) {
        FileHandle.standardOutput.write(Data(jsonString.utf8))
    }
    exit(0)
}

func checkMicrophonePermission() {
    if AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined {
        diagnostic("Waiting for microphone permission")
        var waiting = true
        AVCaptureDevice.requestAccess(for: .audio) { _ in
            DispatchQueue.main.async { waiting = false }
        }
        while waiting {
            RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05))
        }
    }
    guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
        fail("Mikrofon izni yok. Sistem Ayarları > Gizlilik ve Güvenlik > Mikrofon bölümünde bu başlatıcıya izin verin.")
    }
}

let checkOnly = CommandLine.arguments.contains("--check")
let listDevices = CommandLine.arguments.contains("--list-devices")
let noVPFlag = CommandLine.arguments.contains("--no-vp") || CommandLine.arguments.contains("--disable-voice-processing")
let forceVPFlag = CommandLine.arguments.contains("--voice-processing")

func getArgValue(_ flag: String) -> UInt32? {
    guard let index = CommandLine.arguments.firstIndex(of: flag),
          index + 1 < CommandLine.arguments.count,
          let value = UInt32(CommandLine.arguments[index + 1]) else { return nil }
    return value
}
let requestedInputDevice = getArgValue("--input-device")
let requestedOutputDevice = getArgValue("--output-device")
let wireQueue = DispatchQueue(label: "kyros.audio.wire")
func packet(_ type: UInt8, _ data: Data) {
    if checkOnly { return }
    // R (ready) must be synchronous so Python's ready.wait() sees it before fallback timeout
    if type == 82 {
        var size = UInt32(data.count).littleEndian
        var message = Data([type])
        withUnsafeBytes(of: &size) { message.append(contentsOf: $0) }
        message.append(data)
        FileHandle.standardOutput.write(message)
        try? FileHandle.standardOutput.synchronize()
        return
    }
    wireQueue.async {
        var size = UInt32(data.count).littleEndian
        var message = Data([type])
        withUnsafeBytes(of: &size) { message.append(contentsOf: $0) }
        message.append(data)
        FileHandle.standardOutput.write(message)
    }
}
func fail(_ text: String) -> Never {
    FileHandle.standardError.write(Data((text + "\n").utf8))
    exit(1)
}
func readExact(_ size: Int) -> Data? {
    var data = Data()
    while data.count < size {
        let next = FileHandle.standardInput.readData(ofLength: size - data.count)
        if next.isEmpty { return nil }
        data.append(next)
    }
    return data
}
func uint32(_ data: Data) -> UInt32 {
    return data.enumerated().reduce(UInt32(0)) { $0 | (UInt32($1.element) << (8 * $1.offset)) }
}

final class Playback {
    let lock = NSLock()
    var samples = [Float](repeating: 0, count: 24000 * 30)
    var read = 0
    var write = 0
    var count = 0
    var generation: UInt32 = 0
    var speaking = false

    func status(_ value: Bool) {
        var number = generation.littleEndian
        var data = Data()
        withUnsafeBytes(of: &number) { data.append(contentsOf: $0) }
        data.append(value ? 1 : 0)
        packet(83, data) // S
    }
    func clear(_ number: UInt32) {
        lock.lock(); defer { lock.unlock() }
        count = 0; read = 0; write = 0
        generation = number; speaking = false
        status(false)
    }
    func append(_ data: Data) {
        lock.lock(); defer { lock.unlock() }
        if count + data.count / 2 > samples.count { fail("Playback buffer overflow") }
        data.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) in
            for index in stride(from: 0, to: data.count - 1, by: 2) {
                let bits = UInt16(bytes[index]) | (UInt16(bytes[index + 1]) << 8)
                samples[write] = Float(Int16(bitPattern: bits)) / 32768.0
                write = (write + 1) % samples.count
                count += 1
            }
        }
    }
    func render(_ frames: Int, _ list: UnsafeMutablePointer<AudioBufferList>) {
        lock.lock(); defer { lock.unlock() }
        let available = min(frames, count)
        let active = available > 0
        if active != speaking { speaking = active; status(active) }
        for buffer in UnsafeMutableAudioBufferListPointer(list) {
            guard let output = buffer.mData?.assumingMemoryBound(to: Float.self) else { continue }
            for index in 0..<frames {
                output[index] = index < available ? samples[(read + index) % samples.count] : 0
            }
        }
        read = (read + available) % samples.count
        count -= available
    }
}

signal(SIGPIPE, SIG_IGN)
if listDevices { printDevices() }
diagnostic("Bridge v6; macOS \(ProcessInfo.processInfo.operatingSystemVersionString)")
checkMicrophonePermission()

let activeInput = requestedInputDevice ?? defaultDevice(kAudioHardwarePropertyDefaultInputDevice)
let activeOutput = requestedOutputDevice ?? defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)
diagnostic("Input: \(deviceDescription(activeInput))")
diagnostic("Output: \(deviceDescription(activeOutput))")
diagnostic("Microphone authorization: \(AVCaptureDevice.authorizationStatus(for: .audio).rawValue)")
if CommandLine.arguments.contains("--diagnose") { exit(0) }
let playback = Playback()

// Helper to build and run engine. Returns never (exits or runs forever).
func runWithVoiceProcessing(_ useVP: Bool) throws {
    let engine = AVAudioEngine()
    let input = engine.inputNode
    let output = engine.outputNode
    let mixer = engine.mainMixerNode
    var stage = useVP ? "enable voice processing" : "configure standard input"
    var captureMixer: AVAudioMixerNode? = nil

    if useVP {
        do {
            try input.setVoiceProcessingEnabled(true)
            guard input.isVoiceProcessingEnabled, output.isVoiceProcessingEnabled else {
                throw NSError(domain: "kyros", code: -1, userInfo: [NSLocalizedDescriptionKey: "voice processing not enabled"])
            }
        } catch {
            diagnostic("Voice processing enable failed: \(error.localizedDescription) — falling back to standard input")
            throw error
        }
    }

    let inputFormat = input.outputFormat(forBus: 0)
    let outputFormat = output.inputFormat(forBus: 0)
    diagnostic("\(useVP ? "Processed" : "Standard") input: \(inputFormat)")
    diagnostic("Output client: \(outputFormat)")
    guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
        fail("No microphone available")
    }
    guard outputFormat.sampleRate > 0, outputFormat.channelCount > 0 else {
        fail("No output device available")
    }
    stage = "configure audio graph"
    if useVP {
        let cm = AVAudioMixerNode()
        captureMixer = cm
        engine.attach(cm)
        cm.outputVolume = 0
        engine.connect(input, to: cm, format: inputFormat)
        engine.connect(cm, to: mixer, format: inputFormat)
        engine.connect(mixer, to: output, format: outputFormat)
    } else {
        // Standard input: no captureMixer needed, but we still need mixer->output for playback
        // input tap works without connecting input to output; just ensure mixer->output exists
        engine.connect(mixer, to: output, format: outputFormat)
    }

    let micFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: false)!
    guard let converter = AVAudioConverter(from: inputFormat, to: micFormat) else {
        fail("Microphone format conversion unavailable")
    }
    // Use a box to allow mutation from tap closure
    final class Box { var firstLogged = false; var frameCount = 0 }
    let box = Box()
    input.installTap(onBus: 0, bufferSize: AVAudioFrameCount(inputFormat.sampleRate * 0.02), format: inputFormat) { buffer, _ in
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * 16000 / inputFormat.sampleRate) + 64
        guard let pcm = AVAudioPCMBuffer(pcmFormat: micFormat, frameCapacity: capacity) else { return }
        var supplied = false
        var error: NSError?
        let result = converter.convert(to: pcm, error: &error) { _, state in
            if supplied { state.pointee = .noDataNow; return nil }
            supplied = true; state.pointee = .haveData
            return buffer
        }
        let hasInt16 = pcm.frameLength > 0 && pcm.int16ChannelData?[0] != nil
        if !box.firstLogged {
            box.firstLogged = true
            box.frameCount = Int(pcm.frameLength)
            diagnostic("First input frame: sourceFrames=\(buffer.frameLength), convertedFrames=\(pcm.frameLength), conversion=\(result), int16=\(hasInt16), error=\(String(describing: error)), voiceProcessing=\(useVP)")
        }
        if result == .error { fail("Microphone conversion failed: \(String(describing: error))") }
        if hasInt16, let samples = pcm.int16ChannelData?[0] {
            packet(77, Data(bytes: samples, count: Int(pcm.frameLength) * 2)) // M
        }
    }
    let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1)!
    let source = AVAudioSourceNode(format: format) { _, _, frames, buffers -> OSStatus in
        playback.render(Int(frames), buffers)
        return noErr
    }
    engine.attach(source)
    engine.connect(source, to: mixer, format: format)
    stage = useVP ? "start voice-processing engine" : "start standard engine"
    try engine.start()
    diagnostic("\(useVP ? "Voice processing" : "Standard") started; microphone and playback ready (firstFramePending=\(!box.firstLogged))")
    if checkOnly {
        // For check mode, verify we actually get a microphone frame within 2s
        let deadline = Date(timeIntervalSinceNow: 2.0)
        while Date() < deadline && !box.firstLogged {
            RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05))
        }
        engine.stop()
        if !box.firstLogged {
            // If VP was enabled and failed, throw to trigger fallback; if already standard, fail
            if useVP {
                diagnostic("Check: voice processing produced no audio, will fallback")
                throw NSError(domain: "kyros", code: -2, userInfo: [NSLocalizedDescriptionKey: "no first frame"])
            } else {
                fail("Microphone produced no audio within 2s; check input device")
            }
        }
        diagnostic("Local audio check passed; no API connection was made (voiceProcessing=\(useVP), firstFrames=\(box.frameCount))")
        exit(0)
    }
    // For live mode with VP, wait up to 1.5s for first frame before deciding fallback
    if useVP {
        let deadline = Date(timeIntervalSinceNow: 1.5)
        while Date() < deadline && !box.firstLogged {
            RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05))
        }
        if !box.firstLogged {
            diagnostic("Voice processing produced no audio after 1.5s — falling back to standard input (no AEC)")
            input.removeTap(onBus: 0)
            engine.stop()
            throw NSError(domain: "kyros", code: -2, userInfo: [NSLocalizedDescriptionKey: "fallback"])
        }
    }

    diagnostic("Audio running with \(useVP ? "voice processing (AEC)" : "standard input (no AEC)") — input=\(deviceDescription(activeInput)), output=\(deviceDescription(activeOutput))")
    // Route handling (same for both modes)
    var routeCheckPending = false
    func reopenDefaultRoute() {
        DispatchQueue.main.async {
            diagnostic("System audio route changed; reopening current defaults")
            engine.stop()
            exit(75)
        }
    }
    func verifyDefaultRouteLater() {
        guard !routeCheckPending else { return }
        routeCheckPending = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            routeCheckPending = false
            let newInput = defaultDevice(kAudioHardwarePropertyDefaultInputDevice)
            let newOutput = defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)
            if newInput != activeInput || newOutput != activeOutput {
                reopenDefaultRoute()
            }
        }
    }
    for selector in [kAudioHardwarePropertyDefaultInputDevice, kAudioHardwarePropertyDefaultOutputDevice] {
        var address = AudioObjectPropertyAddress(mSelector: selector,
            mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        let status = AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, DispatchQueue.main) { _, _ in
            verifyDefaultRouteLater()
        }
        guard status == noErr else { fail("Default audio device listener failed: \(status)") }
    }
    packet(82, Data()) // R: ready
    DispatchQueue.global(qos: .userInteractive).async {
        while let header = readExact(5) {
            let type = header[0]
            let length = Int(uint32(Data(header.dropFirst())))
            if length > 2_000_000 { fail("Invalid audio packet size") }
            guard let data = readExact(length) else { break }
            switch type {
            case 80: // P
                if data.count % 2 != 0 { fail("Invalid PCM packet") }
                playback.append(data)
            case 67: // C
                if data.count != 4 { fail("Invalid clear packet") }
                playback.clear(uint32(data))
            default: fail("Unknown audio command")
            }
        }
        DispatchQueue.main.async {
            engine.stop()
            exit(0)
        }
    }
    RunLoop.main.run()
    // Should never return
    fail("RunLoop exited unexpectedly at stage \(stage)")
}

// Top-level orchestration: try VP if allowed, else standard. Auto-fallback if VP produces no audio.
do {
    let tryVP = !noVPFlag
    if tryVP {
        do {
            try runWithVoiceProcessing(true)
        } catch let err as NSError where err.code == -2 {
            diagnostic("Falling back to standard input after VP timeout")
            try runWithVoiceProcessing(false)
        } catch {
            // Any other error during VP setup/start (e.g. -10875, no device) -> try standard before giving up
            let ns = error as NSError
            diagnostic("VP setup failed (\(ns.domain) code=\(ns.code) \(ns.localizedDescription)) — trying standard input")
            try runWithVoiceProcessing(false)
        }
    } else {
        try runWithVoiceProcessing(false)
    }
} catch {
    let details = error as NSError
    let message = "Audio engine failed at '\(details.domain)': code=\(details.code), \(details.localizedDescription). System default input=\(deviceDescription(defaultDevice(kAudioHardwarePropertyDefaultInputDevice))); output=\(deviceDescription(defaultDevice(kAudioHardwarePropertyDefaultOutputDevice)))."
    if details.code == -10875 && !checkOnly {
        FileHandle.standardError.write(Data((message + "\n").utf8))
        try? FileHandle.standardError.synchronize()
        exit(76)
    }
    if details.code == -2 {
        do {
            diagnostic("Retrying with standard input after error \(details)")
            try runWithVoiceProcessing(false)
        } catch {
            fail("Audio engine failed after fallback: \(error)")
        }
    } else {
        fail(message)
    }
}
