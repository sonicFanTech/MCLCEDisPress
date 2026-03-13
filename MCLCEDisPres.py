import configparser
import os
import sys
import time
import threading
import subprocess
import shlex
import webbrowser
from datetime import datetime

import psutil
from pypresence import Presence
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "MCLCE Discord Presence"
APP_SHORT_NAME = "MCLCEDisPres"
APP_VERSION = "1.2.0"
APP_AUTHOR = "sonic Fan Tech"
APP_COPYRIGHT = "Copyright (c) sonic Fan Tech"
APP_LICENSE = "MIT License"
APP_GITHUB_URL = "https://github.com/sonicFanTech/MCLCEDisPress/tree/main"
DISCORD_CLIENT_ID = "1481086293193789612"
DEFAULT_TARGET_EXE = "Minecraft.Client.exe"
DEFAULT_CHECK_INTERVAL = 5
DEFAULT_DETAILS = "Playing Minecraft Legacy PC Port"
DEFAULT_STATE = "In-game"
DEFAULT_LARGE_TEXT = "Minecraft Legacy PC Port"
DEFAULT_GAME_EXE_PATH = ""
DEFAULT_GAME_LAUNCH_ARGS = ""
DEFAULT_LAUNCH_COOLDOWN = 10
TEST_PRESENCE_SECONDS = 15
DISCORD_PROCESS_NAMES = {"discord.exe", "discordcanary.exe", "discordptb.exe"}

rpc = None
presence_active = False
session_start = None
monitoring_paused = False
tray_icon = None
last_status_text = "Starting..."
minecraft_running_last = False
config = None
config_path = None
settings_window = None
about_window = None
settings_vars = {}
last_game_launch_time = 0.0
auto_close_after_game_seen = False
shutdown_requested = False

stop_event = threading.Event()
lock = threading.Lock()
settings_lock = threading.Lock()
about_lock = threading.Lock()


def log(msg: str):
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    except Exception:
        pass


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def current_executable_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(__file__)


def current_base_name() -> str:
    return os.path.splitext(os.path.basename(current_executable_path()))[0]


def get_config_path() -> str:
    return os.path.join(app_dir(), f"{APP_SHORT_NAME}.ini")


def get_startup_dir() -> str:
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")


def get_startup_bat_path() -> str:
    return os.path.join(get_startup_dir(), f"{APP_SHORT_NAME}_Startup.bat")


def load_config():
    global config, config_path
    config_path = get_config_path()
    cfg = configparser.ConfigParser()

    cfg["General"] = {
        "target_exe": DEFAULT_TARGET_EXE,
        "check_interval": str(DEFAULT_CHECK_INTERVAL),
        "start_paused": "false",
        "start_with_windows": "false",
        "open_discord_on_start": "false",
        "game_exe_path": DEFAULT_GAME_EXE_PATH,
        "game_launch_args": DEFAULT_GAME_LAUNCH_ARGS,
        "launch_cooldown_seconds": str(DEFAULT_LAUNCH_COOLDOWN),
        "auto_close_after_game_closes": "true",
    }
    cfg["Presence"] = {
        "details": DEFAULT_DETAILS,
        "state": DEFAULT_STATE,
        "large_text": DEFAULT_LARGE_TEXT,
    }
    cfg["Tray"] = {
        "tray_tooltip_name": APP_NAME,
    }

    if os.path.exists(config_path):
        cfg.read(config_path, encoding="utf-8")
        if cfg.has_option("Tray", "icon_path"):
            cfg.remove_option("Tray", "icon_path")
        if cfg.has_option("Presence", "large_image"):
            cfg.remove_option("Presence", "large_image")
    else:
        save_config(cfg)

    config = cfg
    return cfg


def save_config(cfg=None):
    global config
    if cfg is None:
        cfg = config
    if cfg is None:
        return
    with open(get_config_path(), "w", encoding="utf-8") as f:
        cfg.write(f)
    config = cfg


def cfg_get(section, key, fallback=""):
    try:
        return config.get(section, key, fallback=fallback)
    except Exception:
        return fallback


