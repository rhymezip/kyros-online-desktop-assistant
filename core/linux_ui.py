"""Linux desktop operations for Wayland/X11 sessions.

This module is intentionally generic.  It does not contain application names,
voice phrases, or task-specific branches.  The model receives the current
desktop state and chooses among the operations exposed here.

Hyprland/Wayland is the first-class path:

* Hyprland IPC supplies windows, monitors, focus and compositor-safe window
  operations.
* ``grim``/``slurp`` provide fast screenshots and region selection.
* AT-SPI2 supplies an accessibility tree for applications that expose one.
* ``wtype``/``ydotool`` are used only when installed and authorized; X11's
  ``xdotool`` is a fallback for X11/XWayland.
* The XDG screenshot portal is a last-resort screenshot path when GIO/GLib is
  available.  It keeps permission decisions in the desktop portal instead of
  attempting to bypass Wayland security.

All subprocesses use argv arrays and never pass model data through a shell.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse
import uuid


class LinuxDesktopError(RuntimeError):
    """A desktop capability is unavailable or an operation failed."""


def _which(name: str) -> str | None:
    return shutil.which(name)


def _ydotool_socket() -> str:
    """Use the per-user runtime socket created by Kyros' ydotoold service."""

    configured = os.environ.get("YDOTOOL_SOCKET")
    if configured:
        return configured
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return str(Path(runtime) / ".ydotool_socket")
    return f"/run/user/{os.getuid()}/.ydotool_socket"


def _ydotool_ready() -> bool:
    if not _which("ydotool"):
        return False
    return Path(_ydotool_socket()).exists()


def _run(argv, *, input_data=None, timeout=10, check=True):
    env = os.environ.copy()
    # Desktop helpers can receive arbitrary argv selected by the model. Keep
    # the Gemini credential out of every child process.
    env.pop("GEMINI_API_KEY", None)
    if Path(argv[0]).name == "ydotool":
        # ydotool's default follows XDG_RUNTIME_DIR, while older package
        # builds default to /tmp. Set the service socket explicitly so both
        # client generations use the same per-user endpoint.
        env.setdefault("YDOTOOL_SOCKET", _ydotool_socket())
    try:
        result = subprocess.run(
            list(argv),
            input=input_data,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise LinuxDesktopError(f"Gerekli Linux aracı bulunamadı: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LinuxDesktopError(f"Linux masaüstü işlemi zaman aşımına uğradı: {argv[0]}") from exc
    except OSError as exc:
        raise LinuxDesktopError(f"Linux masaüstü işlemi başlatılamadı: {exc}") from exc
    stdout = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else result.stdout
    stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else result.stderr
    result.stdout = stdout or ""
    result.stderr = stderr or ""
    if check and result.returncode != 0:
        detail = (stderr or stdout or f"exit code {result.returncode}").strip()[-1200:]
        raise LinuxDesktopError(f"{argv[0]} başarısız oldu: {detail}")
    return result


def _hypr_json(command, *args):
    hyprctl = _which("hyprctl")
    if not hyprctl:
        raise LinuxDesktopError("Hyprland IPC kullanılamıyor: hyprctl bulunamadı.")
    result = _run([hyprctl, "-j", command, *map(str, args)], timeout=5)
    try:
        return json.loads(result.stdout or "null")
    except (TypeError, ValueError) as exc:
        raise LinuxDesktopError(f"hyprctl geçersiz JSON döndürdü ({command}).") from exc


def _hypr_dispatch(dispatcher, *args):
    hyprctl = _which("hyprctl")
    if not hyprctl:
        raise LinuxDesktopError("Hyprland IPC kullanılamıyor: hyprctl bulunamadı.")
    result = _run([hyprctl, "dispatch", dispatcher, *map(str, args)], timeout=8)
    return (result.stdout or "").strip()


def _session_info() -> dict:
    session = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get(
        "XDG_SESSION_DESKTOP", ""
    )
    desktop = desktop.strip() or "unknown"
    compositor = "Hyprland" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else desktop
    return {
        "session_type": session,
        "desktop": desktop,
        "compositor": compositor,
        "wayland_display": bool(os.environ.get("WAYLAND_DISPLAY")),
        "x11_display": bool(os.environ.get("DISPLAY")),
    }


def _extend_system_python_paths():
    """Make distro-installed GI modules visible inside a normal venv.

    PyGObject/AT-SPI is commonly distributed by the OS rather than PyPI.  A
    venv made by the installer therefore cannot see it by default even though
    the same Python ABI is used.  Adding only known system site-package paths
    keeps the project environment intact and lets the helper use the desktop's
    native accessibility bindings.
    """

    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        Path(sys.base_prefix) / "lib" / f"python{version}" / "site-packages",
        Path(sys.base_prefix) / "lib" / f"python{version}" / "dist-packages",
        Path("/usr/lib") / f"python{version}" / "site-packages",
        Path("/usr/lib") / f"python{version}" / "dist-packages",
        Path("/usr/local/lib") / f"python{version}" / "site-packages",
        Path("/usr/local/lib") / f"python{version}" / "dist-packages",
    ]
    for candidate in candidates:
        value = str(candidate)
        if candidate.is_dir() and value not in sys.path:
            sys.path.append(value)


def _load_gi():
    try:
        import gi
    except ImportError:
        _extend_system_python_paths()
        try:
            import gi
        except ImportError as exc:
            raise LinuxDesktopError(
                "AT-SPI/portal için PyGObject eksik. Dağıtımınızın python-gobject ve at-spi2-core paketlerini kurun."
            ) from exc
    return gi


def _load_atspi():
    gi = _load_gi()
    try:
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError) as exc:
        raise LinuxDesktopError(
            "AT-SPI2 typelib bulunamadı. at-spi2-core paketini kurun ve oturumu yeniden başlatın."
        ) from exc
    return Atspi


def _load_gio():
    gi = _load_gi()
    try:
        gi.require_version("Gio", "2.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as exc:
        raise LinuxDesktopError(
            "XDG portal için GIO/GLib eksik. Dağıtımınızın python-gobject paketini kurun."
        ) from exc
    return Gio, GLib


def _atspi_desktop():
    if not _atspi_bus_available():
        raise LinuxDesktopError(
            "AT-SPI2 erişilebilirlik bus'ı bulunamadı; at-spi-bus-launcher ve session D-Bus'ı kontrol edin."
        )
    Atspi = _load_atspi()
    try:
        Atspi.init()
        desktop = Atspi.get_desktop(0)
    except Exception as exc:
        raise LinuxDesktopError(
            "AT-SPI2 masaüstü servisine bağlanılamadı; at-spi2-core ve session D-Bus'ı kontrol edin."
        ) from exc
    if desktop is None:
        raise LinuxDesktopError(
            "AT-SPI2 masaüstü ağacı boş. Erişilebilirlik servisinin çalıştığından emin olun."
        )
    return Atspi, desktop


def _atspi_bus_available() -> bool:
    """Avoid calling Atspi.init when its native library cannot reach D-Bus.

    Some at-spi2-core builds abort the process from their C layer instead of
    returning an exception when the accessibility bus is absent.  A normal
    D-Bus NameHasOwner request is safe to probe and lets the JSON helper fail
    honestly without taking down the parent Live session.
    """

    try:
        Gio, GLib = _load_gio()
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", ("org.a11y.Bus",)),
            None,
            Gio.DBusCallFlags.NONE,
            1_000,
            None,
        )
        return bool(reply.unpack()[0])
    except Exception:
        return False


def _accessible_children(item):
    try:
        count = int(item.get_child_count())
    except Exception:
        return []
    children = []
    for index in range(max(0, min(count, 400))):
        try:
            child = item.get_child_at_index(index)
        except Exception:
            child = None
        if child is not None:
            children.append(child)
    return children


