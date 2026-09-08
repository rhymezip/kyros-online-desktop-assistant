"""Generic macOS Accessibility and Quartz operations, isolated for cancellation."""

import json
import subprocess
import sys
import time


def operate(args):
    import ApplicationServices as AX
    import Quartz as Q
    from AppKit import NSWorkspace

    action = args["action"]
    workspace = NSWorkspace.sharedWorkspace()
    front = workspace.frontmostApplication()

    def attr(element, name):
        error, value = AX.AXUIElementCopyAttributeValue(element, name, None)
        return value if error == 0 else None

    def label(element):
        return str(attr(element, "AXTitle") or attr(element, "AXDescription") or "")[
            :300
        ]

    def resolve():
        pid = int(args.get("pid", front.processIdentifier()))
        element = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(element, 1.0)
        for index in args.get("path", []):
            children = attr(element, "AXChildren") or []
            if not 0 <= index < len(children):
                raise ValueError("Stale accessibility path; inspect again")
            element = children[index]
        return pid, element

    if action == "screenshot":
        if not Q.CGPreflightScreenCaptureAccess():
            Q.CGRequestScreenCaptureAccess()
            return {
                "ok": False,
                "error": "Ekran Kaydı izni gerekiyor; Sistem Ayarları > Gizlilik ve Güvenlik.",
            }
        error, displays, count = Q.CGGetActiveDisplayList(32, None, None)
        if error:
            raise RuntimeError(f"Display enumeration failed: {error}")
        index = int(args.get("display", 1))
        if not 1 <= index <= count:
            raise ValueError("display must be a 1-based active display index")
        bounds = Q.CGDisplayBounds(displays[index - 1])
        result = subprocess.run(
            [
                "/usr/sbin/screencapture",
                "-x",
                "-D",
                str(index),
                "-t",
                "jpg",
                args["image_path"],
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode:
            return {"ok": False, "error": result.stderr.decode(errors="replace")}
        from PIL import Image

        with Image.open(args["image_path"]) as picture:
            picture.thumbnail((1600, 1600))
            size = picture.size
            picture.convert("RGB").save(args["image_path"], quality=82)
        return {
            "ok": True,
            "display": index,
            "display_count": count,
            "image_pixels": list(size),
            "screen_points": {
                "x": bounds.origin.x,
                "y": bounds.origin.y,
                "width": bounds.size.width,
                "height": bounds.size.height,
            },
            "coordinate_mapping": "global_x = screen.x + image_x * screen.width / image_pixels[0]; likewise y",
            "detail": "The corresponding screenshot is sent to your live video input.",
        }

    if not AX.AXIsProcessTrusted():
        AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True})
        return {
            "ok": False,
            "error": "Erişilebilirlik izni gerekiyor; Sistem Ayarları > Gizlilik ve Güvenlik.",
        }

    if action == "inspect":
        pid, element = resolve()
        depth = max(1, min(int(args.get("depth", 5)), 10))
        nodes = []
        clipped = False
        used_bytes = 0
        deadline = time.monotonic() + 12

        def walk(item, path, remaining):
            nonlocal clipped, used_bytes
            if len(nodes) >= 180 or time.monotonic() > deadline:
                clipped = True
                return
            role = str(attr(item, "AXRole") or "")
            subrole = str(attr(item, "AXSubrole") or "")
            value = attr(item, "AXValue")
            node = {
                "path": path,
                "role": role,
                "label": label(item),
                "enabled": bool(attr(item, "AXEnabled")),
            }
            if (
                isinstance(value, (str, int, float, bool))
                and subrole != "AXSecureTextField"
            ):
                node["value"] = str(value)[:700]
            error, actions = AX.AXUIElementCopyActionNames(item, None)
            if error == 0:
                node["actions"] = list(actions or [])
            size = len(json.dumps(node, ensure_ascii=False).encode())
            if used_bytes + size > 22000:
                clipped = True
                return
            used_bytes += size
            nodes.append(node)
            children = attr(item, "AXChildren") or []
            node["child_count"] = len(children)
            if remaining:
                for index, child in enumerate(children):
                    walk(child, path + [index], remaining - 1)
                    if clipped:
                        break
            elif children:
                node["children_omitted"] = True

        walk(element, list(args.get("path", [])), depth)
        return {
            "ok": True,
            "pid": pid,
            "frontmost": {
                "name": front.localizedName(),
                "pid": front.processIdentifier(),
            },
            "apps": [
                {
                    "name": app.localizedName(),
                    "pid": app.processIdentifier(),
                    "bundle_id": app.bundleIdentifier(),
                }
                for app in workspace.runningApplications()
                if app.activationPolicy() == 0
            ],
            "nodes": nodes,
            "truncated": clipped,
            "detail": "Paths are AXChildren indices from app root. Reinspect subtrees if children omitted. UI can change; inspect again after actions.",
        }

    if action in ("ax_press", "ax_set"):
        _, element = resolve()
        if (
            str(attr(element, "AXRole") or "") != args["role"]
            or label(element) != args["label"]
        ):
            raise ValueError("Element changed; inspect again before acting")
        if action == "ax_press":
            error = AX.AXUIElementPerformAction(element, "AXPress")
        else:
            error = AX.AXUIElementSetAttributeValue(element, "AXValue", args["text"])
        return {
            "ok": error == 0,
            "ax_error": int(error),
            "detail": "Verify resulting UI with inspect.",
        }

    flags = 0
    for modifier in args.get("modifiers", []):
        flags |= {
            "command": Q.kCGEventFlagMaskCommand,
            "shift": Q.kCGEventFlagMaskShift,
            "option": Q.kCGEventFlagMaskAlternate,
            "control": Q.kCGEventFlagMaskControl,
        }[modifier]

    def post(event):
        if event is None:
            raise RuntimeError("Unable to create input event")
        Q.CGEventSetFlags(event, flags)
        Q.CGEventPost(Q.kCGHIDEventTap, event)

    if action == "key":
        code = int(args["keycode"])
        if not 0 <= code <= 127:
            raise ValueError("keycode must be 0..127")
        post(Q.CGEventCreateKeyboardEvent(None, code, True))
        post(Q.CGEventCreateKeyboardEvent(None, code, False))
    elif action == "type_text":
        # Small Unicode chunks preserve emoji/surrogates and avoid keyboard layout assumptions.
        text = args["text"]
        for offset in range(0, len(text), 16):
            chunk = text[offset : offset + 16]
            units = len(chunk.encode("utf-16-le")) // 2
            for down in (True, False):
                event = Q.CGEventCreateKeyboardEvent(None, 0, down)
                Q.CGEventKeyboardSetUnicodeString(event, units, chunk)
                post(event)
            time.sleep(0.005)
    elif action in ("click", "drag"):
        point = (float(args["x"]), float(args["y"]))
        right = args.get("button", "left") == "right"
        button = Q.kCGMouseButtonRight if right else Q.kCGMouseButtonLeft
        down = Q.kCGEventRightMouseDown if right else Q.kCGEventLeftMouseDown
        up = Q.kCGEventRightMouseUp if right else Q.kCGEventLeftMouseUp
        count = max(1, min(int(args.get("clicks", 1)), 3))
        for click in range(1, count + 1):
            event = Q.CGEventCreateMouseEvent(None, down, point, button)
            Q.CGEventSetIntegerValueField(event, Q.kCGMouseEventClickState, click)
            post(event)
            if action == "drag":
                end = (float(args["to_x"]), float(args["to_y"]))
                for step in range(1, 16):
                    pos = (
                        point[0] + (end[0] - point[0]) * step / 15,
                        point[1] + (end[1] - point[1]) * step / 15,
                    )
                    post(
                        Q.CGEventCreateMouseEvent(
                            None,
                            Q.kCGEventRightMouseDragged
                            if right
                            else Q.kCGEventLeftMouseDragged,
                            pos,
                            button,
                        )
                    )
                    time.sleep(0.01)
                point = end
            event = Q.CGEventCreateMouseEvent(None, up, point, button)
            Q.CGEventSetIntegerValueField(event, Q.kCGMouseEventClickState, click)
            post(event)
    elif action == "scroll":
        post(
            Q.CGEventCreateScrollWheelEvent(
                None,
                Q.kCGScrollEventUnitPixel,
                2,
                int(args.get("dy", 0)),
                int(args.get("dx", 0)),
            )
        )
    else:
        raise ValueError("Unknown computer action")
    return {
        "ok": True,
        "detail": "Input delivered; inspect/screenshot to verify the intended result.",
    }


if __name__ == "__main__":
    try:
        result = operate(json.load(sys.stdin))
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
