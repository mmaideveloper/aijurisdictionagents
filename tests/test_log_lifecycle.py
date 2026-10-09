import os
from pathlib import Path

import pytest

from scripts.server.log_lifecycle import prune_logs, publish_latest


@pytest.mark.skipif(os.name == "nt", reason="Native symlink tests run on Linux/Docker")
def test_publish_is_relative_and_survives_log_only_mount(tmp_path):
    log = tmp_path / "laws-collector-daily-20261009T000000Z.log"
    log.write_text("synthetic event\n")
    latest = tmp_path / "laws-collector-daily-latest.log"
    publish_latest(log, latest)
    assert os.readlink(latest) == log.name
    assert latest.read_text() == "synthetic event\n"
    log2 = tmp_path / "laws-collector-daily-20261010T000000Z.log"
    log2.write_text("next event\n")
    publish_latest(log2, latest)
    assert latest.read_text() == "next event\n"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="Native symlink tests run on Linux/Docker")
def test_retention_repairs_alias_before_deleting_old_target(tmp_path):
    now = 2_000_000_000
    old = tmp_path / "laws-collector-daily-old.log"
    old.write_text("expired synthetic")
    os.utime(old, (now - 30 * 86400, now - 30 * 86400))
    new = tmp_path / "laws-collector-daily-new.log"
    new.write_text("current synthetic")
    os.utime(new, (now, now))
    latest = tmp_path / "laws-collector-daily-latest.log"
    publish_latest(old, latest)
    assert prune_logs(tmp_path, retention_days=7, now=now) == 1
    assert not old.exists()
    assert latest.read_text() == "current synthetic"
    assert os.readlink(latest) == new.name


@pytest.mark.skipif(os.name == "nt", reason="Native symlink tests run on Linux/Docker")
def test_dangling_alias_removed_without_fabricating_a_log(tmp_path):
    latest = tmp_path / "laws-collector-daily-latest.log"
    latest.symlink_to("missing.log")
    prune_logs(tmp_path, retention_days=7)
    assert not latest.is_symlink()
    assert not list(tmp_path.glob("*.log"))


@pytest.mark.skipif(os.name == "nt", reason="Native symlink tests run on Linux/Docker")
def test_outside_directory_target_is_never_deleted(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("must survive")
    latest = logs / "laws-collector-daily-latest.log"
    latest.symlink_to(outside)
    prune_logs(logs, retention_days=7)
    assert outside.read_text() == "must survive"
    assert not latest.is_symlink()
    with pytest.raises(ValueError):
        publish_latest(outside, latest)


def test_existing_regular_latest_file_is_preserved(tmp_path):
    log = tmp_path / "actual.log"
    log.write_text("source")
    latest = tmp_path / "service-latest.log"
    latest.write_text("real log")
    with pytest.raises(ValueError):
        publish_latest(log, latest)
    assert latest.read_text() == "real log"


def test_alloy_ingests_job_files_without_alias_or_container_copy():
    config = (Path(__file__).resolve().parents[1] / "Deployment/monitoring/alloy/config.alloy").read_text()
    assert '__path_exclude__ = "/srv/jurisdigta/runs/logs/*-latest.log"' in config
    assert 'regex         = ".*/court-decision-collector\\\\.log"' in config
    assert "loki.source.docker" in config