def _accessible_role(item) -> str:
    try:
        return str(item.get_role_name() or "")
    except Exception:
        return ""


def _accessible_label(item) -> str:
    try:
        name = str(item.get_name() or "")
    except Exception:
        name = ""
    if name:
        return name[:300]
    try:
        return str(item.get_description() or "")[:300]
    except Exception:
        return ""


def _accessible_enabled(Atspi, item) -> bool:
    try:
        return bool(item.get_state_set().contains(Atspi.StateType.ENABLED))
    except Exception:
        return False


def _accessible_actions(item) -> list[str]:
    try:
        count = int(item.get_n_actions())
    except Exception:
        return []
    actions = []
    for index in range(max(0, min(count, 32))):
        try:
            name = str(item.get_action_name(index) or "")
        except Exception:
            name = ""
        if name:
            actions.append(name[:100])
    return actions


def _accessible_value(item, role: str) -> str | None:
    lower_role = role.lower()
    if "password" in lower_role or "secure" in lower_role:
        return None
    try:
        value_iface = item.get_value_iface()
        if value_iface is not None:
            value = value_iface.get_current_value()
            if value is not None:
                return str(value)[:700]
    except Exception:
        pass
    try:
        text_iface = item.get_text_iface()
        if text_iface is not None:
            count = int(text_iface.get_character_count())
            if count:
                return str(text_iface.get_text(0, min(count, 700)))[:700]
    except Exception:
        pass
    try:
        value = item.get_data()
        if isinstance(value, (str, int, float, bool)):
            return str(value)[:700]
    except Exception:
        pass
    return None


def _atspi_apps(Atspi, desktop) -> list[tuple[int, object]]:
    result = []
    for index, app in enumerate(_accessible_children(desktop)):
        try:
            pid = int(app.get_process_id())
        except Exception:
            pid = -1
        if pid > 0:
            result.append((index, app))
    return result


def _active_hypr_window() -> dict:
    try:
        value = _hypr_json("activewindow")
        return value if isinstance(value, dict) else {}
    except LinuxDesktopError:
        return {}


def _hypr_clients() -> list[dict]:
    value = _hypr_json("clients")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _hypr_monitors() -> list[dict]:
    value = _hypr_json("monitors")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normal_window(item: dict) -> dict:
    workspace = item.get("workspace") if isinstance(item.get("workspace"), dict) else {}
    position = item.get("at")
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        position = item.get("x")
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        position = [item.get("x", 0), item.get("y", 0)]
    size = item.get("size")
    if not isinstance(size, (list, tuple)) or len(size) < 2:
        size = [item.get("w", 0), item.get("h", 0)]
    return {
        "address": str(item.get("address", "")),
        "pid": int(item.get("pid", -1) or -1),
        "class": str(item.get("class", "")),
        "initial_class": str(item.get("initialClass", item.get("initial_class", ""))),
        "title": str(item.get("title", ""))[:500],
        "initial_title": str(item.get("initialTitle", item.get("initial_title", "")))[:500],
        "x": position[0],
        "y": position[1],
        "width": size[0],
        "height": size[1],
        "workspace": workspace.get("name", workspace.get("id", "")),
        "monitor": item.get("monitor", ""),
        "floating": bool(item.get("floating", False)),
        "fullscreen": bool(item.get("fullscreen", False)),
        "mapped": bool(item.get("mapped", True)),
        "hidden": bool(item.get("hidden", False)),
        "pinned": bool(item.get("pinned", False)),
        "focused": bool(item.get("focusHistoryID", -1) == 0),
    }


def _x11_clients() -> list[dict]:
    wmctrl = _which("wmctrl")
    if not wmctrl:
        return []
    result = _run([wmctrl, "-lGx"], timeout=5, check=False)
    clients = []
    for line in (result.stdout or "").splitlines():
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        address, desktop, x, y, width, height, _host, wm_class, title = parts
        try:
            geometry = [int(x), int(y), int(width), int(height)]
        except ValueError:
            continue
        clients.append(
            {
                "address": address,
                "pid": -1,
                "class": wm_class,
                "title": title[:500],
                "x": geometry[0],
                "y": geometry[1],
                "width": geometry[2],
                "height": geometry[3],
                "workspace": desktop,
                "monitor": "",
                "floating": False,
                "fullscreen": False,
                "mapped": True,
                "hidden": False,
                "pinned": False,
                "focused": False,
            }
        )
    return clients


def _window_snapshot() -> tuple[list[dict], list[dict], dict]:
    clients = []
    monitors = []
    active = {}
    if _which("hyprctl") and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            clients = [_normal_window(item) for item in _hypr_clients()]
            monitors = _hypr_monitors()
            active_window = _active_hypr_window()
            active = _normal_window(active_window) if active_window else {}
        except LinuxDesktopError:
            clients = []
    if not clients:
        clients = _x11_clients()
    return clients, monitors, active


def _accessibility_snapshot(args, active: dict) -> dict:
    Atspi, desktop = _atspi_desktop()
    apps = _atspi_apps(Atspi, desktop)
    requested_pid = args.get("pid")
    pid = int(requested_pid) if requested_pid is not None else int(active.get("pid", -1) or -1)
    selected = None
    app_index = None
    for index, app in apps:
        try:
            app_pid = int(app.get_process_id())
        except Exception:
            continue
        if pid > 0 and app_pid == pid:
            selected, app_index = app, index
            pid = app_pid
            break
    if selected is None and len(apps) == 1:
        app_index, selected = apps[0]
        pid = int(selected.get_process_id())
    if selected is None:
        return {
            "available": True,
            "pid": pid if pid > 0 else None,
            "nodes": [],
            "detail": "Aktif pencere AT-SPI2 uygulama ağacında bulunamadı; pid ile yeniden inspect deneyin.",
        }

    path = [int(index) for index in args.get("path", [])]
    element = selected
    for index in path:
        children = _accessible_children(element)
        if not 0 <= index < len(children):
            raise LinuxDesktopError("Accessibility yolu değişti; yeniden inspect yapın.")
        element = children[index]

    depth = max(1, min(int(args.get("depth", 5)), 10))
    nodes = []
    seen = set()
    clipped = False
    used_bytes = 0

    def walk(item, current_path, remaining):
        nonlocal clipped, used_bytes
        if len(nodes) >= 180 or used_bytes >= 22_000:
            clipped = True
            return
        identity = id(item)
        if identity in seen:
            return
        seen.add(identity)
        role = _accessible_role(item)
        node = {
            "path": current_path,
            "role": role,
            "label": _accessible_label(item),
            "enabled": _accessible_enabled(Atspi, item),
            "actions": _accessible_actions(item),
        }
        value = _accessible_value(item, role)
        if value is not None:
            node["value"] = value
        children = _accessible_children(item)
        node["child_count"] = len(children)
        size = len(json.dumps(node, ensure_ascii=False).encode("utf-8"))
        if used_bytes + size > 22_000:
            clipped = True
            return
        used_bytes += size
        nodes.append(node)
        if remaining:
            for index, child in enumerate(children):
                walk(child, current_path + [index], remaining - 1)
                if clipped:
                    break
        elif children:
            node["children_omitted"] = True

    walk(element, path, depth)
    return {
        "available": True,
        "pid": pid,
        "application_path": [app_index] if app_index is not None else [],
        "root_path": path,
        "nodes": nodes,
        "truncated": clipped,
        "detail": "Path indeksleri seçili uygulamanın AT-SPI2 child sırasıdır. Her işlemden sonra inspect yapın; arayüz değişebilir.",
    }


