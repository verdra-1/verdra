# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Constants: app IDs, service names, folder paths (R3).

Every name Verdra registers with an operating system or service is defined here and nowhere
else (Reference R3); a test checks that no other module spells them. Changing an identifier
would orphan users' system changes, so these never change once released.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

import platformdirs

# --- Shared across platforms -----------------------------------------------------------------

PRODUCT_NAME: Final = "Verdra"
DISTRIBUTION: Final = "verdra"
EXECUTABLE: Final = "verdra"
KEEPER_EXECUTABLE: Final = "verdra-keeper"
AUTHORS: Final = "q0f7"

#: Reverse-DNS base. Where a system forbids the hyphen (Flatpak and desktop-entry IDs) the
#: underscore form below is used instead.
APP_ID: Final = "io.github.verdra-1.verdra"
APP_ID_UNDERSCORE: Final = "io.github.verdra_1.verdra"

SECRET_SERVICE: Final = APP_ID
SECRET_ITEM_CA_KEY: Final = "ca-key"  # noqa: S105 - an item name, not a secret
SECRET_ITEM_ACCOUNT_PREFIX: Final = "account-"  # noqa: S105 - an item name, not a secret
SECRET_ITEM_UPSTREAM_PROXY: Final = "upstream-proxy"  # noqa: S105 - an item name, not a secret

CA_SUBJECT_COMMON_NAME: Final = "Verdra Local CA"
CA_SUBJECT_ORGANIZATION: Final = "Verdra"
CA_BEGIN_MARKER: Final = "# BEGIN Verdra Local CA"
CA_END_MARKER: Final = "# END Verdra Local CA"
HOSTS_MARKER: Final = "# verdra:route"

#: Inno Setup AppId: generated once at M0 (decision record 0004) and never changed.
INNO_APP_ID: Final = "{8F770622-386C-4265-AF56-B019A81EA7BE}"

PROXY_HOST: Final = "127.0.0.1"
PROXY_PORT: Final = 49443

SINGLE_INSTANCE_PREFIX: Final = "verdra-"
KEEPER_PROTOCOL: Final = "verdra-keeper/1"
REPOSITORY_URL: Final = "https://github.com/verdra-1/verdra"
URL_SCHEME: Final = "roblox-player"
PACK_EXTENSION: Final = ".verdrapack"
PACK_MIME_TYPE: Final = "application/vnd.verdra.pack+zip"

FORMAT_SETTINGS: Final = "verdra.settings"
FORMAT_LEDGER: Final = "verdra.ledger"
FORMAT_PROFILE: Final = "verdra.profile"
FORMAT_CLIMATE: Final = "verdra.climate"
FORMAT_TWEAKS: Final = "verdra.tweaks"
FORMAT_PACK: Final = "verdra.pack"
FORMAT_CATALOG: Final = "verdra.catalogue"
FORMAT_TRAFFIC: Final = "verdra.traffic"

CATALOG_INDEX_URL: Final = (
    "https://raw.githubusercontent.com/verdra-1/verdra-pollen/main/index.json"
)
CATALOG_SIGNATURE_URL: Final = CATALOG_INDEX_URL + ".sig"
RELEASES_API_URL: Final = "https://api.github.com/repos/verdra-1/verdra/releases"


def user_agent(version: str) -> str:
    """Return the User-Agent for Verdra's own web requests."""
    return f"Verdra/{version} (+{REPOSITORY_URL})"


# --- Folders (Master plan 9.1) ---------------------------------------------------------------

#: When set, every folder below lives under this one instead (tests and portable runs).
HOME_OVERRIDE_VARIABLE: Final = "VERDRA_HOME"

SETTINGS_FILE: Final = "settings.json"
STATE_FILE: Final = "state.json"
LEDGER_FILE: Final = "changes.json"
LOG_FILE: Final = "verdra.log"
#: Under the config folder (plan 9.1): the CA certificate.
TRUST_FOLDER: Final = "trust"
CA_CERTIFICATE_FILE: Final = "ca.crt"


def _override() -> Path | None:
    value = os.environ.get(HOME_OVERRIDE_VARIABLE)
    return Path(value) if value else None