def cfg_get_bool(section, key, fallback=False):
    try:
        return config.getboolean(section, key, fallback=fallback)
    except Exception:
        return fallback


def cfg_get_int(section, key, fallback=DEFAULT_CHECK_INTERVAL):
    try:
        value = int(config.get(section, key, fallback=str(fallback)))
        return max(1, value)
    except Exception:
        return fallback


def target_exe_name() -> str:
    return cfg_get("General", "target_exe", DEFAULT_TARGET_EXE).strip() or DEFAULT_TARGET_EXE


def check_interval_seconds() -> int:
    return cfg_get_int("General", "check_interval", DEFAULT_CHECK_INTERVAL)


def launch_cooldown_seconds() -> int:
    return cfg_get_int("General", "launch_cooldown_seconds", DEFAULT_LAUNCH_COOLDOWN)


def should_start_paused() -> bool:
    return cfg_get_bool("General", "start_paused", False)


def should_open_discord_on_start() -> bool:
    return cfg_get_bool("General", "open_discord_on_start", False)


def should_auto_close_after_game_closes() -> bool:
    return cfg_get_bool("General", "auto_close_after_game_closes", True)


def startup_enabled() -> bool:
    return os.path.exists(get_startup_bat_path())


def game_exe_path() -> str:
    return cfg_get("General", "game_exe_path", DEFAULT_GAME_EXE_PATH).strip()


def game_launch_args() -> str:
    return cfg_get("General", "game_launch_args", DEFAULT_GAME_LAUNCH_ARGS).strip()


def enable_startup() -> bool:
    try:
        startup_path = get_startup_bat_path()
        startup_dir = os.path.dirname(startup_path)
        os.makedirs(startup_dir, exist_ok=True)
        exe_path = current_executable_path()
        if getattr(sys, "frozen", False):
            command = f'@echo off\r\nstart "" "{exe_path}"\r\n'
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            python_to_use = pythonw if os.path.exists(pythonw) else sys.executable
            command = f'@echo off\r\nstart "" "{python_to_use}" "{exe_path}"\r\n'
        with open(startup_path, "w", encoding="utf-8") as f:
            f.write(command)
        return True
    except Exception as e:
        set_status(f"Could not enable startup: {e}", notify=True)
        return False


def disable_startup() -> bool:
    try:
        path = get_startup_bat_path()
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception as e:
        set_status(f"Could not disable startup: {e}", notify=True)
        return False


def sync_startup_setting_in_config():
    config.set("General", "start_with_windows", "true" if startup_enabled() else "false")
    save_config()


def is_process_running_by_name(name: str) -> bool:
    target = name.lower().strip()
    if not target:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            proc_name = proc.info["name"]
            if proc_name and proc_name.lower() == target:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


def is_minecraft_running() -> bool:
    return is_process_running_by_name(target_exe_name())


def is_discord_running() -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            proc_name = proc.info["name"]
            if proc_name and proc_name.lower() in DISCORD_PROCESS_NAMES:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


def open_discord(show_status=True):
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "discord://-/channels/@me"], shell=False)
        if show_status:
            set_status("Opening Discord...", notify=False)
        return True
    except Exception as e:
        if show_status:
            set_status(f"Could not open Discord: {e}", notify=True)
        return False


def ensure_discord_running(wait_seconds=6):
    if is_discord_running():
        return True
    opened = open_discord(show_status=False)
    if not opened:
        return False
    end_time = time.time() + max(1, wait_seconds)
    while time.time() < end_time:
        if is_discord_running():
            set_status("Discord was started for RPC.", notify=False)
            return True
        time.sleep(0.5)
    return is_discord_running()


def connect_rpc():
    global rpc
    if rpc is None:
        rpc = Presence(DISCORD_CLIENT_ID)
        rpc.connect()


def disconnect_rpc():
    global rpc
    if rpc is not None:
        try:
            rpc.close()
        except Exception:
            pass
        rpc = None