def _accessibility_resolve(args):
    Atspi, desktop = _atspi_desktop()
    apps = _atspi_apps(Atspi, desktop)
    active = _active_hypr_window()
    requested_pid = args.get("pid")
    pid = int(requested_pid) if requested_pid is not None else int(active.get("pid", -1) or -1)
    selected = None
    for _index, app in apps:
        try:
            app_pid = int(app.get_process_id())
        except Exception:
            continue
        if pid > 0 and app_pid == pid:
            selected, pid = app, app_pid
            break
    if selected is None:
        raise LinuxDesktopError("AT-SPI2 uygulaması bulunamadı; önce aktif pencereyi inspect edin ve pid gönderin.")
    element = selected
    for index in [int(index) for index in args.get("path", [])]:
        children = _accessible_children(element)
        if not 0 <= index < len(children):
            raise LinuxDesktopError("Accessibility yolu değişti; yeniden inspect yapın.")
        element = children[index]
    return Atspi, pid, element


def _ax_action(args):
    Atspi, pid, element = _accessibility_resolve(args)
    role = _accessible_role(element)
    label = _accessible_label(element)
    if role != str(args.get("role", "")) or label != str(args.get("label", "")):
        raise LinuxDesktopError("Element değişti; işlemden önce yeniden inspect yapın.")
    action_names = _accessible_actions(element)
    if not action_names:
        raise LinuxDesktopError("Bu accessibility elementinin uygulanabilir action'ı yok.")
    desired = str(args.get("action_name", "")).lower()
    index = None
    for candidate in (desired, "click", "press", "activate", "toggle"):
        if not candidate:
            continue
        for action_index, name in enumerate(action_names):
            if candidate == name.lower() or candidate in name.lower():
                index = action_index
                break
        if index is not None:
            break
    if index is None:
        index = 0
    if not bool(element.do_action(index)):
        raise LinuxDesktopError(f"AT-SPI2 action uygulanamadı: {action_names[index]}")
    return {"ok": True, "pid": pid, "action": action_names[index], "detail": "Sonucu inspect ile doğrulayın."}


def _ax_set(args):
    _Atspi, pid, element = _accessibility_resolve(args)
    role = _accessible_role(element)
    label = _accessible_label(element)
    if role != str(args.get("role", "")) or label != str(args.get("label", "")):
        raise LinuxDesktopError("Element değişti; işlemden önce yeniden inspect yapın.")
    text = args.get("text")
    if not isinstance(text, str):
        raise LinuxDesktopError("AT-SPI2 set için text alanı metin olmalı.")
    try:
        editable = element.get_editable_text_iface()
        if editable is None or not bool(editable.set_text_contents(text)):
            raise LinuxDesktopError("Element düzenlenebilir metin kabul etmedi.")
    except LinuxDesktopError:
        raise
    except Exception as exc:
        raise LinuxDesktopError(f"AT-SPI2 metin değeri yazılamadı: {exc}") from exc
    return {"ok": True, "pid": pid, "detail": "Değişikliği inspect ile doğrulayın."}


def _monitor_payload(monitors):
    result = []
    for monitor in monitors:
        if not isinstance(monitor, dict):
            continue
        result.append(
            {
                "name": monitor.get("name", ""),
                "description": monitor.get("description", ""),
                "x": monitor.get("x", 0),
                "y": monitor.get("y", 0),
                "width": monitor.get("width", 0),
                "height": monitor.get("height", 0),
                "scale": monitor.get("scale", 1),
                "focused": bool(monitor.get("focused", False)),
                "active_workspace": monitor.get("activeWorkspace", {}),
            }
        )
    return result


def _inspect(args):
    clients, monitors, active = _window_snapshot()
    result = {
        "ok": True,
        "platform": "linux",
        "session": _session_info(),
        "frontmost": active,
        "windows": clients[:180],
        "monitors": _monitor_payload(monitors),
        "capabilities": capabilities(),
    }
    try:
        result["accessibility"] = _accessibility_snapshot(args, active)
    except LinuxDesktopError as exc:
        result["accessibility"] = {
            "available": False,
            "nodes": [],
            "error": str(exc),
        }
    result["detail"] = "Linux masaüstü durumu. Eylemlerden sonra arayüzü yeniden inspect/screenshot edin."
    return result


def _convert_to_jpeg(source: Path, destination: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise LinuxDesktopError("Screenshot için Pillow kurulmalı.") from exc
    try:
        with Image.open(source) as picture:
            picture.thumbnail((1600, 1600))
            size = picture.size
            picture.convert("RGB").save(destination, "JPEG", quality=82, optimize=True)
            return size
    except (OSError, ValueError) as exc:
        raise LinuxDesktopError(f"Screenshot JPEG'e dönüştürülemedi: {exc}") from exc


def _portal_response(connection, GLib, handle, timeout=20):
    response = {}

    def on_signal(_connection, _sender, path, _interface, signal_name, parameters):
        if path == handle and signal_name == "Response":
            try:
                values = parameters.unpack()
                response["code"] = int(values[0])
                response["results"] = values[1] if len(values) > 1 else {}
            except Exception as exc:
                response["error"] = str(exc)

    subscription = connection.signal_subscribe(
        None,
        "org.freedesktop.portal.Request",
        "Response",
        None,
        None,
        0,
        on_signal,
        None,
    )
    try:
        context = GLib.MainContext.default()
        deadline = time.monotonic() + timeout
        while not response and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)
    finally:
        connection.signal_unsubscribe(subscription)
    if not response:
        raise LinuxDesktopError("XDG portal yanıtı zaman aşımına uğradı.")
    if response.get("error"):
        raise LinuxDesktopError(f"XDG portal yanıtı okunamadı: {response['error']}")
    if response.get("code") != 0:
        raise LinuxDesktopError("XDG portal isteği kullanıcı tarafından reddedildi veya iptal edildi.")
    return response.get("results", {})


def _portal_screenshot(destination: Path, args):
    Gio, GLib = _load_gio()
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES
            | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS,
            None,
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            None,
        )
        options = {
            "handle_token": GLib.Variant("s", f"kyros_{uuid.uuid4().hex}"),
            "modal": GLib.Variant("b", False),
            "interactive": GLib.Variant("b", bool(args.get("select_region", False))),
        }
        target = args.get("target")
        if target in ("active_window", "active-window"):
            options["target"] = GLib.Variant("u", 8)
        elif args.get("select_region"):
            options["target"] = GLib.Variant("u", 4)
        else:
            options["target"] = GLib.Variant("u", 1)
        reply = proxy.call_sync(
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            Gio.DBusCallFlags.NONE,
            15_000,
            None,
        )
        handle = reply.unpack()[0]
        values = _portal_response(connection, GLib, handle)
        uri = values.get("uri") if isinstance(values, dict) else None
        if not uri:
            raise LinuxDesktopError("XDG screenshot portal bir dosya URI'si döndürmedi.")
        parsed = urlparse(str(uri))
        if parsed.scheme != "file":
            raise LinuxDesktopError("XDG screenshot portal yerel dosya döndürmedi.")
        source = Path(unquote(parsed.path))
        if not source.is_file():
            raise LinuxDesktopError("XDG screenshot portal dosyası bulunamadı.")
        size = _convert_to_jpeg(source, destination)
        return size
    except LinuxDesktopError:
        raise
    except Exception as exc:
        raise LinuxDesktopError(f"XDG screenshot portal kullanılamadı: {exc}") from exc


