# River Watch AIS Bridge - Windows User Guide

A tiny console app that forwards AIS / NMEA data from **Boat Beacon** on your
local Wi-Fi to the **River Watch** GCP collector so your vessel shows up on
the dashboard map.

You do **not** need Python, Git, or PowerShell. Download the bundle, edit one
`.ini` file (optional), double-click `RiverWatchAISBridge.exe`, done.

---

## 1. What's in the bundle

After downloading and unzipping `RiverWatchAISBridge.zip` you will see a
folder like:

```
RiverWatchAISBridge\
├── RiverWatchAISBridge.exe          ← the bridge itself
├── riverwatch_bridge.example.ini    ← template config
├── README.md                        ← this file
├── _internal\                       ← Python runtime + libraries (don't touch)
```

On first launch the bridge will copy `riverwatch_bridge.example.ini` next to
the .exe as `riverwatch_bridge.ini` if it isn't there yet. Edit that copy if
you need to change anything.

---

## 2. Run the bridge (foreground / console mode)

1. Make sure your PC is on the **same Wi-Fi or Ethernet network** as the
   device running Boat Beacon.
2. In Boat Beacon, enable the **TCP / NMEA output**:
   - Boat Beacon → *Settings* → *NMEA Output* → switch **TCP** on
   - Note the **port** Boat Beacon shows (5353 / 7000 / 10110 are common).
3. Double-click `RiverWatchAISBridge.exe`.

A console window opens. After a few seconds you should see something like:

```
2026-05-13 09:01:02 INFO  ============================================================
2026-05-13 09:01:02 INFO  River Watch AIS Bridge starting
2026-05-13 09:01:02 INFO  Collector: 34.172.47.153:6000
2026-05-13 09:01:02 INFO  Cache file: C:\Users\you\.riverwatch_ais_relay.json
2026-05-13 09:01:02 INFO  Boat Beacon: auto-discover
2026-05-13 09:01:02 INFO  ============================================================
2026-05-13 09:01:02 INFO  Local interfaces visible:
2026-05-13 09:01:02 INFO    eth0       192.168.0.0/24       AUTO-SCAN
2026-05-13 09:01:02 INFO  Scanning 250 targets across 1 subnet(s) on ports (5353, 7000, ...)
2026-05-13 09:01:05 INFO    found 192.168.0.25:5353 ais_detected (score=85)
2026-05-13 09:01:05 INFO  Selected Boat Beacon: 192.168.0.25:5353
2026-05-13 09:01:05 INFO  Cached Boat Beacon feed to C:\Users\you\.riverwatch_ais_relay.json
2026-05-13 09:01:05 INFO  Connecting to Boat Beacon at 192.168.0.25:5353...
2026-05-13 09:01:05 INFO  Connected to Boat Beacon!
2026-05-13 09:01:05 INFO  Connecting to Collector at 34.172.47.153:6000...
2026-05-13 09:01:05 INFO  Connected to Collector!
2026-05-13 09:01:05 INFO  Relay active - forwarding NMEA data...
2026-05-13 09:01:15 INFO  STATUS lines=42 bytes=3127 errors=0 last_data=09:01:14
```

The `STATUS` line refreshes every 10 seconds. Keep that window open while
you're on the river. Press **Ctrl + C** to stop.

---

## 3. Config file (`riverwatch_bridge.ini`)

The bridge looks for `riverwatch_bridge.ini` in the **same folder as the
.exe**. Everything in it is optional - if you delete it you get sensible
defaults. The template is reproduced below; edit it with Notepad.

```ini
[collector]
ip   = 34.172.47.153
port = 6000
token =

[boat_beacon]
ip   =          ; leave blank for auto-discovery
port =
subnet =        ; e.g. 192.168.0.0/24 to force a subnet
cache_path =    ; blank = %USERPROFILE%\.riverwatch_ais_relay.json

[logging]
level                   = INFO     ; DEBUG, INFO, WARNING, ERROR
status_interval_seconds = 10
log_dir                 =          ; blank = console only
```

After editing, **close and reopen** the bridge so it picks up the change.

---

## 4. Useful command-line flags

You normally don't need these, but they help while troubleshooting:

| Command                                           | What it does                                              |
| ------------------------------------------------- | --------------------------------------------------------- |
| `RiverWatchAISBridge.exe`                         | Default - discover and relay                              |
| `RiverWatchAISBridge.exe --status`                | One-shot health check: cache state + can we reach :6000?  |
| `RiverWatchAISBridge.exe --clear-cache`           | Forget the cached Boat Beacon feed; re-scan next launch   |
| `RiverWatchAISBridge.exe --config "C:\path\to\my.ini"` | Use a config file from somewhere else                 |
| `RiverWatchAISBridge.exe install-service`         | Install as a Windows service (requires NSSM, see §6)      |
| `RiverWatchAISBridge.exe start-service`           | Start the installed service                               |
| `RiverWatchAISBridge.exe stop-service`            | Stop the installed service                                |
| `RiverWatchAISBridge.exe uninstall-service`       | Remove the service                                        |

Open a Command Prompt, `cd` to the folder containing the .exe, and run the
command. Example:

```bat
cd %USERPROFILE%\Downloads\RiverWatchAISBridge
RiverWatchAISBridge.exe --status
```

