# Privacy

Verdra keeps everything on your computer.

## What Verdra sends

- **No telemetry, no analytics, no crash reporting** to any server.
- **Roblox:** only the requests your own Roblox client makes, plus asset lookups you trigger.
- **GitHub** (github.com and raw.githubusercontent.com): the update check, the preset catalog
  and the FastFlag reference list.
- **Sites you name:** any URL you enter for a replacement, and the sites a preset you add lists.

## What Verdra stores locally

- Settings, replacement profiles, presets, file tweaks and the list of system changes.
- Captured assets in the library.
- Logs, with secrets redacted.
- Account login tokens and Verdra's certificate key, only in your system's secure storage
  (Windows Credential Manager, macOS Keychain, or the Secret Service on Linux).

## Folders

| Kind | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Settings, profiles, presets, system changes | `%LOCALAPPDATA%\Verdra\` | `~/Library/Application Support/Verdra/` | `~/.config/verdra/` |
| Library | `%LOCALAPPDATA%\Verdra\Library\` | `~/Library/Caches/Verdra/Library/` | `~/.cache/verdra/library/` |
| Logs | `%LOCALAPPDATA%\Verdra\Logs\` | `~/Library/Logs/Verdra/` | `~/.local/state/verdra/logs/` |
| Exports (only what you export) | `Documents\Verdra\` | `~/Documents/Verdra/` | `~/Documents/Verdra/` |

If you move the library in Settings › Library, it lives where you chose instead.

## Removing everything

Settings › System changes › "Reset everything…" undoes every change Verdra made outside its own
folders. Uninstalling Verdra afterwards removes the app; the uninstaller asks whether to delete
the folders above too.

## Contact

Questions about privacy: [verdra.support@atomicmail.io](mailto:verdra.support@atomicmail.io).