def _screenshot(args):
    image_path = Path(args["image_path"])
    image_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = image_path.with_suffix(".png")
    source = None
    command_detail = ""
    grim = _which("grim")
    monitor = args.get("monitor") or args.get("output")
    region = args.get("region")
    portal_only = False
    if isinstance(region, dict):
        try:
            region = f"{int(region['x'])},{int(region['y'])} {int(region['width'])}x{int(region['height'])}"
        except (KeyError, TypeError, ValueError) as exc:
            raise LinuxDesktopError("region x/y/width/height alanlarını içermeli.") from exc
    if args.get("select_region") and not region:
        slurp = _which("slurp")
        if slurp:
            result = _run([slurp, "-f", "%x,%y %wx%h"], timeout=60)
            region = (result.stdout or "").strip()
            if not region:
                raise LinuxDesktopError("Bölge seçimi iptal edildi.")
        elif grim:
            # Let the XDG Screenshot portal provide its own interactive region
            # picker; a full-screen grim capture would violate the request.
            grim = None
            portal_only = True
        else:
            portal_only = True
    if grim:
        argv = [grim]
        if monitor:
            argv.extend(["-o", str(monitor)])
        if region:
            argv.extend(["-g", str(region)])
        argv.append(str(raw_path))
        result = _run(argv, timeout=20, check=False)
        if result.returncode == 0 and raw_path.exists():
            source = raw_path
            command_detail = "grim"
    if source is None and (monitor or region):
        raise LinuxDesktopError(
            "Belirli monitor/output veya region ekran görüntüsü için çalışan grim gerekir."
        )
    if source is None and not portal_only and not os.environ.get("WAYLAND_DISPLAY"):
        # Common X11 fallbacks.  They are tried only after the compositor-native
        # path; failure output is retained for a useful final error.
        fallbacks = []
        if _which("gnome-screenshot"):
            fallbacks.append([_which("gnome-screenshot"), "-f", str(raw_path)])
        if _which("scrot"):
            fallbacks.append([_which("scrot"), str(raw_path)])
        if _which("maim"):
            fallbacks.append([_which("maim"), str(raw_path)])
        for argv in fallbacks:
            result = _run(argv, timeout=20, check=False)
            if result.returncode == 0 and raw_path.exists():
                source = raw_path
                command_detail = Path(argv[0]).name
                break
    if source is None:
        try:
            size = _portal_screenshot(image_path, args)
            command_detail = "xdg-desktop-portal"
        except LinuxDesktopError as portal_error:
            raise LinuxDesktopError(
                "Screenshot alınamadı: grim/gnome-screenshot/scrot/maim ve XDG portal başarısız. "
                + str(portal_error)
            ) from portal_error
    else:
        size = _convert_to_jpeg(source, image_path)
    try:
        if raw_path.exists() and raw_path != image_path:
            raw_path.unlink()
    except OSError:
        pass
    clients, monitors, active = _window_snapshot()
    return {
        "ok": True,
        "image_pixels": list(size),
        "frontmost": active,
        "windows": clients[:100],
        "monitors": _monitor_payload(monitors),
        "capture_backend": command_detail,
        "coordinate_mapping": "Global Hyprland coordinates use monitor x/y plus image-relative pixels scaled by image_pixels.",
        "detail": "Ekran görüntüsü canlı oturumun video bağlamına gönderildi; işlem sonrası yeniden screenshot/inspect ile doğrulayın.",
    }


_MODIFIER_MAP = {
    "command": ("logo", "SUPER"),
    "super": ("logo", "SUPER"),
    "meta": ("logo", "SUPER"),
    "shift": ("shift", "SHIFT"),
    "option": ("alt", "ALT"),
    "alt": ("alt", "ALT"),
    "control": ("ctrl", "CTRL"),
    "ctrl": ("ctrl", "CTRL"),
}


def _input_modifiers(values):
    result = []
    for value in values or []:
        key = str(value).lower()
        if key not in _MODIFIER_MAP:
            raise LinuxDesktopError(f"Desteklenmeyen modifier: {value}")
        result.append(_MODIFIER_MAP[key])
    return result


def _safe_selector_text(value: str) -> bool:
    return bool(value and len(value) <= 300 and not any(char in value for char in ",\n\r\x00"))


def _workspace_target(value) -> str:
    text = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:+-]+", text):
        raise LinuxDesktopError("Hyprland workspace hedefi geçersiz veya ayraç içeriyor.")
    return text


def _x11_control_allowed() -> bool:
    if not os.environ.get("DISPLAY"):
        return False
    # xdotool cannot control native Wayland surfaces.  An explicit opt-in is
    # available for users who intentionally target XWayland applications.
    return not os.environ.get("WAYLAND_DISPLAY") or os.environ.get(
        "KYROS_ALLOW_XWAYLAND_XDOTOOL"
    ) == "1"


def _target_selector(args):
    if args.get("address"):
        address = str(args["address"])
        if not re.fullmatch(r"0x[0-9a-fA-F]+|[0-9a-fA-F]+", address):
            raise LinuxDesktopError("Hyprland window address geçersiz.")
        if int(address, 16) <= 0:
            raise LinuxDesktopError("Hyprland window address geçersiz.")
        return f"address:{address}"
    if args.get("pid") is not None:
        try:
            pid = int(args["pid"])
        except (TypeError, ValueError) as exc:
            raise LinuxDesktopError("pid sayı olmalı.") from exc
        if pid <= 0:
            raise LinuxDesktopError("pid pozitif olmalı.")
        return f"pid:{pid}"
    if args.get("class"):
        value = str(args["class"])
        if not _safe_selector_text(value):
            raise LinuxDesktopError("Hyprland class filtresi boş, uzun veya ayraç içeriyor.")
        return f"class:{value}"
    if args.get("title"):
        value = str(args["title"])
        if not _safe_selector_text(value):
            raise LinuxDesktopError("Hyprland title filtresi boş, uzun veya ayraç içeriyor.")
        return f"title:{value}"
    return "activewindow"


def _hypr_window_action(args):
    operation = str(args.get("operation") or args.get("window_action") or "").lower()
    selector = _target_selector(args)
    if operation in ("focus", "activate"):
        detail = _hypr_dispatch("focuswindow", selector)
    elif operation in ("close", "quit"):
        detail = _hypr_dispatch("closewindow", selector)
    elif operation in ("toggle_floating", "toggle-floating", "float"):
        detail = _hypr_dispatch("togglefloating", selector)
    elif operation in ("center", "center_window"):
        detail = _hypr_dispatch("centerwindow", selector)
    elif operation in ("pin", "toggle_pin"):
        detail = _hypr_dispatch("pin", selector)
    elif operation in ("fullscreen", "toggle_fullscreen"):
        if selector != "activewindow":
            _hypr_dispatch("focuswindow", selector)
        detail = _hypr_dispatch("fullscreen")
    elif operation in ("move", "move_window"):
        if args.get("x") is None or args.get("y") is None:
            raise LinuxDesktopError("Pencere taşıma için x ve y gerekir.")
        detail = _hypr_dispatch(
            "movewindowpixel", f"exact {int(args['x'])} {int(args['y'])},{selector}"
        )
    elif operation in ("resize", "resize_window"):
        if args.get("width") is None or args.get("height") is None:
            raise LinuxDesktopError("Pencere boyutlandırma için width ve height gerekir.")
        detail = _hypr_dispatch(
            "resizewindowpixel",
            f"exact {int(args['width'])} {int(args['height'])},{selector}",
        )
    elif operation in ("workspace", "move_workspace"):
        workspace = args.get("workspace")
        if workspace is None:
            raise LinuxDesktopError("Workspace hedefi gerekir.")
        workspace = _workspace_target(workspace)
        dispatcher = "movetoworkspacesilent" if args.get("silent") else "movetoworkspace"
        detail = _hypr_dispatch(dispatcher, f"{workspace},{selector}")
    elif operation in ("next", "cycle_next"):
        detail = _hypr_dispatch("cyclenext")
    elif operation in ("previous", "cycle_previous"):
        detail = _hypr_dispatch("cyclenext", "prev")
    else:
        raise LinuxDesktopError(
            "Bilinmeyen window işlemi. focus, close, move, resize, workspace, fullscreen, float, pin veya center kullanın."
        )
    _clients, _monitors, active = _window_snapshot()
    return {"ok": True, "operation": operation, "detail": detail, "frontmost": active}


