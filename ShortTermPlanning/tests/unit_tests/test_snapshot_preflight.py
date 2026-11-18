"""Snapshot readiness diagnostics must detect the real Jenkins failure without leaking endpoints."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
import requests

path = Path(__file__).resolve().parents[2] / 'extras' / 'snapshot_preflight.py'
spec = importlib.util.spec_from_file_location('snapshot_preflight', path)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
STAMP = '2024-12-31T11:00:00Z'
BASE = 'http://hidden-user:hidden-password@private-host:5016'


@pytest.fixture
def setup(monkeypatch):
    for key, value in dict(REST_URL=BASE, SNAPSHOT_VERSION=STAMP, SCENARIO_4_5_EQUIPMENT='7',
                           SCENARIO_6_EQUIPMENT='7', SCENARIO_7_EQUIPMENTS='6 7',
                           SCENARIO_8_EQUIPMENTS='6 7', SCENARIO_8_ORDER_ID='order7').items():
        monkeypatch.setenv(key, value)
    site = {'equipment': [{'id': 6, 'name_short': 'FIN01'}, {'id': 7, 'name_short': 'FIN02'}]}
    snapshot = dict(timestamp=STAMP,
                    orders=[{'id': f'order{i}', 'allowed_equipment': [6 if i == 6 else 7]} for i in (6, 7, 8)],
                    material=[{'id': f'mat{i}', 'order': f'order{i}', 'current_equipment': 6 if i == 6 else 7} for i in (6, 7, 8)])
    calls = []
    responses = {}
    def get(url, **kwargs):
        endpoint = unquote(url.removeprefix(BASE))
        calls.append((endpoint, kwargs))
        if endpoint in responses:
            return responses[endpoint]
        if endpoint == '/site':
            data = site
        elif endpoint.startswith('/snapshots/'):
            data = snapshot
        else:
            eq = int(endpoint.split('/')[3])
            data = {'snapshot_id': STAMP, 'targets': {'equipment': eq}}
        return SimpleNamespace(ok=True, status_code=200, json=lambda: data)
    return SimpleNamespace(get=get, site=site, snapshot=snapshot, calls=calls, responses=responses)


def test_valid_snapshot_and_selected_orders_and_initial_costs_pass(setup, capsys):
    assert preflight.main(setup.get) == 0
    assert 'PASS:' in capsys.readouterr().out
    assert [path for path, _ in setup.calls] == ['/site', '/snapshots/' + STAMP,
        '/costs/status/6/' + STAMP, '/costs/status/7/' + STAMP]
    assert all(kwargs['timeout'] == (4, 30) for _, kwargs in setup.calls)


def test_missing_snapshot_http_500_is_identified_without_sensitive_details(setup, capsys):
    setup.responses['/snapshots/' + STAMP] = SimpleNamespace(ok=False, status_code=500, text=BASE)
    assert preflight.main(setup.get) == 1
    output = capsys.readouterr().out
    assert 'SNAPSHOT: HTTP_500' in output
    for secret in (BASE, 'hidden-password', 'private-host'):
        assert secret not in output
    assert len(setup.calls) == 2


def test_wrong_profile_is_detected_before_loading_any_snapshot(setup, capsys):
    setup.site['equipment'][1]['name_short'] = 'NWW04'
    assert preflight.main(setup.get) == 1
    assert 'PROFILE_MISMATCH' in capsys.readouterr().out
    assert len(setup.calls) == 1


def test_a_silently_substituted_snapshot_is_rejected(setup, capsys):
    setup.snapshot['timestamp'] = '2024-12-30T23:00:00Z'
    assert preflight.main(setup.get) == 1
    assert 'SNAPSHOT_MISMATCH' in capsys.readouterr().out


def test_expected_order_must_be_in_actual_selection(setup, monkeypatch, capsys):
    monkeypatch.setenv('SCENARIO_8_ORDER_ID', '1193611')
    assert preflight.main(setup.get) == 1
    assert 'EXPECTED_ORDER_NOT_SELECTED' in capsys.readouterr().out


def test_no_candidate_material_fails_before_agent_launch(setup, capsys):
    setup.snapshot['material'] = []
    assert preflight.main(setup.get) == 1
    assert 'NO_ELIGIBLE_MATERIAL' in capsys.readouterr().out


def test_missing_distinct_order_for_scenario_6_is_rejected(setup, capsys):
    setup.snapshot['material'].pop()
    assert preflight.main(setup.get) == 1
    assert 'SCENARIO_6: INSUFFICIENT_DISTINCT_ORDERS' in capsys.readouterr().out


def test_broken_initial_cost_provider_is_detected(setup, capsys):
    setup.responses['/costs/status/7/' + STAMP] = SimpleNamespace(ok=False, status_code=503)
    assert preflight.main(setup.get) == 1
    assert 'COST_STATUS_7: HTTP_503' in capsys.readouterr().out


def test_unreachable_backend_does_not_leak_exception_url(setup, capsys):
    def fail(*args, **kwargs):
        raise requests.ConnectionError(BASE)
    assert preflight.main(fail) == 1
    output = capsys.readouterr().out
    assert 'REQUEST_FAILED' in output
    assert BASE not in output


@pytest.mark.parametrize('stamp', ['', 'not-a-date', '2024-12-31T11:00:00'])
def test_invalid_snapshot_configuration_fails_without_http(setup, monkeypatch, capsys, stamp):
    monkeypatch.setenv('SNAPSHOT_VERSION', stamp)
    assert preflight.main(setup.get) == 1
    assert 'CONFIG_ERROR' in capsys.readouterr().out
    assert not setup.calls


def test_material_referencing_absent_order_is_rejected(setup, capsys):
    setup.snapshot['orders'].pop()
    assert preflight.main(setup.get) == 1
    assert 'SNAPSHOT_INVALID' in capsys.readouterr().out