def build_presence_payload(details=None, state=None, large_text=None, start_timestamp=None):
    return {
        "details": details if details is not None else cfg_get("Presence", "details", DEFAULT_DETAILS),
        "state": state if state is not None else cfg_get("Presence", "state", DEFAULT_STATE),
        "start": start_timestamp if start_timestamp is not None else int(time.time()),
        "large_text": large_text if large_text is not None else cfg_get("Presence", "large_text", DEFAULT_LARGE_TEXT),
    }


def set_presence():
    global session_start
    if rpc is None:
        return
    if session_start is None:
        session_start = int(time.time())
    rpc.update(**build_presence_payload(start_timestamp=session_start))


def clear_presence():
    global session_start
    if rpc is not None:
        try:
            rpc.clear()
        except Exception:
            pass
    session_start = None


def update_tray_title():
    global tray_icon, last_status_text
    if tray_icon is not None:
        try:
            tooltip_name = cfg_get("Tray", "tray_tooltip_name", APP_NAME).strip() or APP_NAME
            tray_icon.title = f"{tooltip_name}\n{last_status_text}"
        except Exception:
            pass


def set_status(text: str, notify: bool = False):
    global last_status_text
    last_status_text = text
    log(text)
    update_tray_title()
    if notify and tray_icon is not None:
        try:
            tray_icon.notify(text, APP_NAME)
        except Exception:
            pass


def create_fallback_icon(size=64):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size - 8, size - 8), radius=12, fill=(34, 139, 34, 255))
    draw.rectangle((18, 18, 24, 46), fill=(255, 255, 255, 255))
    draw.rectangle((40, 18, 46, 46), fill=(255, 255, 255, 255))
    draw.rectangle((24, 18, 30, 28), fill=(255, 255, 255, 255))
    draw.rectangle((34, 18, 40, 28), fill=(255, 255, 255, 255))
    draw.rectangle((29, 24, 35, 34), fill=(255, 255, 255, 255))
    return image


def find_auto_icon_path() -> str:
    base_dir = app_dir()
    preferred_names = [
        f"{current_base_name()}.ico",
        f"{APP_SHORT_NAME}.ico",
        f"{APP_NAME}.ico",
        "app.ico",
        "icon.ico",
    ]
    for name in preferred_names:
        path = os.path.join(base_dir, name)
        if os.path.isfile(path):
            return path
    ico_files = []
    try:
        for name in os.listdir(base_dir):
            if name.lower().endswith(".ico"):
                full = os.path.join(base_dir, name)
                if os.path.isfile(full):
                    ico_files.append(full)
    except Exception:
        pass
    if ico_files:
        ico_files.sort(key=lambda p: os.path.basename(p).lower())
        return ico_files[0]
    return ""


def load_tray_icon_image():
    icon_path = find_auto_icon_path()
    if icon_path:
        try:
            return Image.open(icon_path)
        except Exception as e:
            set_status(f"Could not load .ico file, using fallback: {e}", notify=True)
    return create_fallback_icon()


def refresh_tray_icon_image():
    global tray_icon
    if tray_icon is not None:
        try:
            tray_icon.icon = load_tray_icon_image()
        except Exception as e:
            set_status(f"Could not refresh tray icon: {e}", notify=True)


def reconnect_rpc():
    global presence_active
    with lock:
        try:
            clear_presence()
        except Exception:
            pass
        disconnect_rpc()
        presence_active = False

        try:
            if monitoring_paused:
                set_status("Monitoring is paused. Discord RPC was not reconnected.", notify=True)
                return

            if not ensure_discord_running():
                set_status("Discord is not running, so RPC could not reconnect.", notify=True)
                return

            if is_minecraft_running():
                connect_rpc()
                set_presence()
                presence_active = True
                set_status("Discord RPC reconnected.", notify=True)
            else:
                set_status("Discord RPC is ready, but the game is not running.", notify=True)
        except Exception as e:
            set_status(f"Reconnect failed: {e}", notify=True)