def _clipboard_backend(selection):
    if _which("wl-paste") and _which("wl-copy"):
        return "wayland"
    if _which("xclip"):
        return "xclip"
    if _which("xsel"):
        return "xsel"
    raise LinuxDesktopError("Clipboard için wl-clipboard, xclip veya xsel bulunamadı.")


def _clipboard_read(args):
    selection = str(args.get("selection", "clipboard"))
    backend = _clipboard_backend(selection)
    if backend == "wayland":
        argv = [_which("wl-paste"), "--no-newline"]
        if selection == "primary":
            argv.append("--primary")
        result = _run(argv, timeout=8)
    elif backend == "xclip":
        argv = [_which("xclip"), "-selection", "primary" if selection == "primary" else "clipboard", "-o"]
        result = _run(argv, timeout=8)
    else:
        argv = [_which("xsel"), "--primary" if selection == "primary" else "--clipboard", "--output"]
        result = _run(argv, timeout=8)
    return {"ok": True, "text": (result.stdout or "")[:24_000], "selection": selection}


def _clipboard_write(args):
    text = args.get("text")
    if not isinstance(text, str):
        raise LinuxDesktopError("Clipboard yazmak için text alanı metin olmalı.")
    selection = str(args.get("selection", "clipboard"))
    backend = _clipboard_backend(selection)
    if backend == "wayland":
        argv = [_which("wl-copy")]
        if selection == "primary":
            argv.append("--primary")
        _run(argv, input_data=text.encode("utf-8"), timeout=8)
    elif backend == "xclip":
        _run(
            [_which("xclip"), "-selection", "primary" if selection == "primary" else "clipboard", "-i"],
            input_data=text.encode("utf-8"),
            timeout=8,
        )
    else:
        _run(
            [_which("xsel"), "--primary" if selection == "primary" else "--clipboard", "--input"],
            input_data=text.encode("utf-8"),
            timeout=8,
        )
    return {"ok": True, "selection": selection, "characters": len(text)}


def _wtype_key(key, modifiers):
    wtype = _which("wtype")
    if not wtype:
        return None
    argv = [wtype]
    for wayland_name, _ in modifiers:
        argv.extend(["-M", wayland_name])
    argv.extend(["-k", str(key)])
    for wayland_name, _ in reversed(modifiers):
        argv.extend(["-m", wayland_name])
    _run(argv, timeout=8)
    return {"backend": "wtype"}


_PORTAL_MODIFIER_CODES = {
    "CTRL": 29,
    "SHIFT": 42,
    "ALT": 56,
    "SUPER": 125,
}
_PORTAL_KEYSYMS = {
    "enter": 0xFF0D,
    "return": 0xFF0D,
    "escape": 0xFF1B,
    "esc": 0xFF1B,
    "tab": 0xFF09,
    "backspace": 0xFF08,
    "delete": 0xFFFF,
    "insert": 0xFF63,
    "home": 0xFF50,
    "end": 0xFF57,
    "pageup": 0xFF55,
    "pagedown": 0xFF56,
    "left": 0xFF51,
    "up": 0xFF52,
    "right": 0xFF53,
    "down": 0xFF54,
    "space": 0x20,
    "minus": 0x2D,
    "equal": 0x3D,
    "plus": 0x2B,
    "comma": 0x2C,
    "period": 0x2E,
    "dot": 0x2E,
    "slash": 0x2F,
    "backslash": 0x5C,
    "semicolon": 0x3B,
    "apostrophe": 0x27,
    "quote": 0x22,
    "leftbracket": 0x5B,
    "rightbracket": 0x5D,
}


def _portal_keysym(key):
    value = str(key)
    lower = value.lower()
    if lower in _PORTAL_KEYSYMS:
        return _PORTAL_KEYSYMS[lower]
    if re.fullmatch(r"f(?:[1-9]|1[0-2])", lower):
        return 0xFFBE + int(lower[1:]) - 1
    if len(value) == 1:
        return ord(value)
    if re.fullmatch(r"0x[0-9a-fA-F]+", value):
        return int(value, 16)
    raise LinuxDesktopError(f"Portal keysym için bilinmeyen key: {key}")


def _portal_proxy(interface):
    Gio, GLib = _load_gio()
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES
            | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS,
            None,
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            interface,
            None,
        )
        return Gio, GLib, connection, proxy
    except Exception as exc:
        raise LinuxDesktopError(f"XDG portal oturumu açılamadı: {exc}") from exc


def _portal_interfaces() -> set[str]:
    """Return interfaces actually exported by the session portal service."""

    Gio, GLib = _load_gio()
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = connection.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.DBus.Introspectable",
            "Introspect",
            GLib.Variant("()", ()),
            None,
            Gio.DBusCallFlags.NONE,
            2_000,
            None,
        )
        xml = reply.unpack()[0]
        return set(re.findall(r'<interface\s+name="([^"]+)"', str(xml)))
    except Exception:
        return set()


def _portal_request(Gio, GLib, connection, proxy, method, signature, values):
    try:
        reply = proxy.call_sync(
            method,
            GLib.Variant(signature, values),
            Gio.DBusCallFlags.NONE,
            20_000,
            None,
        )
        handle = reply.unpack()[0]
        return _portal_response(connection, GLib, handle)
    except LinuxDesktopError:
        raise
    except Exception as exc:
        raise LinuxDesktopError(f"XDG portal {method} başarısız oldu: {exc}") from exc


def _portal_remote_session(types):
    Gio, GLib, connection, proxy = _portal_proxy(
        "org.freedesktop.portal.RemoteDesktop"
    )
    session = None
    try:
        token = f"kyros_{uuid.uuid4().hex}"
        created = _portal_request(
            Gio,
            GLib,
            connection,
            proxy,
            "CreateSession",
            "(a{sv})",
            (
                {
                    "handle_token": GLib.Variant("s", token),
                    "session_handle_token": GLib.Variant("s", token),
                },
            ),
        )
        session = created.get("session_handle") if isinstance(created, dict) else None
        if not session:
            raise LinuxDesktopError("XDG portal remote session handle döndürmedi.")
        selected = _portal_request(
            Gio,
            GLib,
            connection,
            proxy,
            "SelectDevices",
            "(oa{sv})",
            (
                session,
                {
                    "types": GLib.Variant("u", int(types)),
                    # Keep permission alive for the current Kyros process;
                    # no long-lived restore token is stored by the helper.
                    "persist_mode": GLib.Variant("u", 1),
                },
            ),
        )
        started = _portal_request(
            Gio,
            GLib,
            connection,
            proxy,
            "Start",
            "(osa{sv})",
            (session, "", {}),
        )
        devices = int(started.get("devices", 0)) if isinstance(started, dict) else 0
        if devices & int(types) != int(types):
            raise LinuxDesktopError(
                f"XDG portal gerekli input yetkisini vermedi (istenen={types}, verilen={devices})."
            )
        return Gio, GLib, connection, proxy, session
    except BaseException:
        if session:
            try:
                Gio.DBusProxy.new_sync(
                    connection,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    "org.freedesktop.portal.Desktop",
                    session,
                    "org.freedesktop.portal.Session",
                    None,
                ).call_sync(
                    "Close",
                    GLib.Variant("()", ()),
                    Gio.DBusCallFlags.NONE,
                    5_000,
                    None,
                )
            except Exception:
                pass
        raise


def _portal_close(Gio, GLib, connection, session):
    try:
        proxy = Gio.DBusProxy.new_sync(
            connection,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.portal.Desktop",
            session,
            "org.freedesktop.portal.Session",
            None,
        )
        proxy.call_sync(
            "Close",
            GLib.Variant("()", ()),
            Gio.DBusCallFlags.NONE,
            5_000,
            None,
        )
    except Exception:
        pass