def legal_dir() -> Path:
    """Return the folder holding LICENSE, NOTICE and PRIVACY.md for the About dialog.

    Each text exists once, at the repository root (decision record 0010). The PyInstaller build
    copies them into `assets/legal/` of the built app, together with the generated
    THIRD_PARTY_NOTICES.md; a source checkout reads them from the repository root.
    """
    package = Path(__file__).resolve().parent.parent
    bundled = package / "assets" / "legal"
    return bundled if bundled.is_dir() else package.parent.parent


def config_dir() -> Path:
    """Return the folder for settings, profiles, presets and the change ledger."""
    if (home := _override()) is not None:
        return home / "config"
    if sys.platform in {"win32", "darwin"}:
        return Path(platformdirs.user_data_dir(PRODUCT_NAME, appauthor=False, roaming=False))
    return Path(platformdirs.user_config_dir(DISTRIBUTION, appauthor=False))


def default_library_dir() -> Path:
    """Return the default library folder (database, blobs, previews)."""
    if (home := _override()) is not None:
        return home / "library"
    if sys.platform == "win32":
        return config_dir() / "Library"
    if sys.platform == "darwin":
        return Path(platformdirs.user_cache_dir(PRODUCT_NAME, appauthor=False)) / "Library"
    return Path(platformdirs.user_cache_dir(DISTRIBUTION, appauthor=False)) / "library"


def logs_dir() -> Path:
    """Return the folder for log files."""
    if (home := _override()) is not None:
        return home / "logs"
    if sys.platform == "win32":
        return config_dir() / "Logs"
    if sys.platform == "darwin":
        return Path(platformdirs.user_log_dir(PRODUCT_NAME, appauthor=False))
    return Path(platformdirs.user_state_dir(DISTRIBUTION, appauthor=False)) / "logs"


def exports_dir() -> Path:
    """Return the default folder for exports and support bundles."""
    if (home := _override()) is not None:
        return home / "exports"
    return Path(platformdirs.user_documents_dir()) / PRODUCT_NAME


# --- Windows ---------------------------------------------------------------------------------

WINDOWS_APP_USER_MODEL_ID: Final = APP_ID
WINDOWS_START_MENU_NAME: Final = PRODUCT_NAME
WINDOWS_AUTOSTART_KEY: Final = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_AUTOSTART_VALUE: Final = PRODUCT_NAME
WINDOWS_URL_HANDLER_KEY: Final = r"Software\Classes\roblox-player"
WINDOWS_PACK_PROGID: Final = "Verdra.Pack"
WINDOWS_KEEPER_SERVICE: Final = "VerdraKeeper"
WINDOWS_KEEPER_DISPLAY_NAME: Final = "Verdra Keeper"
WINDOWS_KEEPER_PIPE: Final = r"\\.\pipe\verdra-keeper"
WINDOWS_WATCHDOG_TASK: Final = r"\Verdra\Verdra Owl"

# --- macOS -----------------------------------------------------------------------------------

MACOS_BUNDLE_ID: Final = APP_ID
MACOS_KEEPER_LABEL: Final = APP_ID + ".keeper"
MACOS_KEEPER_SOCKET: Final = f"/var/run/{MACOS_KEEPER_LABEL}.sock"
MACOS_PACK_UTI: Final = APP_ID + ".pack"

# --- Linux (paused, planned later: reference only, decision record 0018) ----------------------

LINUX_FLATPAK_ID: Final = APP_ID_UNDERSCORE
LINUX_DESKTOP_ENTRY: Final = APP_ID_UNDERSCORE + ".desktop"
LINUX_METAINFO: Final = APP_ID_UNDERSCORE + ".metainfo.xml"
LINUX_HANDLER_DESKTOP_ENTRY: Final = APP_ID_UNDERSCORE + ".handler.desktop"
LINUX_POLKIT_ACTION: Final = APP_ID + ".keeper"
LINUX_POLKIT_POLICY_PATH: Final = f"/usr/share/polkit-1/actions/{LINUX_POLKIT_ACTION}.policy"
LINUX_KEEPER_PATH: Final = "/usr/local/libexec/verdra/verdra-keeper"
LINUX_KEEPER_SOCKET: Final = "/run/verdra-keeper.sock"
LINUX_WATCHDOG_UNIT: Final = "verdra-owl.service"
LINUX_ICON_NAME: Final = APP_ID_UNDERSCORE
LINUX_TRAY_ICON_NAME: Final = APP_ID_UNDERSCORE + "-symbolic"
SOBER_FLATPAK_ID: Final = "org.vinegarhq.Sober"