def launch_game():
    global last_game_launch_time, auto_close_after_game_seen
    path = game_exe_path()
    args = game_launch_args()

    if not path:
        set_status("Game EXE path is not set.", notify=True)
        return False, "Game EXE path is not set."

    if not os.path.isfile(path):
        set_status("Configured game EXE path was not found.", notify=True)
        return False, f"The configured game EXE was not found:\n{path}"

    if is_minecraft_running():
        set_status("Minecraft PC Port is already running.", notify=True)
        return False, "Minecraft PC Port is already running."

    cooldown = launch_cooldown_seconds()
    now = time.time()
    if now - last_game_launch_time < cooldown:
        remaining = max(1, int(cooldown - (now - last_game_launch_time)))
        set_status(f"Please wait {remaining} more second(s) before launching again.", notify=True)
        return False, f"Please wait {remaining} more second(s) before launching again."

    try:
        command = [path]
        if args:
            command.extend(shlex.split(args, posix=False))
        subprocess.Popen(command, cwd=os.path.dirname(path) or None)
        auto_close_after_game_seen = True
        last_game_launch_time = now
        set_status(f"Launched game: {os.path.basename(path)}", notify=True)
        return True, "Game launched."
    except Exception as e:
        set_status(f"Could not launch game: {e}", notify=True)
        return False, str(e)


def run_test_presence(parent=None):
    def _worker():
        try:
            with lock:
                if not ensure_discord_running():
                    raise RuntimeError("Discord is not running.")
                connect_rpc()
                test_start = int(time.time())
                payload = build_presence_payload(start_timestamp=test_start)
                rpc.update(**payload)
            set_status("Test presence is live for 15 seconds.", notify=True)
            time.sleep(TEST_PRESENCE_SECONDS)
            with lock:
                if not is_minecraft_running():
                    try:
                        rpc.clear()
                    except Exception:
                        pass
                    disconnect_rpc()
            set_status("Test presence finished.", notify=False)
        except Exception as e:
            set_status(f"Test presence failed: {e}", notify=True)
            if parent is not None:
                try:
                    parent.after(0, lambda: messagebox.showerror(APP_NAME, f"Could not test presence:\n{e}", parent=parent))
                except Exception:
                    pass

    threading.Thread(target=_worker, daemon=True).start()




def request_exit(reason: str = ""):
    global tray_icon, shutdown_requested
    if shutdown_requested:
        return
    shutdown_requested = True
    if reason:
        set_status(reason, notify=False)
    stop_event.set()
    try:
        clear_presence()
    except Exception:
        pass
    disconnect_rpc()
    try:
        if settings_window is not None:
            settings_window.after(0, settings_window.destroy)
    except Exception:
        pass
    try:
        if about_window is not None:
            about_window.after(0, about_window.destroy)
    except Exception:
        pass
    try:
        if tray_icon is not None:
            tray_icon.visible = False
    except Exception:
        pass
    try:
        if tray_icon is not None:
            tray_icon.stop()
    except Exception:
        pass


def watcher_loop():
    global presence_active, minecraft_running_last, auto_close_after_game_seen
    set_status(f"Watching for {target_exe_name()}...", notify=False)

    while not stop_event.is_set():
        try:
            if monitoring_paused:
                if presence_active:
                    clear_presence()
                    disconnect_rpc()
                    presence_active = False
                minecraft_running_last = False
                set_status("Monitoring paused.", notify=False)
                stop_event.wait(check_interval_seconds())
                continue

            running = is_minecraft_running()

            if running and not presence_active:
                try:
                    if not ensure_discord_running():
                        raise RuntimeError("Discord is not running.")
                    connect_rpc()
                    set_presence()
                    presence_active = True
                    minecraft_running_last = True
                    auto_close_after_game_seen = True
                    set_status("Minecraft PC Port detected. Presence enabled.", notify=True)
                except Exception as e:
                    disconnect_rpc()
                    presence_active = False
                    set_status(f"Could not connect/update Discord RPC: {e}", notify=True)

            elif not running and presence_active:
                clear_presence()
                disconnect_rpc()
                presence_active = False
                minecraft_running_last = False
                if should_auto_close_after_game_closes() and auto_close_after_game_seen:
                    request_exit("Minecraft PC Port closed. Auto-closing Discord Presence...")
                    break
                set_status("Minecraft PC Port closed. Presence cleared.", notify=True)

            elif running and presence_active:
                try:
                    set_presence()
                    if not minecraft_running_last:
                        set_status("Minecraft PC Port is running. Presence active.", notify=False)
                    minecraft_running_last = True
                except Exception as e:
                    disconnect_rpc()
                    presence_active = False
                    set_status(f"Lost Discord RPC connection: {e}", notify=True)

            else:
                minecraft_running_last = False
                set_status(f"Waiting for {target_exe_name()}...", notify=False)

            stop_event.wait(check_interval_seconds())

        except Exception as e:
            set_status(f"Watcher error: {e}", notify=True)
            stop_event.wait(check_interval_seconds())


