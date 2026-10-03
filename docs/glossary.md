# Glossary

The same list as Reference R6 of the Master Build Plan. The first table maps code names to what
users see; a nature name must not appear in the interface where a plain word is listed, except in
brand moments (splash, empty states).

## Code names

| Code name | Plain meaning | Shown to users as |
| --- | --- | --- |
| canopy | User interface layer | — |
| crown | Window frame and app-wide UI | — |
| leaves | Reusable widgets | — |
| glade | Asset previews | Preview |
| dew | Toast notifications | — |
| seedling | First-run onboarding | Setup |
| trunk | App services and state | — |
| sapwood | App lifetime: startup, single instance, shutdown | — |
| almanac | Settings store | Settings |
| rings | Logging; the Activity screen | Activity |
| tendrils | Background jobs | — |
| budding | Update check | Updates |
| branches | Feature services | — |
| grafts | Replacement profiles and their service; the Replacements screen | Replacements, replacement profile |
| pollen | Preset catalogue (verdra-1/verdra-pollen) | Presets |
| seedpods | Packs | Pack |
| transplant | Import of replacement profiles from other tools | Import |
| cuttings | File tweaks | File tweaks |
| climate | FastFlags and the frame-rate cap | FastFlags, Frame-rate cap |
| garden | The Tweaks screen | Tweaks |
| hive | Accounts | Accounts |
| sprout | Launching Roblox | Launch |
| trails | Subplaces | Subplaces |
| mimicry | Displayed name and privacy mode | Name display, Privacy mode |
| fallow | Reset everything | Reset everything |
| streams | Traffic | Traffic |
| roots | Network engine (the proxy) | Routing |
| mycelium | Proxy listener | — |
| hyphae | One proxied connection | — |
| litmus | Diagnostic interception, from source only (decision record 0015) | — |
| taproot | Upstream connections | Internet connection |
| gardener | Routing lifecycle and status | Routing status |
| burrow | Hosts-file routing | Hosts-file routing |
| owl | Crash watchdog | Verdra Owl (task and service names only) |
| rules | Rule snapshots | — |
| symbionts | Proxy pipeline handlers | — |
| grafter | Replacement handler | — |
| forager | Capture handler | Capture new assets |
| trailguard | Subplace join handler | — |
| bark | Trust and protection layer | — |
| resin | Certificate authority | Verdra's certificate |
| husk | OS secret store access | Secure storage |
| nectar | Login tokens | Login token |
| pollinator | Roblox web client | — |
| rain | Verified downloads | — |
| seal | Signature checks | Verified, Not signed |
| scar | System change ledger | System changes |
| veil | Redaction filter | •••• (redacted) |
| seedbank | Asset store | Library |
| vault | Library database and blobs | — |
| sieve | Library search | Search |
| harvest | Exports | Export |
| kinds | Asset types | Asset type |
| strata | File formats layer | — |
| amber | Models (RBXM, RBXMX) | Models |
| clay | Meshes | Meshes |
| ochre | Textures | Images |
| sway | Animations and rigs | Animations |
| granite | Solid models (CSG), after 1.0 | — |
| soil | Platform adapters and shared foundations | — |
| humus | Platform interface | — |
| terrain | Constants: IDs and paths | — |
| atomic | Safe file writes | — |
| lichen | Keeper protocol | — |
| meadow / orchard / tundra | Windows / macOS (deferred until after 1.0) / Linux adapters | — |
| keeper | Privileged helper for Hosts-file routing | Helper, Verdra Keeper |
## Product terms

| Term | Meaning |
| --- | --- |
| Replacement | One rule: an original asset and what it becomes on your screen (another asset ID, a local file, an HTTPS link, or removed). |
| Replacement profile | A named, switchable set of replacements (verdra.profile). |
| Preset | A replacement profile published in the signed catalogue. |
| Pack | A .verdrapack file: one or more profiles with the files they use, for sharing. |
| Library | Assets Verdra captured while Roblox ran through it, stored locally for preview and export. |
| Routing | Sending Roblox's traffic through Verdra's local proxy, per app or through the hosts file. |
| Per-app routing | Roblox started by Verdra with proxy settings; no administrator rights. |
| Hosts-file routing | Roblox hostnames pointed at this computer through the hosts file; needs the keeper. |
| Interception | Decrypting a Roblox connection with Verdra's certificate so a feature can read or change it. Everything else passes through untouched. |
| Apply now | Save, clear Roblox's asset cache and restart Roblox through Verdra. |
| System change | Anything Verdra changes outside its own folders; listed in Settings › System changes and undone by Reset everything. |
| Risk badge | One of four labels on every feature: Cosmetic, Client behaviour, Account-sensitive, Moderation risk (5.5). |
| FastFlag | A Roblox client setting delivered by Roblox's servers or a local file. |
| Allowlist (FastFlags) | Roblox's published list of flags users may set locally. |
| Allowlist (licences) | Licences dependencies may use (12.3). |
| Login token | The browser cookie that proves a Roblox sign-in; Verdra stores it only in the OS secret store. |
| Subplace | A place inside an experience other than its start place. |
| Clean room | Building Verdra without access to the old tool's code (3.1). |
| Spec | A feature specification in the Feature specs tab and docs/specs/. |
| Exit gate | The conditions a milestone must meet before its version is tagged. |
| Sober | The Roblox client for Linux, distributed as a Flatpak by VinegarHQ. |
