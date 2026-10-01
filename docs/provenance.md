# Provenance

One entry per module under `src/verdra/`, as required by Master Build Plan section 3.1 (process
control 3): what the module was built from. Allowed inputs are the specs in `docs/specs/`, public
documentation, Roblox's observable behaviour captured with Verdra's own tools, and the libraries
in the licence allowlist. No entry may cite another asset-replacement tool's code.

`tools/check_docs.py` fails CI when a module has no entry. Name a module by its path relative to
`src/` in backticks; a package's `__init__.py` may be named by its folder.

| Module | Built from | Libraries |
| --- | --- | --- |
| `verdra/` | Reference R1 (module tree) | Standard library (`importlib.metadata`) |
| `verdra/__main__.py` | Reference R1 | Standard library |
| `verdra/bark/` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/husk.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/nectar.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/pollinator.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/rain.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/resin.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/scar.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/seal.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/bark/veil.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/about.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/dew.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/header.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/seedling.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/shortcuts.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/sidebar.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/splash.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/theme.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/tray.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/crown/window.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/audio.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/font.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/image.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/mesh.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/model.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/glade/motion.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/badge.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/dialogs.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/drawer.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/empty.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/fields.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/notice.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/progress.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/switch.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/leaves/tables.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/garden.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/grafts/` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/grafts/editor.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/grafts/imports.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/grafts/presets.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/grafts/preview.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/grafts/screen.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/hive.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/rings.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/seedbank.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/settings.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/canopy/screens/streams.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/burrow.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/gardener.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/hyphae.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/mycelium.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/owl.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/rules.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/climate.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/forager.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/grafter.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/mimicry.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/streams.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/symbionts/trailguard.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/roots/taproot.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/seedbank/` | Reference R1 (job line only; no code yet) | — |
| `verdra/seedbank/harvest.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/seedbank/kinds.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/seedbank/sieve.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/seedbank/vault.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/atomic.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/humus.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/lichen.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/autostart.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/files.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/hotkeys.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/instances.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/keeper.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/keeper_client.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/launcher.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/meadow/watchdog.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/autostart.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/files.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/hotkeys.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/instances.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/keeper.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/keeper_client.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/launcher.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/orchard/watchdog.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/terrain.py` | Reference R3 (system identifiers) | Standard library |
| `verdra/soil/tundra/` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/autostart.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/files.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/hotkeys.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/instances.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/keeper.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/keeper_client.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/launcher.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/soil/tundra/watchdog.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/strata/` | Reference R1 (job line only; no code yet) | — |
| `verdra/strata/amber/` | Reference R1 (job line only; no code yet) | — |
| `verdra/strata/clay/` | Reference R1 (job line only; no code yet) | — |
| `verdra/strata/granite/` | Reference R1 (job line only; no code yet) | — |
| `verdra/strata/ochre/` | Reference R1 (job line only; no code yet) | — |
| `verdra/strata/sway/` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/almanac/` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/almanac/migrate.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/almanac/schema.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/almanac/store.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/climate.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/cuttings.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/fallow.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/grafts.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/hive.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/mimicry.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/pollen.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/seedpods.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/sprout.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/trails.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/branches/transplant.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/budding.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/rings.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/sapwood/` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/sapwood/cli.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/sapwood/shutdown.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/sapwood/single.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/sapwood/startup.py` | Reference R1 (job line only; no code yet) | — |
| `verdra/trunk/tendrils.py` | Reference R1 (job line only; no code yet) | — |
