"""Read-only network diagnostics preserve endpoint masking."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import errno
import pytest

spec=importlib.util.spec_from_file_location('preflight',Path(__file__).resolve().parents[2]/'extras/kafka_preflight.py')
preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)


def test_parser_supports_multiple_endpoints_and_bracketed_ipv6():
    assert preflight.endpoints('broker:9092,[::1]:9093')==[('broker',9092),('::1',9093)]


@pytest.mark.parametrize('value',['','http://broker:9092','broker','broker:0','user@broker:9092'])
def test_invalid_endpoint_does_not_print_its_value(monkeypatch,capsys,value):
    monkeypatch.setenv('KAFKA_IP',value)
    assert preflight.main()==1
    output=capsys.readouterr().out
    if value:assert value not in output


def test_no_route_is_classified_without_leaking_endpoint(monkeypatch,capsys):
    monkeypatch.setenv('KAFKA_IP','private-broker:9092')
    monkeypatch.setattr(preflight.socket,'getaddrinfo',lambda *a,**kw:[])
    def fail(*a,**kw):raise OSError(errno.EHOSTUNREACH,'private-broker')
    monkeypatch.setattr(preflight.socket,'create_connection',fail)
    assert preflight.main()==1
    output=capsys.readouterr().out
    assert 'HOST_UNREACHABLE' in output and 'private-broker' not in output


def test_bootstrap_success_and_advertised_failure_are_distinguished(monkeypatch,capsys):
    monkeypatch.setenv('KAFKA_IP','private-broker:9092')
    calls=[]
    def probe(host,port,label):calls.append(label);return label.startswith('BOOTSTRAP')
    monkeypatch.setattr(preflight,'probe',probe)
    admin=MagicMock();admin.list_topics.return_value=SimpleNamespace(brokers={1:SimpleNamespace(host='advertised-private',port=9092)})
    assert preflight.main(lambda _:admin)==1
    assert calls==['BOOTSTRAP[1]','ADVERTISED[1]']
    output=capsys.readouterr().out
    assert 'advertised.listeners' in output and 'advertised-private' not in output
    admin.list_topics.assert_called_once_with(timeout=10)
    admin.create_topics.assert_not_called();admin.delete_topics.assert_not_called()


def test_success_uses_read_only_metadata_and_no_values(monkeypatch,capsys):
    monkeypatch.setenv('KAFKA_IP','private-broker:9092')
    monkeypatch.setattr(preflight,'probe',lambda *a:True)
    admin=MagicMock();admin.list_topics.return_value=SimpleNamespace(brokers={1:SimpleNamespace(host='private',port=9092)})
    assert preflight.main(lambda _:admin)==0
    output=capsys.readouterr().out
    assert 'PASS' in output and 'private' not in output
