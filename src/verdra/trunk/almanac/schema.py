# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""msgspec structs for every key in R2.

The settings file nests keys by group: `general.close_to_tray` is stored as
`{"general": {"close_to_tray": true}}`. Every key, its type, range and default is defined here
once (Reference R2); the store validates key by key against these types, so one bad value never
costs the user their other settings.
"""

from __future__ import annotations

from typing import Annotated, Literal

import msgspec
from msgspec import Meta, Struct, field

from verdra.soil import terrain

FORMAT = terrain.FORMAT_SETTINGS
VERSION = 1

Port = Annotated[int, Meta(ge=1024, le=65535)]
OptionalPort = Annotated[int, Meta(ge=0, le=65535)]
LanguageTag = Annotated[str, Meta(pattern=r"^(system|[a-z]{2,3}(-[A-Za-z0-9]{2,8})*)$")]

RiskFeature = Literal[
    "accounts", "custom_flags", "multi_instance", "subplaces", "displayed_name", "traffic_editing"
]


class General(Struct, kw_only=True, omit_defaults=False):
    """Settings › General."""

    start_with_system: bool = False
    start_minimised: bool = True
    close_to_tray: bool = True
    route_on_launch: bool = True
    check_updates: bool = True
    update_channel: Literal["stable", "beta"] = "stable"
    language: LanguageTag = "system"
    onboarding_done: bool = False


class Upstream(Struct, kw_only=True):
    """Settings › Routing › Internet connection."""

    kind: Literal["system", "direct", "http", "socks5"] = "system"
    host: str = ""
    port: OptionalPort = 0
    username: str = ""


class Routing(Struct, kw_only=True):
    """Settings › Routing."""

    mode: Literal["per_app", "hosts_file"] = "per_app"
    proxy_port: Port = terrain.PROXY_PORT
    handle_roblox_links: bool = True
    close_roblox_on_quit: bool = False
    upstream: Upstream = field(default_factory=Upstream)


class Library(Struct, kw_only=True):
    """Settings › Library."""

    capture: bool = True
    size_cap_gb: Annotated[int, Meta(ge=1, le=100)] = 5
    location: str = ""


class Appearance(Struct, kw_only=True):
    """Settings › Appearance."""

    theme: Literal["system", "light", "dark"] = "system"
    # The four text sizes from Master plan 6.2 (see the S-02 spec on the R2 range).
    text_scale: Literal[90, 100, 115, 130] = 100
    reduce_motion: Literal["system", "on", "off"] = "system"
    density: Literal["comfortable", "compact"] = "comfortable"


class RiskAcceptance(Struct, kw_only=True):
    """When and in which version the user accepted one feature's risk warning."""

    accepted_at: str
    app_version: str


class Privacy(Struct, kw_only=True):
    """Settings › Privacy & safety."""

    risk_acceptances: dict[RiskFeature, RiskAcceptance] = field(default_factory=dict)
    keep_traffic: bool = False


class Advanced(Struct, kw_only=True):
    """Settings › Advanced."""

    advanced_mode: bool = False
    detailed_logging: bool = False
    #: When detailed logging was turned on (ISO 8601, UTC); it turns itself off 24 hours later.
    detailed_logging_since: str = ""
    worker_threads: Annotated[int, Meta(ge=1, le=16)] = 4


class FlagHotkey(Struct, kw_only=True):
    """A global shortcut that toggles one FastFlag while playing."""

    flag: str
    on_value: str
    off_value: str
    shortcut: str


class Tweaks(Struct, kw_only=True):
    """Feature state edited on the Tweaks screen."""

    custom_flags_enabled: bool = False
    active_flag_profile: str = ""
    flag_hotkeys: list[FlagHotkey] = field(default_factory=list)
    frame_rate_cap: Literal["unlimited"] | Annotated[int, Meta(ge=30, le=1000)] | None = None


class Accounts(Struct, kw_only=True):
    """Feature state edited on the Accounts screen."""

    launch_account: Annotated[int, Meta(ge=1)] | None = None
    multi_instance: bool = False
    subplaces: bool = False
    displayed_name: Annotated[str, Meta(max_length=20)] = ""
    privacy_mode: bool = False


class TrafficRule(Struct, kw_only=True):
    """One find-and-replace rule on the Traffic screen."""

    host: str
    where: Literal["json", "header", "query"]
    find: str
    replace: str
    enabled: bool = True


class Traffic(Struct, kw_only=True):
    """Feature state edited on the Traffic screen."""

    editing: bool = False
    rules: list[TrafficRule] = field(default_factory=list)


class Settings(Struct, kw_only=True):
    """Every setting, grouped as in Reference R2."""

    general: General = field(default_factory=General)
    routing: Routing = field(default_factory=Routing)
    library: Library = field(default_factory=Library)
    appearance: Appearance = field(default_factory=Appearance)
    privacy: Privacy = field(default_factory=Privacy)
    advanced: Advanced = field(default_factory=Advanced)
    tweaks: Tweaks = field(default_factory=Tweaks)
    accounts: Accounts = field(default_factory=Accounts)
    traffic: Traffic = field(default_factory=Traffic)


#: Groups shown on the Settings screen, in order (Master plan 7.7). The other groups hold feature
#: state edited on each feature's own screen.
SCREEN_GROUPS = ("general", "routing", "library", "appearance", "privacy", "advanced")


def defaults() -> dict[str, object]:
    """Return {dotted key: default} for every setting, nested groups flattened."""
    result: dict[str, object] = {}

    def walk(prefix: str, struct: Struct) -> None:
        for info in msgspec.structs.fields(type(struct)):
            value = getattr(struct, info.name)
            dotted = f"{prefix}{info.name}"
            if isinstance(value, Struct) and not isinstance(value, RiskAcceptance):
                walk(dotted + ".", value)
            else:
                result[dotted] = value

    walk("", Settings())
    return result


def field_type(dotted: str) -> object:
    """Return the annotated type of one dotted key, for validating a single value."""
    struct_type: type[Struct] = Settings
    *groups, name = dotted.split(".")
    for group in groups:
        struct_type = _field_info(struct_type, group).type
    return _field_info(struct_type, name).type


def _field_info(struct_type: type[Struct], name: str) -> msgspec.structs.FieldInfo:
    for info in msgspec.structs.fields(struct_type):
        if info.name == name:
            return info
    raise KeyError(name)
