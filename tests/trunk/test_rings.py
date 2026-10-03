# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-03: activity log."""

import json
import logging
import time
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from verdra.bark import veil
from verdra.trunk import rings
from verdra.trunk.almanac.store import SettingsStore

from ..bark.test_veil import SECRETS

log = logging.getLogger("verdra.test")


@pytest.fixture
def logging_on(tmp_path: Path) -> Iterator[rings.Rings]:
    installed = rings.Rings(tmp_path / "logs")
    installed.start(detailed=True)
    yield installed
    installed.stop()


def bundle_sources(tmp_path: Path) -> rings.BundleSources:
    return rings.BundleSources(
        routing_mode="per_app",
        routing_status="Idle",
        settings_file=tmp_path / "config" / "settings.json",
        ledger_file=tmp_path / "config" / "changes.json",
        profiles_dir=tmp_path / "config" / "profiles",
    )


@pytest.mark.spec("S-03", 1)
def test_secrets_are_redacted_everywhere(logging_on: rings.Rings, tmp_path: Path) -> None:
    secrets = [secret for _text, secret in SECRETS]
    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
        for text, _secret in SECRETS:
            log.log(level, text)
            log.log(level, "argument: %s", text)
            try:
                raise RuntimeError(text)
            except RuntimeError:
                log.log(level, "failed", exc_info=True)
    logging_on.stop()
    file_text = logging_on.log_file.read_text(encoding="utf-8")
    ring_text = "\n".join(record.message for record in logging_on.ring.snapshot())
    target = rings.export_support_bundle(
        tmp_path / "bundle.zip", logging_on, bundle_sources(tmp_path)
    )
    with zipfile.ZipFile(target) as bundle:
        bundle_text = "\n".join(bundle.read(name).decode("utf-8") for name in bundle.namelist())
    for text in (file_text, ring_text, bundle_text):
        assert veil.REDACTED in text
        for secret in secrets:
            assert secret not in text
    assert file_text.count("RuntimeError: ") == 4 * len(SECRETS)


@pytest.mark.spec("S-03", 2)
def test_rotation_keeps_five_files_of_two_megabytes(logging_on: rings.Rings) -> None:
    line = "x" * 1000
    for _ in range(13_000):  # about 13 MB
        log.info(line)
    logging_on.stop()
    files = sorted(logging_on.logs_dir.iterdir())
    assert len(files) == rings.FILE_COUNT
    assert all(path.stat().st_size <= rings.FILE_BYTES for path in files)


@pytest.mark.spec("S-03", 3)
def test_search_over_5000_records_is_fast(qtbot: QtBot) -> None:
    # Times the filter the Activity screen really uses (review finding H3).
    ring = rings.RingBuffer()
    for n in range(5000):
        ring.append(
            rings.ActivityRecord(
                time.time(), logging.INFO, "verdra.x", f"Replaced asset {n} in profile {n % 7}"
            )
        )
    model = rings.ActivityModel(ring)
    proxy = rings.ActivityFilter()
    proxy.setSourceModel(model)
    proxy.set_levels({logging.INFO, logging.WARNING})
    started = time.perf_counter()
    proxy.set_text("PROFILE 3")
    shown = proxy.rowCount()
    assert time.perf_counter() - started < 0.1
    assert shown == len([n for n in range(5000) if n % 7 == 3])
    proxy.set_levels({logging.ERROR})
    assert proxy.rowCount() == 0


@pytest.mark.spec("S-03", 4)
def test_debug_records_only_with_detailed_logging(tmp_path: Path, qtbot: QtBot) -> None:
    installed = rings.Rings(tmp_path / "logs")
    installed.start(detailed=False)
    settings = SettingsStore(tmp_path / "settings.json")
    settings.load()
    detailed = rings.DetailedLogging(installed, settings)
    log.debug("hidden detail")
    settings.set("advanced.detailed_logging", True)
    assert settings.value("advanced.detailed_logging_since")
    log.debug("visible detail")
    installed.stop()
    messages = [record.message for record in installed.ring.snapshot()]
    assert "visible detail" in messages
    assert "hidden detail" not in messages
    # 24 hours later, it turns itself off (also when Verdra starts after the deadline).
    past = datetime.now(UTC) - timedelta(hours=24, minutes=1)
    settings.set("advanced.detailed_logging_since", past)
    restarted = rings.DetailedLogging(installed, settings)
    assert settings.value("advanced.detailed_logging") is False
    assert not installed.detailed
    installed.start(detailed=installed.detailed)
    assert logging.getLogger(rings.LOGGER_NAME).level == logging.INFO
    installed.stop()
    del detailed, restarted


@pytest.mark.spec("S-03", 4)
def test_detailed_logging_turns_off_after_24_hours_across_a_restart(
    tmp_path: Path, qtbot: QtBot
) -> None:
    """R2 advanced.detailed_logging_since: the deadline survives a restart (plan 16.2)."""
    path = tmp_path / "settings.json"
    first = SettingsStore(path)
    first.load()
    installed = rings.Rings(tmp_path / "logs")
    installed.start(detailed=False)
    detailed = rings.DetailedLogging(installed, first)
    first.set("advanced.detailed_logging", True)
    first.flush()
    saved = json.loads(path.read_text(encoding="utf-8"))["advanced"]["detailed_logging_since"]
    assert datetime.fromisoformat(saved).tzinfo is not None
    # Turning it off clears the timestamp.
    first.set("advanced.detailed_logging", False)
    assert first.value("advanced.detailed_logging_since") is None
    # On again, then Verdra quits and starts 25 hours later.
    first.set("advanced.detailed_logging", True)
    first.set("advanced.detailed_logging_since", datetime.now(UTC) - timedelta(hours=25))
    first.flush()
    second = SettingsStore(path)
    second.load()
    restarted = rings.DetailedLogging(installed, second)
    second.flush()
    installed.stop()
    after = json.loads(path.read_text(encoding="utf-8"))["advanced"]
    assert after["detailed_logging"] is False
    assert after["detailed_logging_since"] is None
    del detailed, restarted