def _portal_keyboard_event(Gio, proxy, GLib, session, *, keycode=None, keysym=None, state):
    if keycode is not None:
        method = "NotifyKeyboardKeycode"
        signature = "(oa{sv}iu)"
        values = (session, {}, int(keycode), int(state))
    else:
        method = "NotifyKeyboardKeysym"
        signature = "(oa{sv}iu)"
        values = (session, {}, int(keysym), int(state))
    try:
        proxy.call_sync(
            method,
            GLib.Variant(signature, values),
            Gio.DBusCallFlags.NONE,
            8_000,
            None,
        )
    except Exception as exc:
        raise LinuxDesktopError(f"XDG portal klavye olayı başarısız oldu: {exc}") from exc


def _portal_key(args):
    mapped = _input_modifiers(args.get("modifiers", []))
    keycode = args.get("keycode") if not args.get("key") else None
    keysym = None if keycode is not None else _portal_keysym(args.get("key"))
    Gio, GLib, connection, proxy, session = _portal_remote_session(1)
    pressed_modifiers = []
    main_pressed = False
    try:
        modifier_codes = [_PORTAL_MODIFIER_CODES[item[1]] for item in mapped]
        for code in modifier_codes:
            _portal_keyboard_event(Gio, proxy, GLib, session, keycode=code, state=1)
            pressed_modifiers.append(code)
        _portal_keyboard_event(
            Gio,
            proxy,
            GLib,
            session,
            keycode=int(keycode) if keycode is not None else None,
            keysym=keysym,
            state=1,
        )
        main_pressed = True
        _portal_keyboard_event(
            Gio,
            proxy,
            GLib,
            session,
            keycode=int(keycode) if keycode is not None else None,
            keysym=keysym,
            state=0,
        )
        main_pressed = False
        for code in reversed(modifier_codes):
            _portal_keyboard_event(Gio, proxy, GLib, session, keycode=code, state=0)
        pressed_modifiers.clear()
    finally:
        if main_pressed:
            try:
                _portal_keyboard_event(
                    Gio,
                    proxy,
                    GLib,
                    session,
                    keycode=int(keycode) if keycode is not None else None,
                    keysym=keysym,
                    state=0,
                )
            except LinuxDesktopError:
                pass
        for code in reversed(pressed_modifiers):
            try:
                _portal_keyboard_event(
                    Gio, proxy, GLib, session, keycode=code, state=0
                )
            except LinuxDesktopError:
                pass
        _portal_close(Gio, GLib, connection, session)
    return {"backend": "xdg-remote-desktop"}


def _portal_type_text(text):
    Gio, GLib, connection, proxy, session = _portal_remote_session(1)
    try:
        for character in text:
            if character == "\n" or character == "\r":
                keysym = _PORTAL_KEYSYMS["enter"]
            elif character == "\t":
                keysym = _PORTAL_KEYSYMS["tab"]
            elif ord(character) <= 0xFF:
                keysym = ord(character)
            else:
                # XKB's Unicode keysym convention.
                keysym = 0x01000000 | ord(character)
            _portal_keyboard_event(
                Gio, proxy, GLib, session, keysym=keysym, state=1
            )
            _portal_keyboard_event(
                Gio, proxy, GLib, session, keysym=keysym, state=0
            )
    finally:
        _portal_close(Gio, GLib, connection, session)
    return {"backend": "xdg-remote-desktop"}