---

## 5. How to verify it is working

There are three places to confirm the data is reaching the dashboard:

1. **Bridge console** - the `STATUS lines=X bytes=Y` counter must keep
   increasing every 10 seconds.
2. **GCP relay health endpoint** - in a browser:
   `http://34.172.47.153:8088/health`. Look for `"mode": "push"` and a
   `lines_received` counter that grows.
3. **River Watch dashboard** - your vessel and other live MMSIs appear on
   the map within ~30 seconds.

If all three show data, the bridge is doing its job.

---

## 6. Run as a Windows service (optional, recommended for set-and-forget use)

The bridge .exe is a normal console program. To run it as a background
Windows service (auto-start at boot, no console window) we use **NSSM**,
the de-facto Windows service wrapper.

### 6.1 One-time setup

1. Download NSSM from <https://nssm.cc/download> (grab the latest stable zip).
2. Extract it. Inside `win64\` (or `win32\` on 32-bit PCs) you'll find
   `nssm.exe`.
3. Copy that `nssm.exe` into the **same folder as `RiverWatchAISBridge.exe`**
   (or add NSSM to your `PATH`).

### 6.2 Install + start the service

Open an **Administrator** Command Prompt and:

```bat
cd %USERPROFILE%\Downloads\RiverWatchAISBridge
RiverWatchAISBridge.exe install-service
RiverWatchAISBridge.exe start-service
```

The service is named `RiverWatchAISBridge`. It starts automatically on boot.
You can manage it from `services.msc` too.

### 6.3 Stop / remove

```bat
RiverWatchAISBridge.exe stop-service
RiverWatchAISBridge.exe uninstall-service
```

### 6.4 Don't want NSSM? Use Task Scheduler instead

If you prefer the built-in Task Scheduler:

1. Start menu → **Task Scheduler**.
2. **Create Basic Task...** → name it *River Watch AIS Bridge*.
3. Trigger: **When the computer starts**.
4. Action: **Start a program** → browse to `RiverWatchAISBridge.exe`.
5. Tick **Run with highest privileges**, **Run whether user is logged on or
   not**.
6. Save. The bridge will launch automatically at every boot.

---

## 7. Troubleshooting

### "No Boat Beacon AIS feed found"

| Possible cause                                                  | Fix                                                                                                          |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| PC is on a different Wi-Fi from Boat Beacon                     | Connect to the same SSID, or plug into the same router by Ethernet.                                          |
| Boat Beacon TCP output disabled                                 | In Boat Beacon → *Settings* → *NMEA Output*, enable **TCP**. Note the port (5353 / 7000 / 10110 are common). |
| Windows Firewall is blocking the LAN scan                       | Allow `RiverWatchAISBridge.exe` on **Private networks** when Windows prompts.                                |
| Your LAN uses a non-standard subnet (e.g. 10.x.x.x)             | Edit `riverwatch_bridge.ini`, set `subnet = 10.0.0.0/24` (or whatever your router uses).                     |
| You know the Boat Beacon IP/port already                        | Put them in `[boat_beacon]` `ip = ...` and `port = ...` to skip the scan entirely.                           |

### "Cannot connect to Collector"

| Possible cause                                                  | Fix                                                                                                          |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Your network blocks outbound TCP on port 6000                   | Try a different network (phone hotspot is a good test). Ask IT to allow outbound TCP/6000.                   |
| Collector IP/port has changed                                   | Update `[collector]` `ip = ...` / `port = ...` in the INI.                                                   |
| Collector is temporarily offline                                | Wait a minute - the bridge retries every 5 seconds automatically.                                            |

### "STATUS lines stuck at 0"

- The bridge connected to **something**, but it isn't AIS/NMEA. Run
  `RiverWatchAISBridge.exe --clear-cache` then relaunch so the auto-scan
  picks a different port.
- If you set `[boat_beacon] ip/port` manually, double-check those values
  against Boat Beacon's *NMEA Output* screen.

### Need verbose logs

Edit `riverwatch_bridge.ini`:

```ini
[logging]
level = DEBUG
log_dir = C:\Users\you\RiverWatchLogs
```

Then restart. A log file `RiverWatchAISBridge-YYYYMMDD.log` is written to
that folder.

### Reset everything

```bat
RiverWatchAISBridge.exe stop-service
RiverWatchAISBridge.exe --clear-cache
del riverwatch_bridge.ini
RiverWatchAISBridge.exe
```

The bridge will recreate the INI from the template and scan from scratch.

---

## 8. For developers / builders

To rebuild the .exe from source:

1. Clone the repo on a Windows 10/11 machine.
2. Install Python 3.10+ (tick *Add Python to PATH*).
3. From an Admin PowerShell:

   ```ps
   cd scripts\windows_bridge
   py -3 -m venv .venv
   .venv\Scripts\activate
   pip install --upgrade pip pyinstaller
   .\build_windows.bat
   ```

4. The output is in `scripts\windows_bridge\dist\RiverWatchAISBridge\`.
   Zip that folder and ship it.

The build is driven by `riverwatch_ais_bridge.spec`. It bundles the verified
`scripts/ais_relay.py` sender as a hidden import, so the .exe always uses
the same proven discovery + push logic the CLI sender uses.
