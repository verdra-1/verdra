# Verdra

Change how your game looks, only on your screen.

Verdra lets you change how Roblox looks on your own computer (textures, meshes, sounds,
animations and client settings) safely, reversibly and transparently. It runs a small local
proxy: when Roblox downloads an asset, Verdra can hand it a different one. Nothing changes on
Roblox's servers or for other players, and every change Verdra makes to your computer is listed
and can be undone with one action.

Works with the Roblox Player on Windows. Windows is the only supported system: Linux is paused
and macOS is deferred, both planned later.

> **Early development.** Verdra is in early development (milestone M0). There are no releases yet
> (the first public release will be 1.0), and it isn't usable yet: it has its window, settings and
> activity log, but no routing or replacements. Verdra is an independent project and is not
> affiliated with or endorsed by Roblox Corporation. Roblox is a trademark of Roblox Corporation.

## What Verdra does

- **Replacements.** Swap any asset for another asset ID, a local file or an HTTPS link, or remove
  it. Group replacements into profiles you can turn on and off.
- **Library.** Assets Roblox loads while it runs through Verdra are captured locally, so you can
  preview them, find their IDs and export them.
- **Tweaks.** File tweaks, the FastFlags Roblox permits locally, and a frame-rate cap.
- **Presets and packs.** Start from signed presets, or share your own profiles as a pack.
- **Nothing hidden, nothing permanent.** Settings › System changes lists everything Verdra changed
  outside its own folders, and "Reset everything" removes all of it.

Every feature carries a risk badge: Cosmetic, Client behavior, Account-sensitive or Moderation
risk. Features with a Moderation-risk badge are off by default and sit behind a warning.

## What Verdra never does

- Give a gameplay advantage over other players, or automate gameplay.
- Read or modify game memory, inject code into Roblox, or hide itself from Roblox.
- Change anything other players see.
- Collect telemetry, or send data anywhere except Roblox, GitHub (update check and presets) and
  the sites your profiles name. See [PRIVACY.md](PRIVACY.md).

## Use at your own risk

Roblox's terms may treat client modifications as against its rules. Features with a
Moderation-risk badge carry that risk: Roblox could take action on the accounts you use with them.
Verdra explains each risk before you turn such a feature on, and you can withdraw your acceptance
at any time in Settings › Privacy & safety.

## Building from source

Verdra needs Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run verdra
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the checks every pull request must pass.

## Support

Questions and support: [verdra.support@atomicmail.io](mailto:verdra.support@atomicmail.io).
Bugs and feature ideas are welcome as GitHub issues.

## Security

Report vulnerabilities privately through GitHub, as described in [SECURITY.md](SECURITY.md).
Don't send them by email.

## Credits

Verdra was inspired by Fleasion, which pioneered local asset replacement for Roblox.

The FastFlag reference list is fetched at runtime from a public tracker and never bundled. The
tracker is credited here by name once the FastFlags feature chooses it (plan 3.4).

## Not affiliated

Verdra is an independent project and is not affiliated with or endorsed by Roblox Corporation.
Roblox is a trademark of Roblox Corporation.

## License

Verdra is licensed under the [Apache License 2.0](LICENSE). The name "Verdra" and the logo are
not licensed for use beyond describing where a fork came from (section 6 of the license).

```
Verdra
Copyright 2026 q0f7

Original project: https://github.com/verdra-1/verdra
Licensed under the Apache License, Version 2.0.
If you received a modified version of Verdra, the original is available at the address above.
```

Original project: <https://github.com/verdra-1/verdra>