def _cursor_position():
    hyprctl = _which("hyprctl")
    if not hyprctl:
        return None
    result = _run([hyprctl, "cursorpos"], timeout=5, check=False)
    match = re.search(r"(-?\d+)\s*,\s*(-?\d+)", result.stdout or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _portal_pointer_motion(Gio, proxy, GLib, session, dx, dy):
    try:
        proxy.call_sync(
            "NotifyPointerMotion",
            GLib.Variant("(oa{sv}dd)", (session, {}, float(dx), float(dy))),
            Gio.DBusCallFlags.NONE,
            8_000,
            None,
        )
    except Exception as exc:
        raise LinuxDesktopError(f"XDG portal imleç hareketi başarısız oldu: {exc}") from exc


def _portal_pointer_button(Gio, proxy, GLib, session, button, state):
    code = {"left": 272, "right": 273, "middle": 274}.get(button)
    if code is None:
        raise LinuxDesktopError("Desteklenen mouse button: left, right, middle.")
    try:
        proxy.call_sync(
            "NotifyPointerButton",
            GLib.Variant("(oa{sv}iu)", (session, {}, code, int(state))),
            Gio.DBusCallFlags.NONE,
            8_000,
            None,
        )
    except Exception as exc:
        raise LinuxDesktopError(f"XDG portal mouse olayı başarısız oldu: {exc}") from exc


def _portal_mouse(args):
    if not (_which("hyprctl") and _session_info()["wayland_display"]):
        return None
    current = _cursor_position()
    if current is None:
        raise LinuxDesktopError("XDG portal için Hyprland cursorpos okunamadı.")
    x, y = int(float(args["x"])), int(float(args["y"]))
    button = str(args.get("button", "left")).lower()
    Gio, GLib, connection, proxy, session = _portal_remote_session(2)
    pressed = False
    try:
        _portal_pointer_motion(Gio, proxy, GLib, session, x - current[0], y - current[1])
        if args.get("action") == "drag":
            to_x = int(float(args["to_x"]))
            to_y = int(float(args["to_y"]))
            steps = max(2, min(32, int(args.get("steps", 16))))
            _portal_pointer_button(Gio, proxy, GLib, session, button, 1)
            pressed = True
            try:
                for step in range(1, steps + 1):
                    next_x = x + (to_x - x) * step / steps
                    next_y = y + (to_y - y) * step / steps
                    _portal_pointer_motion(
                        Gio, proxy, GLib, session, next_x - x, next_y - y
                    )
                    x, y = next_x, next_y
            finally:
                if pressed:
                    _portal_pointer_button(Gio, proxy, GLib, session, button, 0)
                    pressed = False
        else:
            clicks = max(1, min(3, int(args.get("clicks", 1))))
            for index in range(clicks):
                _portal_pointer_button(Gio, proxy, GLib, session, button, 1)
                _portal_pointer_button(Gio, proxy, GLib, session, button, 0)
                if index + 1 < clicks:
                    time.sleep(0.05)
    finally:
        if pressed:
            try:
                _portal_pointer_button(Gio, proxy, GLib, session, button, 0)
            except LinuxDesktopError:
                pass
        _portal_close(Gio, GLib, connection, session)
    return {"backend": "xdg-remote-desktop"}


def _portal_scroll(args):
    if not _session_info()["wayland_display"]:
        return None
    dx = float(args.get("dx", 0))
    dy = float(args.get("dy", 0))
    Gio, GLib, connection, proxy, session = _portal_remote_session(2)
    try:
        try:
            proxy.call_sync(
                "NotifyPointerAxis",
                GLib.Variant("(oa{sv}dd)", (session, {"finish": GLib.Variant("b", True)}, dx, dy)),
                Gio.DBusCallFlags.NONE,
                8_000,
                None,
            )
        except Exception as exc:
            raise LinuxDesktopError(f"XDG portal kaydırması başarısız oldu: {exc}") from exc
    finally:
        _portal_close(Gio, GLib, connection, session)
    return {"backend": "xdg-remote-desktop"}


def _hypr_key(key, modifiers, selector=None):
    hyprctl = _which("hyprctl")
    if not hyprctl:
        return None
    mod_text = " ".join(item[1] for item in modifiers)
    params = f"{mod_text},{key},{selector or ''}" if mod_text else f",{key},{selector or ''}"
    _run([hyprctl, "dispatch", "sendshortcut", params], timeout=8)
    return {"backend": "hyprland-sendshortcut"}


def _xdotool_key(key, modifiers):
    xdotool = _which("xdotool")
    if not xdotool or not _x11_control_allowed():
        return None
    x11_mods = {"CTRL": "ctrl", "SHIFT": "shift", "ALT": "alt", "SUPER": "super"}
    combo = "+".join([x11_mods[item[1]] for item in modifiers] + [str(key)])
    _run([xdotool, "key", "--clearmodifiers", combo], timeout=8)
    return {"backend": "xdotool"}


def _key(args):
    key = args.get("key")
    modifiers = list(args.get("modifiers", []))
    if not key and args.get("keycode") is None:
        raise LinuxDesktopError("key için key adı veya keycode gerekir.")
    if isinstance(key, str) and not modifiers and "+" in key:
        pieces = [piece.strip() for piece in key.split("+") if piece.strip()]
        if len(pieces) > 1:
            key = pieces[-1]
            modifiers = pieces[:-1]
    mapped = _input_modifiers(modifiers)
    if args.get("keycode") is not None and not key:
        ydotool = _which("ydotool")
        try:
            code = int(args["keycode"])
        except (TypeError, ValueError) as exc:
            raise LinuxDesktopError("keycode sayı olmalı.") from exc
        if not 0 <= code <= 65535:
            raise LinuxDesktopError("keycode 0 ile 65535 arasında olmalı.")
        if ydotool:
            try:
                _run([ydotool, "key", f"{code}:1", f"{code}:0"], timeout=8)
                return {"ok": True, "backend": "ydotool", "keycode": code}
            except LinuxDesktopError:
                pass
        if _session_info()["wayland_display"]:
            try:
                result = _portal_key({**args, "key": None, "keycode": code})
                if result:
                    return {"ok": True, **result, "keycode": code}
            except LinuxDesktopError:
                pass
        raise LinuxDesktopError("keycode için ydotool/ydotoold veya XDG Remote Desktop portal kullanılamadı.")
    try:
        result = _wtype_key(str(key), mapped)
        if result:
            return {"ok": True, **result}
    except LinuxDesktopError:
        pass
    try:
        result = _hypr_key(str(key), mapped, args.get("target"))
        if result:
            return {"ok": True, **result}
    except LinuxDesktopError:
        pass
    try:
        result = _xdotool_key(str(key), mapped)
        if result:
            return {"ok": True, **result}
    except LinuxDesktopError:
        pass
    try:
        result = _portal_key({**args, "key": key, "modifiers": modifiers})
        if result:
            return {"ok": True, **result}
    except LinuxDesktopError:
        pass
    raise LinuxDesktopError(
        "Klavye girdisi için wtype, ydotool, Hyprland sendshortcut, XDG Remote Desktop portal veya X11 xdotool kullanılamadı."
    )


def _type_clipboard(text):
    # Last resort for Wayland desktops without a virtual-keyboard utility.
    # Preserve and restore the clipboard so typing does not silently destroy
    # user data.  The final operation is still a normal Ctrl+V key event.
    try:
        old = _clipboard_read({})["text"]
    except LinuxDesktopError:
        old = None
    _clipboard_write({"text": text})
    try:
        paste = _key({"key": "v", "modifiers": ["control"]})
    finally:
        if old is not None:
            try:
                _clipboard_write({"text": old})
            except LinuxDesktopError:
                pass
    return {"backend": "clipboard-paste", "paste": paste}


def _type_text(args):
    text = args.get("text")
    if not isinstance(text, str):
        raise LinuxDesktopError("type_text için text alanı metin olmalı.")
    if not text:
        return {"ok": True, "characters": 0, "backend": "none"}
    wtype = _which("wtype")
    if wtype:
        try:
            _run([wtype, "-"], input_data=text.encode("utf-8"), timeout=30)
            return {"ok": True, "characters": len(text), "backend": "wtype"}
        except LinuxDesktopError:
            pass
    ydotool = _which("ydotool")
    if ydotool:
        try:
            _run([ydotool, "type", "--file", "-"], input_data=text.encode("utf-8"), timeout=30)
            return {"ok": True, "characters": len(text), "backend": "ydotool"}
        except LinuxDesktopError:
            pass
    xdotool = _which("xdotool")
    if xdotool and _x11_control_allowed():
        try:
            _run(
                [xdotool, "type", "--clearmodifiers", "--delay", "1", "--", text],
                timeout=30,
            )
            return {"ok": True, "characters": len(text), "backend": "xdotool"}
        except LinuxDesktopError:
            pass
    if _session_info()["wayland_display"]:
        try:
            result = _portal_type_text(text)
            return {"ok": True, "characters": len(text), **result}
        except LinuxDesktopError:
            pass
    if _which("wl-copy") and _which("wl-paste"):
        result = _type_clipboard(text)
        return {"ok": True, "characters": len(text), **result}
    raise LinuxDesktopError(
        "Unicode metin yazılamadı. Wayland için wtype/ydotool, X11 için xdotool kurun."
    )


def _ydotool_mouse(args):
    ydotool = _which("ydotool")
    if not ydotool:
        return None
    x, y = int(float(args["x"])), int(float(args["y"]))
    _run([ydotool, "mousemove", "--absolute", "-x", str(x), "-y", str(y)], timeout=8)
    action = args.get("action", "click")
    button = str(args.get("button", "left")).lower()
    button_code = {"left": 0, "right": 1, "middle": 2}.get(button)
    if button_code is None:
        raise LinuxDesktopError("Desteklenen mouse button: left, right, middle.")
    if action == "drag":
        to_x = int(float(args["to_x"]))
        to_y = int(float(args["to_y"]))
        pressed = False
        try:
            _run([ydotool, "click", hex(0x40 + button_code)], timeout=8)
            pressed = True
            steps = max(2, min(32, int(args.get("steps", 16))))
            for step in range(1, steps + 1):
                current_x = x + (to_x - x) * step // steps
                current_y = y + (to_y - y) * step // steps
                _run(
                    [
                        ydotool,
                        "mousemove",
                        "--absolute",
                        "-x",
                        str(current_x),
                        "-y",
                        str(current_y),
                    ],
                    timeout=8,
                )
        finally:
            if pressed:
                _run([ydotool, "click", hex(0x80 + button_code)], timeout=8)
    else:
        clicks = max(1, min(3, int(args.get("clicks", 1))))
        _run([ydotool, "click", "--repeat", str(clicks), hex(0xC0 + button_code)], timeout=8)
    return {"backend": "ydotool"}


def _xdotool_mouse(args):
    xdotool = _which("xdotool")
    if not xdotool or not _x11_control_allowed():
        return None
    x, y = int(float(args["x"])), int(float(args["y"]))
    _run([xdotool, "mousemove", "--sync", str(x), str(y)], timeout=8)
    button = {"left": "1", "right": "3", "middle": "2"}.get(str(args.get("button", "left")))
    if button is None:
        raise LinuxDesktopError("Desteklenen mouse button: left, right, middle.")
    if args.get("action") == "drag":
        pressed = False
        try:
            _run([xdotool, "mousedown", button], timeout=8)
            pressed = True
            _run(
                [
                    xdotool,
                    "mousemove",
                    "--sync",
                    str(int(float(args["to_x"]))),
                    str(int(float(args["to_y"]))),
                ],
                timeout=8,
            )
        finally:
            if pressed:
                _run([xdotool, "mouseup", button], timeout=8)
    else:
        clicks = max(1, min(3, int(args.get("clicks", 1))))
        _run([xdotool, "click", "--repeat", str(clicks), button], timeout=8)
    return {"backend": "xdotool"}


def _mouse(args):
    if args.get("x") is None or args.get("y") is None:
        raise LinuxDesktopError("Mouse işlemi için x ve y gerekir.")
    last_error = None
    for handler in (_ydotool_mouse, _xdotool_mouse, _portal_mouse):
        try:
            result = handler(args)
            if result:
                return {"ok": True, **result}
        except LinuxDesktopError as exc:
            last_error = exc
    raise LinuxDesktopError(
        str(last_error)
        if last_error
        else "Mouse tıklaması için Wayland'da ydotool/portal input veya X11'de xdotool gerekir."
    )


def _scroll(args):
    dx = int(args.get("dx", 0))
    dy = int(args.get("dy", 0))
    if not dx and not dy:
        return {"ok": True, "detail": "Kaydırma miktarı sıfırdı."}
    ydotool = _which("ydotool")
    if ydotool:
        try:
            _run(
                [ydotool, "mousemove", "--wheel", "-x", str(dx), "-y", str(dy)],
                timeout=8,
            )
            return {"ok": True, "backend": "ydotool"}
        except LinuxDesktopError:
            pass
    xdotool = _which("xdotool")
    if xdotool and _x11_control_allowed():
        button = "4" if dy > 0 else "5"
        count = max(1, min(100, abs(dy) // 40 or 1))
        if dx:
            button = "6" if dx > 0 else "7"
            count = max(1, min(100, abs(dx) // 40 or 1))
        _run([xdotool, "click", "--repeat", str(count), button], timeout=8)
        return {"ok": True, "backend": "xdotool"}
    if _session_info()["wayland_display"]:
        result = _portal_scroll(args)
        if result:
            return {"ok": True, **result}
    raise LinuxDesktopError("Kaydırma için ydotool veya X11 xdotool gerekir.")


def _launch(args):
    argv = args.get("argv")
    if argv is None:
        desktop_id = args.get("desktop_id")
        launch_path = args.get("path_name")
        if launch_path is None and isinstance(args.get("path"), str):
            launch_path = args["path"]
        if desktop_id:
            argv = [_which("gtk-launch") or "gtk-launch", str(desktop_id)]
        elif args.get("uri") or launch_path:
            argv = [_which("xdg-open") or "xdg-open", str(args.get("uri") or launch_path)]
        else:
            raise LinuxDesktopError("launch için argv, desktop_id, uri veya path gerekir.")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise LinuxDesktopError("launch argv boş olmayan bir string listesi olmalı.")
    if args.get("wait"):
        result = _run(argv, timeout=max(1, min(30, int(args.get("timeout", 10)))), check=False)
        return {
            "ok": result.returncode == 0,
            "argv": argv,
            "exit_code": result.returncode,
            "stdout": (result.stdout or "")[:4000],
            "stderr": (result.stderr or "")[:4000],
        }
    try:
        env = os.environ.copy()
        env.pop("GEMINI_API_KEY", None)
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        raise LinuxDesktopError(f"Uygulama başlatılamadı: {exc}") from exc
    return {"ok": True, "argv": argv, "pid": process.pid, "detail": "Süreç başlatıldı; pencereyi inspect ile doğrulayın."}


def _notify(args):
    command = _which("notify-send")
    if not command:
        raise LinuxDesktopError("Bildirim için notify-send bulunamadı.")
    title = str(args.get("notification_title") or args.get("title") or "Kyros")
    body = str(args.get("body", ""))
    argv = [command]
    urgency = args.get("urgency")
    if urgency in ("low", "normal", "critical"):
        argv.extend(["-u", urgency])
    if args.get("expire_ms") is not None:
        argv.extend(["-t", str(max(0, min(86_400_000, int(args["expire_ms"]))))])
    argv.extend([title, body])
    _run(argv, timeout=8)
    return {"ok": True, "detail": "Bildirim gönderildi."}


def _window_or_workspace(args):
    action = str(args.get("action", ""))
    if action == "window":
        return _hypr_window_action(args)
    if action == "workspace":
        workspace = args.get("workspace")
        if workspace is None:
            raise LinuxDesktopError("Workspace hedefi gerekir.")
        workspace = _workspace_target(workspace)
        detail = _hypr_dispatch("workspace", workspace)
        clients, monitors, active = _window_snapshot()
        return {"ok": True, "workspace": workspace, "detail": detail, "frontmost": active, "windows": clients[:100], "monitors": _monitor_payload(monitors)}
    raise LinuxDesktopError("window/workspace işlemi için action alanı gerekir.")


def capabilities() -> dict:
    session = _session_info()
    atspi_available = False
    try:
        _load_atspi()
        atspi_available = _atspi_bus_available()
    except LinuxDesktopError:
        pass
    portal_interfaces = set()
    try:
        portal_interfaces = _portal_interfaces()
    except LinuxDesktopError:
        pass
    screenshot_portal = "org.freedesktop.portal.Screenshot" in portal_interfaces
    remote_desktop_portal = "org.freedesktop.portal.RemoteDesktop" in portal_interfaces
    return {
        "platform": "linux",
        "session": session,
        "audio": {
            "pipewire": bool(_which("pw-record") and _which("pw-play")),
            "portaudio": bool(importlib.util.find_spec("sounddevice")),
        },
        "screen": {
            "grim": bool(_which("grim")),
            "slurp": bool(_which("slurp")),
            "portal_screenshot": screenshot_portal,
        },
        "accessibility": {"atspi2": atspi_available},
        "keyboard": {
            "wtype": bool(_which("wtype")),
            "ydotool": _ydotool_ready(),
            "hyprland_sendshortcut": bool(_which("hyprctl") and session["compositor"] == "Hyprland"),
            "xdotool": bool(_which("xdotool")),
            "xdg_remote_desktop": remote_desktop_portal,
        },
        "pointer": {
            "ydotool": _ydotool_ready(),
            "xdotool": bool(_which("xdotool")),
            "xdg_remote_desktop": remote_desktop_portal,
        },
        "windows": {"hyprland_ipc": bool(_which("hyprctl") and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")), "wmctrl": bool(_which("wmctrl"))},
        "clipboard": {"wayland": bool(_which("wl-copy") and _which("wl-paste")), "xclip": bool(_which("xclip")), "xsel": bool(_which("xsel"))},
        "launch": {"xdg_open": bool(_which("xdg-open")), "gtk_launch": bool(_which("gtk-launch"))},
        "media": {"playerctl": bool(_which("playerctl"))},
        "notify": bool(_which("notify-send")),
        "requirements": {
            "pointer_wayland": "ydotool + ydotoold veya kullanıcı izinli XDG Remote Desktop portal gerekir.",
            "unicode_wayland": "wtype tercih edilir; ydotool, XDG portal ve clipboard-paste fallbackleri denenir.",
            "accessibility": "python-gobject + at-spi2-core + çalışan AT-SPI2 session bus gerekir.",
        },
    }


def operate(args: dict) -> dict:
    if not isinstance(args, dict):
        raise LinuxDesktopError("Linux desktop tool argümanları object olmalı.")
    action = str(args.get("action", ""))
    if action == "inspect":
        return _inspect(args)
    if action == "screenshot":
        return _screenshot(args)
    if action in ("ax_press", "accessibility_press"):
        return _ax_action(args)
    if action in ("ax_set", "accessibility_set"):
        return _ax_set(args)
    if action in ("click", "drag"):
        return _mouse(args)
    if action == "scroll":
        return _scroll(args)
    if action == "key":
        return _key(args)
    if action == "type_text":
        return _type_text(args)
    if action == "clipboard_read":
        return _clipboard_read(args)
    if action == "clipboard_write":
        return _clipboard_write(args)
    if action in ("window", "workspace"):
        return _window_or_workspace(args)
    if action == "launch":
        return _launch(args)
    if action == "notify":
        return _notify(args)
    if action == "capabilities":
        return {"ok": True, "capabilities": capabilities()}
    raise LinuxDesktopError(f"Bilinmeyen Linux desktop işlemi: {action}")


if __name__ == "__main__":
    try:
        result = operate(json.load(sys.stdin))
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "capabilities": capabilities()}
    print(json.dumps(result, ensure_ascii=False))