def test_expiry_rule() -> None:
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    assert rings.detailed_logging_expired(None, now)
    assert rings.detailed_logging_expired(datetime(2026, 10, 1, 12, 0, tzinfo=UTC), now)
    assert not rings.detailed_logging_expired(datetime(2026, 10, 1, 12, 0, 1, tzinfo=UTC), now)


@pytest.mark.spec("S-03", 5)
def test_support_bundle_contents(logging_on: rings.Rings, tmp_path: Path) -> None:
    sources = bundle_sources(tmp_path)
    sources.settings_file.parent.mkdir(parents=True)
    sources.settings_file.write_text(
        json.dumps({"format": "verdra.settings", "version": 1, "x": {"Cookie": "a=1"}}),
        encoding="utf-8",
    )
    sources.ledger_file.write_text(
        json.dumps({"format": "verdra.ledger", "version": 1}), encoding="utf-8"
    )
    sources.profiles_dir.mkdir()
    (sources.profiles_dir / "Clean UI.json").write_text("{}", encoding="utf-8")
    for n in range(2500):
        log.info("line %d", n)
    logging_on.stop()

    without = rings.export_support_bundle(tmp_path / "a.zip", logging_on, sources)
    with zipfile.ZipFile(without) as bundle:
        assert sorted(bundle.namelist()) == [
            "about.json",
            "changes.json",
            "settings.json",
            "verdra.log",
        ]
        about = json.loads(bundle.read("about.json"))
        assert {
            "version",
            "build",
            "system",
            "architecture",
            "routing_mode",
            "routing_status",
        } <= about.keys()
        lines = bundle.read("verdra.log").decode("utf-8").splitlines()
        assert len(lines) == rings.BUNDLE_LOG_LINES
        assert lines[-1].endswith("line 2499")
        assert "a=1" not in bundle.read("settings.json").decode("utf-8")

    with_profiles = rings.export_support_bundle(
        tmp_path / "b.zip", logging_on, sources, include_profiles=True
    )
    with zipfile.ZipFile(with_profiles) as bundle:
        assert "profiles/Clean UI.json" in bundle.namelist()


def test_support_bundle_redacts_log_lines_written_by_others(
    logging_on: rings.Rings, tmp_path: Path
) -> None:
    # A line that never went through the filter (an older version, the keeper, a hand edit)
    # must still be redacted in the bundle (review finding M18).
    logging_on.stop()
    with logging_on.log_file.open("a", encoding="utf-8") as handle:
        handle.write("2026-10-01 12:00:00,000 INFO    x: Cookie: session=UNFILTERED1\n")
    bundle_path = rings.export_support_bundle(
        tmp_path / "c.zip", logging_on, bundle_sources(tmp_path)
    )
    with zipfile.ZipFile(bundle_path) as bundle:
        text = bundle.read("verdra.log").decode("utf-8")
    assert "UNFILTERED1" not in text
    assert f"Cookie: {veil.REDACTED}" in text


@pytest.mark.spec("S-03", 7)
def test_ring_buffer_keeps_the_last_5000(logging_on: rings.Rings) -> None:
    for n in range(5100):
        log.info("record %d", n)
    logging_on.stop()
    records = logging_on.ring.snapshot()
    assert len(records) == rings.RING_SIZE
    assert records[0].message == "record 100"
    assert records[-1].message == "record 5099"


def test_activity_model_follows_new_records(logging_on: rings.Rings, qtbot: QtBot) -> None:
    model = logging_on.model()
    log.warning("first")
    qtbot.waitUntil(lambda: model.rowCount() == 1)
    assert model.record(0).message == "first"
    assert model.data(model.index(0, 1)) == "Warning"
    assert model.data(model.index(0, 2)) == "first"
    assert rings.bundle_file_name(0).startswith("Verdra support bundle ")


def test_the_listener_thread_survives_the_rings_that_started_it(tmp_path: Path) -> None:
    """CI run 37110221102: a Rings dropped without stop() let Qt delete its bridge while the
    listener thread still emitted through it ("Signal source has been deleted")."""
    import gc
    import threading

    errors: list[BaseException | None] = []
    previous = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value)
    try:
        logs = rings.Rings(tmp_path)
        logs.start()
        listener = logs._listener  # noqa: SLF001 - the thread outliving its owner is the test
        assert listener is not None
        del logs
        gc.collect()
        logging.getLogger("verdra.test").warning("after the Rings is gone")
        listener.stop()  # flushes the queue through the handlers on the listener thread
    finally:
        threading.excepthook = previous
        logger = logging.getLogger(rings.LOGGER_NAME)
        logger.handlers.clear()  # the dropped Rings never gave the logger back
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
    assert errors == []


def test_stop_gives_the_logger_back_as_it_was(tmp_path: Path) -> None:
    """A level left behind decided which records a later test counted (S-14 test, run order)."""
    logger = logging.getLogger(rings.LOGGER_NAME)
    before = (logger.level, logger.propagate, list(logger.handlers))
    logs = rings.Rings(tmp_path)
    logs.hold()
    logs.start(detailed=True)
    assert (logger.level, logger.propagate) == (logging.DEBUG, False)
    logs.stop()
    assert (logger.level, logger.propagate, list(logger.handlers)) == before
    logs.set_detailed(False)  # after stop: remembered, the logger untouched
    assert logger.level == before[0]
    assert not logs.detailed
