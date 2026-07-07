---
name: loom-adb-forward-proxy-bypass
description: "Use when APKClaw/LOOM phone control is unreachable over Wi-Fi/LAN because the phone is running VPN/proxy/firewall, but USB ADB is authorized. Sets up an ADB local forward and points LOOM at 127.0.0.1 without changing phone token/signature secrets."
---

# LOOM ADB Forward Proxy Bypass

This skill repairs a specific connection failure:

```text
LOOM computer -> phone LAN IP:9527 fails
ADB devices -> authorized device is available
phone may be running VPN/proxy such as Nano, Clash, v2ray, or an always-on VPN
```

The fix is to create a USB tunnel:

```text
LOOM computer -> 127.0.0.1:18790 -> USB ADB forward -> phone localhost:9527 -> APKClaw
```

This is not a special APKClaw Agent command. `adb forward` is created by the Android Debug Bridge. After the forward exists, normal LOOM phone Agent HTTP requests travel through the forwarded local port.

## When To Use

Use this when all are true:

- APKClaw is running on the phone.
- LOOM cannot reach `http://PHONE_IP:9527`.
- `adb devices` shows one authorized phone, or the user can provide a serial.
- The phone may be using VPN/proxy/firewall rules that block LAN inbound traffic.

Do not use this for:

- model not configured
- invalid APKClaw token
- invalid Lumi signature
- APKClaw crash
- missing USB debugging authorization

## One-Command Repair

From this skill folder:

```powershell
.\loom-adb-forward-setup.ps1
```

Useful options:

```powershell
.\loom-adb-forward-setup.ps1 -BasePath D:\LOOM
.\loom-adb-forward-setup.ps1 -DeviceSerial ABC123 -LocalPort 18791
.\loom-adb-forward-setup.ps1 -ConfigPath D:\LOOM\LOOMFiles\data\.openclaw\launcher\phone-agents.json
.\loom-adb-forward-setup.ps1 -DryRun
```

## Expected Result

- ADB forward exists: `tcp:18790 -> tcp:9527`.
- LOOM phone config `baseUrl` becomes `http://127.0.0.1:18790`.
- Existing token, album, `lumiLauncherId`, and `lumiLauncherSecret` stay unchanged.
- A `.bak.<timestamp>` config backup is written before the change.

## Multiple Phones

Each phone needs its own local port:

```powershell
.\loom-adb-forward-setup.ps1 -DeviceSerial PHONE_A -LocalPort 18790
.\loom-adb-forward-setup.ps1 -DeviceSerial PHONE_B -LocalPort 18791
```

If the LOOM config has multiple devices, pass `-LoomDeviceId` or run the script once and choose the correct device when prompted by the UI. The script will not silently rewrite the first device when multiple entries exist.

## Rollback

Remove the tunnel:

```powershell
adb forward --remove tcp:18790
```

Restore the config backup:

```powershell
Copy-Item phone-agents.json.bak.YYYYMMDD-HHMMSS phone-agents.json -Force
```

## Notes

- Replugging USB or restarting ADB can remove the forward; rerun the script.
- ADB forward bypasses phone-side VPN/proxy because traffic goes over USB.
- Accessibility repair is not guaranteed on every Android ROM; the script only starts APKClaw and reports clear next steps.
- Use `loom-command-brain` after this repair for normal LOOM phone tasks.
