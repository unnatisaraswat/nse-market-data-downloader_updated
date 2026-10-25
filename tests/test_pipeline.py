import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from nse_downloader.acquisition import fetch_json, AcquisitionError
from nse_downloader.pipeline import run
from nse_downloader.validation import normalize, deduplicate, ValidationError

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def config():
    cfg = json.loads((ROOT / "config/datasets.json").read_text())
    for spec in cfg["datasets"].values():
        for source in spec["sources"]:
            source["fixture"] = str((ROOT / "config" / source["fixture"]).resolve())
    return cfg


def test_all_four_outputs_and_repeat(config, tmp_path):
    names = list(config["datasets"])
    assert run(config, names, tmp_path, demo=True) == []
    paths = sorted(tmp_path.glob("*.csv"))
    assert len(paths) == 4
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    assert run(config, names, tmp_path, demo=True) == []
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}


def test_failure_isolation(config, tmp_path):
    names = list(config["datasets"])
    config["datasets"][names[0]]["sources"][0]["fixture"] = "missing.json"
    assert run(config, names, tmp_path, demo=True) == [names[0]]
    assert len(list(tmp_path.glob("*.csv"))) == 3

@pytest.mark.parametrize("payload", [{}, {"data": []}, {"data": "bad"}, {"data": [{}], "trading_date": "2026-01-02"}])
def test_bad_payload(config, payload):
    name = next(iter(config["datasets"]))
    spec = config["datasets"][name]
    with pytest.raises(ValidationError):
        normalize(payload, spec["sources"][0], spec, name)


def test_duplicate_conflict():
    assert deduplicate([{"id":"A", "v":"1"}]*2, ["id"]) == [{"id":"A", "v":"1"}]
    with pytest.raises(ValidationError):
        deduplicate([{"id":"A", "v":"1"}, {"id":"A", "v":"2"}], ["id"])

@pytest.mark.parametrize("status", [401, 403, 404, 302])
def test_http_failure(status):
    session = Mock()
    session.get.return_value.status_code = status
    with pytest.raises(AcquisitionError):
        fetch_json({"url":"https://example.org/feed"}, session=session)
    assert session.get.call_count == 1


def test_network_retry():
    session = Mock()
    session.get.side_effect = requests.Timeout()
    with pytest.raises(AcquisitionError):
        fetch_json({"url":"https://example.org/feed"}, session=session, sleep=lambda _: None)
    assert session.get.call_count == 3


def test_successful_http():
    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.headers = {"Content-Type":"application/json"}
    session.get.return_value.json.return_value = {"data":[1]}
    assert fetch_json({"url":"https://example.org/feed"}, session=session) == {"data":[1]}


def test_html_rejected():
    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.headers = {"Content-Type":"text/html"}
    with pytest.raises(AcquisitionError):
        fetch_json({"url":"https://example.org/feed"}, session=session)


def test_invalid_json():
    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.headers = {"Content-Type":"application/json"}
    session.get.return_value.json.side_effect = ValueError()
    with pytest.raises(AcquisitionError):
        fetch_json({"url":"https://example.org/feed"}, session=session)

@pytest.mark.parametrize("status", [429, 500, 503])
def test_status_retry(status):
    session = Mock()
    session.get.return_value.status_code = status
    session.get.return_value.headers = {}
    with pytest.raises(AcquisitionError):
        fetch_json({"url":"https://example.org/feed"}, session=session, sleep=lambda _:None)
    assert session.get.call_count == 3


def test_stale_date(config, tmp_path):
    names = list(config["datasets"])
    assert run(config, names, tmp_path, demo=True, expected_date="2026-01-03") == names
    assert not list(tmp_path.glob("*.csv"))


def test_permission_required(config, tmp_path):
    names = list(config["datasets"])
    assert run(config, names, tmp_path) == names


def test_invalid_numeric(config):
    name = next(iter(config["datasets"]))
    spec = config["datasets"][name]
    source = spec["sources"][0]
    payload = fetch_json(source, demo=True)
    payload["data"][0]["ltp"] = "NaN"
    with pytest.raises(ValidationError):
        normalize(payload, source, spec, name)