def on_show_status(icon, _item):
    running = is_minecraft_running()
    icon_path = find_auto_icon_path()
    game_path = game_exe_path()
    state = []
    state.append(f"Target EXE: {target_exe_name()}")
    state.append(f"Game Path: {os.path.basename(game_path) if game_path else 'Not set'}")
    state.append("Minecraft PC Port: Running" if running else "Minecraft PC Port: Not running")
    state.append("Monitoring: Paused" if monitoring_paused else "Monitoring: Active")
    state.append("Discord RPC: Active" if presence_active else "Discord RPC: Inactive")
    state.append(f"Discord: {'Running' if is_discord_running() else 'Not running'}")
    state.append(f"Startup: {'Enabled' if startup_enabled() else 'Disabled'}")
    state.append(f"Tray Icon: {os.path.basename(icon_path) if icon_path else 'Built-in fallback'}")
    try:
        icon.notify("\n".join(state), f"{APP_NAME} Status")
    except Exception:
        pass


def on_toggle_pause(icon, _item):
    global monitoring_paused
    monitoring_paused = not monitoring_paused
    set_status("Monitoring paused by user." if monitoring_paused else "Monitoring resumed by user.", notify=True)


def on_reconnect(icon, _item):
    reconnect_rpc()


def on_open_discord(icon, _item):
    open_discord(show_status=True)


def on_launch_game(icon, _item):
    launch_game()


def apply_settings_from_window(window):
    global monitoring_paused
    try:
        target_exe = settings_vars["target_exe"].get().strip() or DEFAULT_TARGET_EXE
        check_interval_raw = settings_vars["check_interval"].get().strip()
        cooldown_raw = settings_vars["launch_cooldown_seconds"].get().strip()
        details = settings_vars["details"].get().strip() or DEFAULT_DETAILS
        state = settings_vars["state"].get().strip() or DEFAULT_STATE
        large_text = settings_vars["large_text"].get().strip() or DEFAULT_LARGE_TEXT
        tray_tooltip_name = settings_vars["tray_tooltip_name"].get().strip() or APP_NAME
        game_path = settings_vars["game_exe_path"].get().strip()
        game_args = settings_vars["game_launch_args"].get().strip()

        try:
            check_interval = max(1, int(check_interval_raw))
        except Exception:
            messagebox.showerror(APP_NAME, "Check interval must be a number of 1 or higher.", parent=window)
            return False

        try:
            cooldown = max(1, int(cooldown_raw))
        except Exception:
            messagebox.showerror(APP_NAME, "Launch cooldown must be a number of 1 or higher.", parent=window)
            return False

        if game_path and not os.path.isfile(game_path):
            if not messagebox.askyesno(
                APP_NAME,
                "The selected game EXE path does not exist right now.\n\nSave it anyway?",
                parent=window,
            ):
                return False

        config.set("General", "target_exe", target_exe)
        config.set("General", "check_interval", str(check_interval))
        config.set("General", "start_paused", "true" if settings_vars["start_paused"].get() else "false")
        config.set("General", "open_discord_on_start", "true" if settings_vars["open_discord_on_start"].get() else "false")
        config.set("General", "auto_close_after_game_closes", "true" if settings_vars["auto_close_after_game_closes"].get() else "false")
        config.set("General", "game_exe_path", game_path)
        config.set("General", "game_launch_args", game_args)
        config.set("General", "launch_cooldown_seconds", str(cooldown))

        config.set("Presence", "details", details)
        config.set("Presence", "state", state)
        config.set("Presence", "large_text", large_text)
        if config.has_option("Presence", "large_image"):
            config.remove_option("Presence", "large_image")

        config.set("Tray", "tray_tooltip_name", tray_tooltip_name)
        if config.has_option("Tray", "icon_path"):
            config.remove_option("Tray", "icon_path")

        want_startup = bool(settings_vars["start_with_windows"].get())
        if want_startup != startup_enabled():
            if want_startup:
                if not enable_startup():
                    return False
            else:
                if not disable_startup():
                    return False

        save_config()
        sync_startup_setting_in_config()

        if not presence_active:
            monitoring_paused = cfg_get_bool("General", "start_paused", False)

        refresh_tray_icon_image()
        update_tray_title()

        if presence_active:
            reconnect_rpc()
        else:
            set_status("Settings saved and applied.", notify=True)
        return True
    except Exception as e:
        messagebox.showerror(APP_NAME, f"Could not apply settings:\n{e}", parent=window)
        return False


