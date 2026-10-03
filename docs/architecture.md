# Architecture

This page mirrors Master Build Plan section 8 and Reference R1. The plan is the source of truth;
when it changes, this page changes in the same pull request.

## Areas and layering

Seven areas, nature-named all the way down. Code names are explained in [glossary.md](glossary.md).

| Area | Job |
| --- | --- |
| `canopy` | Everything the user sees |
| `trunk` | App services and state |
| `roots` | Network engine |
| `bark` | Trust and protection |
| `seedbank` | Asset store |
| `strata` | File formats |
| `soil` | Platform adapters and shared foundations |

Imports flow one way: `canopy → trunk → {roots, seedbank, strata, bark} → soil`.

- `trunk` is the only layer the UI talks to: `canopy` imports `trunk` and the shared foundations
  in `soil`, never `roots`, `seedbank`, `strata` or `bark`.
- Inside the middle layer, `roots` may use `strata` and `bark`; `seedbank` may use `strata` and
  `bark`; `strata` and `bark` use only `soil`. `roots` and `seedbank` don't import each other,
  nor do `strata` and `bark`.
- Nothing imports upward. `soil` imports nothing from the other areas: it holds the shared
  constants (`soil/terrain`: paths and app IDs) and the safe-write helper (`soil/atomic`).
- OS actions in `soil` never write the ledger themselves; the caller records the ledger entry
  (`bark/scar`) before calling them.

`lint-imports` enforces these rules in CI (contracts in `pyproject.toml`).

## Processes and threads

- **Main process** (normal user): the Qt main thread for the UI; one asyncio thread for the proxy
  (`roots`); one worker pool (`trunk/tendrils`, 4 threads by default) for decoding, conversion,
  disk and web lookups.
- **Keeper** (separate small executable, privileged): only in Hosts-file mode.
- Qt queued signals carry results towards the UI; thread-safe queues carry events from the proxy
  to services; services hand the proxy immutable rule snapshots, swapped with one reference
  assignment, so the proxy never takes a lock to read them.
- The proxy thread never blocks on disk, the UI or the network beyond the request it forwards.

## Module tree

Every package and module under `src/verdra/`, with its one-line job. The docstring of each module
and `__init__.py` starts with exactly this job; `tools/check_docs.py` checks both directions
(every line here exists as a module, every module has a line here). Modules in `meadow/` and
`orchard/` are the same as those listed under `tundra/`. Adding a module means adding a line here
and an entry in [provenance.md](provenance.md).

