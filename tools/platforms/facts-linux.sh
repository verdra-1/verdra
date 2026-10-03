#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
#
# Verdra: Sober's facts from docs/platforms/protocol.md that need only an installed Sober
# (L-01, L-02, L-03, L-04, L-05, L-07), for the Platform facts workflow.
#
# Sober is never started. The one `flatpak run` is `--command=sha256sum` inside Sober's sandbox,
# for L-07; it runs sha256sum from the runtime, not Sober. Files are listed by name, size and
# SHA-256 only; the only files read are Flatpak's own metadata and Sober's desktop entry.
#
# Usage: facts-linux.sh OUTPUT_FILE
set -uo pipefail

out=${1:?usage: facts-linux.sh OUTPUT_FILE}
app=org.vinegarhq.Sober
mkdir -p "$(dirname "$out")"
: > "$out"

section() { printf '\n== %s ==\n' "$1" >> "$out"; }
run() { printf '$ %s\n' "$*" >> "$out"; "$@" >> "$out" 2>&1 || printf '(exit %s)\n' "$?" >> "$out"; }

echo "Verdra platform facts, Linux CI runner (docs/platforms/protocol.md)" >> "$out"
echo "Date: $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$out"

section "Step 0 The machine"
run grep -E '^(NAME|VERSION)=' /etc/os-release
run uname -m
run flatpak --version

section "L-01 Sober's ID, version, commit, runtime and permissions"
run flatpak info "$app"
run flatpak info --show-permissions "$app"
run flatpak info --show-metadata "$app"

location=$(flatpak info --show-location "$app" 2>/dev/null)
section "L-02 Trust files Sober ships (names, sizes, SHA-256), and its runtime"
echo "Install location: $location" >> "$out"
if [ -n "$location" ]; then
  find "$location" \( -name '*.pem' -o -name '*.crt' -o -name '*cacert*' -o -name '*ca-bundle*' \) \
    -type f -printf '%P | %s bytes\n' >> "$out" 2>&1
  find "$location" \( -name '*.pem' -o -name '*.crt' -o -name '*cacert*' -o -name '*ca-bundle*' \) \
    -type f -exec sha256sum {} + 2>/dev/null | sed "s|$location/||" >> "$out"
  echo "(end of trust-file list)" >> "$out"
fi
run flatpak info --show-runtime "$app"

section "L-02/L-03/L-04 Sober's per-user folders before any start"
home_dir="$HOME/.var/app/$app"
if [ -e "$home_dir" ]; then
  find "$home_dir" -printf '%P | %y | %s bytes\n' >> "$out"
else
  echo "Not present: ~/.var/app/$app (Flatpak creates it on Sober's first start)" >> "$out"
fi

section "L-03/L-04 Every file name Sober installs (names and sizes only, nothing opened)"
if [ -n "$location" ]; then
  find "$location/files" -type f -printf '%P | %s bytes\n' 2>/dev/null | sort >> "$out"
fi

section "L-05 Link handler"
for dir in /var/lib/flatpak/exports/share/applications "$HOME/.local/share/flatpak/exports/share/applications"; do
  for entry in "$dir"/*"$app"*.desktop; do
    [ -f "$entry" ] || continue
    echo "Desktop entry: $entry" >> "$out"
    grep -E '^(Name|Exec|MimeType)=' "$entry" >> "$out"
  done
done
run env XDG_DATA_DIRS="/var/lib/flatpak/exports/share:/usr/share" xdg-mime query default x-scheme-handler/roblox-player

section "L-07 /etc/hosts from the host and from inside Sober's sandbox (hashes only)"
run sha256sum /etc/hosts
run flatpak run --command=sha256sum "$app" /etc/hosts

echo >> "$out"
echo "End of report." >> "$out"
cat "$out"