def open_settings_window():
    global settings_window
    with settings_lock:
        if settings_window is not None:
            try:
                settings_window.deiconify()
                settings_window.lift()
                settings_window.focus_force()
                return
            except Exception:
                settings_window = None

    def _browse_game_exe():
        filename = filedialog.askopenfilename(
            title="Select Minecraft Legacy PC Port EXE",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")],
        )
        if filename:
            settings_vars["game_exe_path"].set(filename)
            settings_vars["target_exe"].set(os.path.basename(filename))

    def _run_window():
        global settings_window, settings_vars
        root = tk.Tk()
        root.title(f"{APP_NAME} Settings")
        root.geometry("660x500")
        root.minsize(660, 500)
        settings_window = root

        settings_vars = {
            "target_exe": tk.StringVar(value=cfg_get("General", "target_exe", DEFAULT_TARGET_EXE)),
            "check_interval": tk.StringVar(value=str(cfg_get_int("General", "check_interval", DEFAULT_CHECK_INTERVAL))),
            "launch_cooldown_seconds": tk.StringVar(value=str(cfg_get_int("General", "launch_cooldown_seconds", DEFAULT_LAUNCH_COOLDOWN))),
            "start_paused": tk.BooleanVar(value=cfg_get_bool("General", "start_paused", False)),
            "start_with_windows": tk.BooleanVar(value=startup_enabled()),
            "open_discord_on_start": tk.BooleanVar(value=cfg_get_bool("General", "open_discord_on_start", False)),
            "auto_close_after_game_closes": tk.BooleanVar(value=cfg_get_bool("General", "auto_close_after_game_closes", True)),
            "game_exe_path": tk.StringVar(value=cfg_get("General", "game_exe_path", DEFAULT_GAME_EXE_PATH)),
            "game_launch_args": tk.StringVar(value=cfg_get("General", "game_launch_args", DEFAULT_GAME_LAUNCH_ARGS)),
            "details": tk.StringVar(value=cfg_get("Presence", "details", DEFAULT_DETAILS)),
            "state": tk.StringVar(value=cfg_get("Presence", "state", DEFAULT_STATE)),
            "large_text": tk.StringVar(value=cfg_get("Presence", "large_text", DEFAULT_LARGE_TEXT)),
            "tray_tooltip_name": tk.StringVar(value=cfg_get("Tray", "tray_tooltip_name", APP_NAME)),
        }

        def on_close():
            global settings_window
            settings_window = None
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        notebook = ttk.Notebook(main)
        notebook.pack(fill="both", expand=True)

        tab_general = ttk.Frame(notebook, padding=12)
        tab_presence = ttk.Frame(notebook, padding=12)
        tab_tray = ttk.Frame(notebook, padding=12)

        notebook.add(tab_general, text="General")
        notebook.add(tab_presence, text="Presence")
        notebook.add(tab_tray, text="Tray")

        for col in range(3):
            tab_general.columnconfigure(col, weight=1)
            tab_presence.columnconfigure(col, weight=1)
            tab_tray.columnconfigure(col, weight=1)

        ttk.Label(tab_general, text="Game EXE path:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_general, textvariable=settings_vars["game_exe_path"]).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Button(tab_general, text="Browse...", command=_browse_game_exe).grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=(0, 12))

        ttk.Label(tab_general, text="Launch arguments (optional):").grid(row=2, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_general, textvariable=settings_vars["game_launch_args"]).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(tab_general, text="Target EXE name:").grid(row=4, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_general, textvariable=settings_vars["target_exe"]).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(tab_general, text="Check interval (seconds):").grid(row=6, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_general, textvariable=settings_vars["check_interval"]).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(tab_general, text="Launch cooldown (seconds):").grid(row=8, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_general, textvariable=settings_vars["launch_cooldown_seconds"]).grid(row=9, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Checkbutton(tab_general, text="Start paused", variable=settings_vars["start_paused"]).grid(row=10, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Checkbutton(tab_general, text="Start with Windows", variable=settings_vars["start_with_windows"]).grid(row=11, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Checkbutton(tab_general, text="Open Discord on start", variable=settings_vars["open_discord_on_start"]).grid(row=12, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Checkbutton(tab_general, text="Auto-close after game closes", variable=settings_vars["auto_close_after_game_closes"]).grid(row=13, column=0, columnspan=3, sticky="w", pady=(0, 8))

        def launch_from_settings():
            if apply_settings_from_window(root):
                launch_game()

        ttk.Button(tab_general, text="Launch Game Now", command=launch_from_settings).grid(row=14, column=0, sticky="w", pady=(12, 0))

        ttk.Label(tab_presence, text="Details text:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_presence, textvariable=settings_vars["details"]).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(tab_presence, text="State text:").grid(row=2, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_presence, textvariable=settings_vars["state"]).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(tab_presence, text="Large text:").grid(row=4, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_presence, textvariable=settings_vars["large_text"]).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        ttk.Label(tab_presence, text="The Discord app icon is used automatically.", wraplength=560).grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Label(tab_presence, text="Use Test Presence to preview your text for 15 seconds without launching the game.", wraplength=560).grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 8))
        ttk.Button(tab_presence, text="Test Presence", command=lambda: run_test_presence(root)).grid(row=8, column=0, sticky="w")

        ttk.Label(tab_tray, text="Tray tooltip/app name:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab_tray, textvariable=settings_vars["tray_tooltip_name"]).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        detected_icon = find_auto_icon_path()
        detected_text = os.path.basename(detected_icon) if detected_icon else "No .ico file found - built-in icon will be used"
        ttk.Label(tab_tray, text="Tray icon is automatic.").grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 8))
        ttk.Label(tab_tray, text=f"Detected icon: {detected_text}", wraplength=560).grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Label(tab_tray, text="Put any .ico file beside the EXE/script and it will be used automatically.", wraplength=560).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        button_row = ttk.Frame(main)
        button_row.pack(fill="x", pady=(10, 0))

        def save_only():
            if apply_settings_from_window(root):
                messagebox.showinfo(APP_NAME, "Settings saved.", parent=root)

        def save_and_close():
            if apply_settings_from_window(root):
                on_close()

        ttk.Button(button_row, text="Save", command=save_only).pack(side="right")
        ttk.Button(button_row, text="Save and Close", command=save_and_close).pack(side="right", padx=(0, 8))
        ttk.Button(button_row, text="Cancel", command=on_close).pack(side="right", padx=(0, 8))

        root.mainloop()

    threading.Thread(target=_run_window, daemon=True).start()


def open_about_window():
    global about_window
    with about_lock:
        if about_window is not None:
            try:
                about_window.deiconify()
                about_window.lift()
                about_window.focus_force()
                return
            except Exception:
                about_window = None

    def _run_about():
        global about_window
        root = tk.Tk()
        root.title(f"About {APP_NAME}")
        root.geometry("560x380")
        root.minsize(560, 380)
        about_window = root

        def on_close():
            global about_window
            about_window = None
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)

        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"Version {APP_VERSION}").pack(anchor="w", pady=(2, 12))

        about_text = (
            "A small tray utility that watches for Minecraft Legacy PC Port and "
            "shows Discord Rich Presence while the game is running.\n\n"
            "Main features:\n"
            "- Watches for the configured Minecraft EXE\n"
            "- Updates Discord Rich Presence automatically\n"
            "- Can launch the game from the tray or settings window\n"
            "- Starts Discord automatically before reconnecting RPC when needed\n"
            "- Can auto-close itself after the game closes\n"
            "- Supports auto-start, auto icon detection, configurable text, and test presence\n"
        )
        ttk.Label(frame, text=about_text, justify="left", wraplength=520).pack(anchor="w")

        info = (
            f"Author: {APP_AUTHOR}\n"
            f"License: {APP_LICENSE}\n"
            f"GitHub: {APP_GITHUB_URL}\n"
            f"Discord App ID: {DISCORD_CLIENT_ID}\n"
            f"Config File: {get_config_path()}\n"
            f"Detected Target EXE: {target_exe_name()}"
        )
        ttk.Label(frame, text=info, justify="left", wraplength=520).pack(anchor="w", pady=(12, 0))

        def open_github():
            try:
                webbrowser.open(APP_GITHUB_URL)
            except Exception as e:
                messagebox.showerror(APP_NAME, f"Could not open GitHub:\n{e}", parent=root)

        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", side="bottom", pady=(16, 0))
        ttk.Button(button_row, text="Close", command=on_close).pack(side="right")
        ttk.Button(button_row, text="Open Settings", command=lambda: (open_settings_window(), on_close())).pack(side="right", padx=(0, 8))
        ttk.Button(button_row, text="GitHub Page", command=open_github).pack(side="left")

        root.mainloop()

    threading.Thread(target=_run_about, daemon=True).start()


def on_open_settings(icon, _item):
    open_settings_window()


def on_open_about(icon, _item):
    open_about_window()


def on_exit(icon, _item):
    global presence_active
    presence_active = False
    request_exit("Exiting...")


def is_paused_checked(_item):
    return monitoring_paused


def build_menu():
    return pystray.Menu(
        item("Show Status", on_show_status),
        item("Launch Game", on_launch_game),
        item("Settings", on_open_settings),
        item("About", on_open_about),
        pystray.Menu.SEPARATOR,
        item("Pause Monitoring", on_toggle_pause, checked=is_paused_checked),
        item("Reconnect Discord RPC", on_reconnect),
        item("Open Discord", on_open_discord),
        pystray.Menu.SEPARATOR,
        item("Exit", on_exit),
    )


def initialize_runtime_settings():
    global monitoring_paused, auto_close_after_game_seen
    load_config()
    sync_startup_setting_in_config()
    monitoring_paused = should_start_paused()
    auto_close_after_game_seen = False
    if should_open_discord_on_start():
        try:
            open_discord(show_status=False)
        except Exception:
            pass


def main():
    global tray_icon
    initialize_runtime_settings()

    watcher_thread = threading.Thread(target=watcher_loop, daemon=True)
    watcher_thread.start()

    tray_icon = pystray.Icon(
        APP_SHORT_NAME,
        load_tray_icon_image(),
        cfg_get("Tray", "tray_tooltip_name", APP_NAME).strip() or APP_NAME,
        build_menu(),
    )
    update_tray_title()
    tray_icon.run()


if __name__ == "__main__":
    main()