```text
src/verdra/
├── __init__.py              Exposes the version, read from package metadata. Nothing else.
├── __main__.py              Entry point for `python -m verdra` and the frozen app; hands over to trunk/sapwood.
│
├── canopy/                  Everything the user sees. Qt widgets only: no network, disk or OS calls of its own.
│   ├── crown/               The window frame and app-wide UI.
│   │   ├── window.py        Main window: sidebar, header, content stack, splitter and geometry memory.
│   │   ├── header.py        Screen title, status pill and its popover, profile selector, Apply now button.
│   │   ├── sidebar.py       Navigation, collapse to icons, items shown only in Advanced mode.
│   │   ├── tray.py          Tray or menu-bar icon, the tray menu (7.10), status-variant icons.
│   │   ├── theme.py         Turns tokens.json into QPalette and a style sheet; live light/dark switching; text scale; density.
│   │   ├── dew.py           Toasts: queue, stacking (at most 3), timers, one optional action, mirror to Activity.
│   │   ├── splash.py        Splash window (480 × 300) and the Living V growth animation.
│   │   ├── seedling.py      First-run onboarding (7.9).
│   │   ├── shortcuts.py     Keyboard shortcuts (7.1) and their help overlay.
│   │   └── about.py         About dialog; licence, third-party notices and privacy viewers.
│   ├── leaves/              Reusable widgets built only from tokens.
│   │   ├── switch.py        Pill switch with the leaf glyph on the thumb when on.
│   │   ├── progress.py      Progress bar with leading leaf, arc spinner.
│   │   ├── badge.py         Risk badges (four levels) and status pills (four states).
│   │   ├── notice.py        Inline notices: info, success, warning, danger.
│   │   ├── dialogs.py       Risk warning, explanation and destructive confirmation dialogs (7.8).
│   │   ├── empty.py         Empty states with illustration, heading, sentence and up to two buttons.
│   │   ├── tables.py        Virtualised table view, filter proxy models, column memory.
│   │   ├── fields.py        Asset-ID field, file picker, HTTPS-only URL field, all with live validation.
│   │   └── drawer.py        Right-hand drawer container with Save / Cancel footer.
│   ├── glade/               Previews.
│   │   ├── image.py         Image preview: zoom, fit, channel view (RGB, R, G, B, A).
│   │   ├── mesh.py          OpenGL mesh viewer: orbit and fly camera, wireframe and grid toggles.
│   │   ├── audio.py         Audio player with waveform (Qt Multimedia).
│   │   ├── motion.py        Animation player on an R6 or R15 rig with speed control.
│   │   ├── font.py          Font specimen.
│   │   └── model.py         Instance tree with a property table.
│   └── screens/             One package or module per sidebar entry.
│       ├── grafts/          Replacements screen.
│       │   ├── screen.py    Profiles list, replacements table, toolbar.
│       │   ├── editor.py    Editor drawer (Asset ID · Local file · URL · Remove).
│       │   ├── preview.py   Preview changes dialog.
│       │   ├── presets.py   Presets dialog (catalogue cards).
│       │   └── imports.py   Import and pack dialogs.
│       ├── seedbank.py      Library screen.
│       ├── garden.py        Tweaks screen: file tweaks, FastFlags, frame-rate cap.
│       ├── hive.py          Accounts screen: list, add wizard, launch panel, multi-instance, subplaces, name display.
│       ├── streams.py       Traffic screen (Advanced mode only).
│       ├── rings.py         Activity screen.
│       └── settings.py      Settings screen, including System changes and Reset everything.
│
├── trunk/                   App services and state. The only layer the UI talks to.
│   ├── sapwood/             App lifetime.
│   │   ├── cli.py           Command-line flags: --reset-everything [--quiet], --minimized, a roblox-player: link.
│   │   ├── single.py        Single instance through a local socket; forwards a second launch's link.
│   │   ├── startup.py       Startup order (8.4) with step timestamps.
│   │   └── shutdown.py      Shutdown order: stop routing, clear hosts entries, flush logs and settings.
│   ├── almanac/             Settings.
│   │   ├── schema.py        msgspec structs for every key in R2.
│   │   ├── store.py         Load, validate, save atomically with .bak; change signals.
│   │   └── migrate.py       One function per schema step; newer files open read-only.
│   ├── rings.py             Logging: rotating files (5 × 2 MB), Activity model, redaction through bark/veil.
│   ├── tendrils.py          Job executor: worker pool, progress, cancellation, results back on the Qt thread.
│   ├── budding.py           Update check against GitHub Releases, at most once per 24 hours.
│   └── branches/            Feature services: hold state, compile rule snapshots, call the lower layers.
│       ├── grafts.py        Replacement profiles: store, validation, conflicts, snapshot compile, undo and redo.
│       ├── pollen.py        Preset catalogue: fetch, verify (bark/seal), cache, add as profile.
│       ├── seedpods.py      Pack export and import (.verdrapack).
│       ├── transplant.py    One-time import of replacement profiles from other tools.
│       ├── cuttings.py      File tweaks: stash originals, apply, re-apply after a Roblox update.
│       ├── climate.py       FastFlag presets, custom flags, flag profiles, hotkeys, frame-rate cap.
│       ├── hive.py          Accounts: add, validate, choose the account used for launches, remove.
│       ├── sprout.py        Launching Roblox: environment, link handling, Apply now restart, multi-instance.
│       ├── trails.py        Subplace browsing and joining.
│       ├── mimicry.py       Displayed name and privacy mode.
│       └── fallow.py        Reset everything: undo every ledger entry in reverse order.
│
├── roots/                   Network engine. Runs on the proxy thread; never touches the UI.
│   ├── mycelium.py          Loopback listener, CONNECT handling, interception decision, TLS termination with leaf certificates.
│   ├── hyphae.py            One connection: HTTP/1.1 through h11, keep-alive, chunked bodies, the symbiont pipeline.
│   ├── taproot.py           Upstream side: verified TLS, SNI, transports (direct, system, HTTP CONNECT, SOCKS5), connection pool.
│   ├── gardener.py          Routing lifecycle and status (Idle, Routing, Degraded, Error); CA in Roblox trust files; coexistence check.
│   ├── burrow.py            Hosts-file routing: keeper client calls, DNS pre-resolution (dnspython), 20 s lease heartbeat.
│   ├── owl.py               Crash watchdog registration (scheduled task, launchd job or systemd unit) and its cleanup command.
│   ├── rules.py             Immutable rule snapshot types shared by trunk and the proxy.
│   ├── litmus.py            Diagnostic interception, from source only: every 10.2 host, nothing changed, TLS details logged.
│   └── symbionts/           Request and response handlers in the proxy pipeline. A crash in one never fails the request.
│       ├── grafter.py       Rewrites asset batch requests and responses; serves replacement content.
│       ├── forager.py       Copies downloaded assets into the library queue.
│       ├── climate.py       Merges the user's flags into client-settings responses.
│       ├── mimicry.py       Rewrites displayed names in profile responses.
│       ├── trailguard.py    Detects the place being joined; adjusts subplace join requests.
│       └── streams.py       Records traffic; hold, edit, forward, drop, replay; find-and-replace rules.
│
├── bark/                    Trust and protection.
│   ├── resin.py             CA: create, rotate 30 days before expiry, Name Constraints; leaf certificates in memory.
│   ├── husk.py              OS secret store through keyring; Linux fallback file (0600) for the CA key only.
│   ├── nectar.py            Login tokens: validate against Roblox, store one item per account, never log.
│   ├── pollinator.py        Roblox web client (httpx): exact-domain cookies, CSRF refresh, timeouts, rate limits.
│   ├── rain.py              Verified downloads: HTTPS only, size limits per type, SHA-256 cache.
│   ├── seal.py              Ed25519 verification of the catalogue; current key plus one announced successor.
│   ├── scar.py              System change ledger (9.4): write-ahead entries, status, undo descriptors.
│   └── veil.py              The one redaction filter (10.6) used by logs, Traffic, exports and support bundles.
│
├── seedbank/                Asset store.
│   ├── vault.py             SQLite schema (9.5), blob folders, eviction, pinning, check and repair, moving the library.
│   ├── sieve.py             Full-text search (FTS5) and filters.
│   ├── harvest.py           Exports per type (9.6).
│   └── kinds.py             Asset types, Roblox type numbers, magic-byte sniffing.
│
├── strata/                  File formats. Pure functions over bytes; no I/O beyond what the caller passes in.
│   ├── amber/               Models: binary RBXM reader, RBXMX through defusedxml, instance tree, property types.
│   ├── clay/                Meshes: FileMesh reader and writer (every documented version), Draco through DracoPy, OBJ import and export.
│   ├── ochre/               Textures: KTX2 reader and writer, block decoding through texture2ddecoder, PNG conversion, TexturePack slots.
│   ├── sway/                Animations: KeyframeSequence reading, R6 and R15 rigs downloaded at runtime.
│   └── granite/             Solid models (CSG). Empty package until after 1.0.
│
├── soil/                    Platform adapters and shared foundations. Imports nothing from the other areas.
│   ├── humus.py             The Platform protocol every OS package implements; picks the right one at startup.
│   ├── terrain.py           Constants: app IDs, service names, folder paths (R3).
│   ├── atomic.py            Safe writes: temp file, fsync, rename, .bak rotation.
│   ├── lichen.py            Keeper protocol: JSON-lines message types and version (standard library only).
│   ├── meadow/              Windows.
│   ├── orchard/             macOS: deferred until after 1.0; every module returns "unsupported on this system".
│   └── tundra/              Linux and Sober.
│       (each OS package has the same modules:)
│       ├── launcher.py      Find Roblox, start it with the proxy variables, register the roblox-player: handler.
│       ├── instances.py     Multi-instance support (Moderation risk). Windows and macOS per S-51; Linux as Sober allows (confirm at M5), otherwise unsupported.
│       ├── keeper.py        The privileged helper's entry point; built separately with packaging/keeper.spec.
│       ├── keeper_client.py Install, start, stop and talk to the keeper.
│       ├── watchdog.py      The OS part of roots/owl.
│       ├── autostart.py     Start with the system.
│       ├── hotkeys.py       Global hotkeys.
│       └── files.py         Roblox trust file, cache, client-settings and tweak target paths for this OS.
│
└── assets/                  Bundled files (no code).
    ├── brand/               tokens.json, logo SVGs, splash frames, generated icon sizes.
    ├── icons/               Lucide subset and the custom icons (leaf, node, vine, seed).
    ├── fonts/               Font files with their OFL texts.
    ├── i18n/                verdra_en.ts source and compiled .qm files.
    ├── flags/               Curated FastFlag preset file built from Roblox's published allowlist.
    └── legal/               LICENSE, NOTICE, PRIVACY and the generated THIRD_PARTY_NOTICES for the About dialog.
```


One module differs from R1: `roots/litmus.py`, the diagnostic interception of spec S-11, runs
from source only and is left out of every build (decision record 0015).

Tests mirror this tree under `tests/` (for example `tests/roots/test_hyphae.py`). A module whose
platform doesn't support a feature (for example `tundra/instances.py`) still exists and returns a
typed "unsupported" result with the reason, so the UI can explain it.
