# MCLCE Discord Presence

A small Windows tray utility that shows **Minecraft Legacy Console Edition PC Port** activity on **Discord Rich Presence**.

This tool watches for `Minecraft.Client.exe`, updates Discord while the game is running, and stays out of the way in the system tray.

It was originally made as a personal utility, but it can also be useful for anyone who wants Discord to show that they are playing the **PC Port of Minecraft Legacy Console Edition**.

---

## What it does

- Watches for `Minecraft.Client.exe`
- Automatically connects to Discord Rich Presence
- Shows a custom status while the game is running
- Clears the status when the game closes
- Runs as a lightweight tray app

---

## Features

### Core features
- Detects whether `Minecraft.Client.exe` is running
- Updates Discord Rich Presence automatically
- Clears Rich Presence when the game closes
- Reconnects to Discord RPC if needed
- Can launch Discord automatically before reconnecting RPC

### Tray utility features
- Runs in the Windows system tray / overflow tray area
- Tray menu includes quick actions such as:
  - Show Status
  - Launch Game
  - Settings
  - About
  - Pause / Resume Monitoring
  - Reconnect Discord RPC
  - Open Discord
  - Exit
- Automatically uses a local `.ico` file for the tray icon if one is found beside the EXE/script

### Settings window
- Basic GUI settings window for easier configuration
- Lets users change:
  - Target EXE name
  - Check interval
  - Presence details text
  - Presence state text
  - Large text / hover text
  - Game EXE path
  - Game launch arguments
  - Startup behavior
- Includes a **Test Presence** button so users can preview the Discord status without launching the game

### Game launching features
- Lets users choose the full path to the game EXE
- Can launch the game directly from the tray app
- Prevents multiple launches if the game is already running
- Includes a launch cooldown to avoid accidental duplicate starts

### Public release features
- About window with program info
- GitHub link in the About window
- MIT license friendly release setup
- INI-based config for easy editing and portability

---

## Requirements

### For users
- Windows
- Discord desktop app installed and running
- A Discord application / app ID set in the program build or source
- The Minecraft Legacy Console Edition PC Port executable, usually detected as:

```text
Minecraft.Client.exe
```

### For Python/source users
- Python 3
- Required packages:

```bash
pip install psutil pypresence pystray pillow
```

---

## How it works

The program checks whether `Minecraft.Client.exe` is running.

If the game is found:
- it connects to Discord Rich Presence
- it sets the configured presence text
- it keeps the presence alive while the game stays open

If the game is not running:
- it clears the Rich Presence
- it waits for the game to start again

---

## Configuration

The program uses an `.ini` config file.

Typical options include:
- target EXE name
- check interval
- presence text
- game EXE path
- launch arguments
- launch cooldown
- startup behavior

This makes it easy to adjust the tool without editing code.

---

## Tray icon behavior

The program will try to find a local `.ico` file automatically.

It first checks for common names such as:
- `MCLCEDisPres.ico`
- `app.ico`
- `icon.ico`
- the EXE/script name with `.ico`

If none are found, it can fall back to a built-in generated icon.

---

## Building the EXE

If you want to build it yourself with PyInstaller:

```bash
pyinstaller --onefile --noconsole MCLCEDisPres.py
```

This creates a background-style EXE that runs in the tray instead of opening a console window.

---

## Basic usage

1. Start the program
2. Open **Settings** and configure the game EXE path if needed
3. Make sure Discord is installed and running
4. Launch the game normally, or use **Launch Game** from the tray menu
5. Discord should show your Rich Presence while the game is running

You can also use **Test Presence** from the Settings window to preview the configured text.

---

## Notes

- This tool is **not affiliated with Mojang, Microsoft, or Discord**
- This project is meant as a fan-made utility
- Rich Presence requires the Discord desktop app
- The program is intended for personal use, but can also be shared publicly under this repository’s license

---

## License

This project is licensed under the **MIT License**.

See the repository license file for full details.

---

## GitHub

Repository:

`https://github.com/sonicFanTech/MCLCEDisPress/tree/main`

---

## Credits

Created by **sonic Fan Tech**.

Special thanks to the Minecraft Legacy Console Edition PC Port community and anyone who wants a simple way to show the game on Discord.
