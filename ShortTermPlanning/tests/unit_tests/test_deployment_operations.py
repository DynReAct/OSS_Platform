"""Offline regression tests: no Docker daemon, SSH connection or registry mutation."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from datetime import datetime,timedelta,timezone

OPS_PATH=Path(__file__).resolve().parents[2]/'extras/deployment/dynreact_ops.py'
spec=importlib.util.spec_from_file_location('dynreact_ops',OPS_PATH)
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
from dynreact.shortterm.common import remote_pool


@pytest.fixture
def config(tmp_path,monkeypatch):
    monkeypatch.setenv('DYNREACT_CONFIG_DIR',str(tmp_path))
    (tmp_path/'agents-oss.env').write_text('OSS_DOCKER_WORKERS=ssh://oss@one,ssh://oss@two\nKAFKA_IP=broker:9092\n')
    ssh=tmp_path/'ssh-oss';ssh.mkdir()
    for name in ('known_hosts','id_ed25519'):(ssh/name).touch()
    return tmp_path


def test_literal_env_file_never_evaluates_shell(tmp_path):
    p=tmp_path/'env';p.write_text('KEY=$(touch /tmp/do-not-execute)\n')
    assert ops.read_env(p)['KEY']=='$(touch /tmp/do-not-execute)'
    p.write_text('export KEY=value\n')
    with pytest.raises(ValueError):ops.read_env(p)


def test_deploy_dry_run_does_not_call_docker(config,monkeypatch):
    monkeypatch.setenv('DYNREACT_DRY_RUN','1')
    call=MagicMock();monkeypatch.setattr(ops,'run',call)
    ops.deploy('oss','abc123');call.assert_not_called()


def test_profiles_cannot_use_each_others_ssh_identity(config):
    (config/'agents-ras.env').write_text('RAS_DOCKER_WORKERS=ssh://oss@one\n')
    with pytest.raises(ValueError,match='ssh://ras'):ops.configuration('ras')


def test_failed_worker_preload_never_removes_parents(config,monkeypatch):
    calls=[]
    monkeypatch.setattr(ops,'run',lambda args,**kw:calls.append(args))
    monkeypatch.setattr(ops,'inspect_image',lambda _:dict(Id='sha256:ID',RepoDigests=['192.168.110.176:5000/dynreact-oss-shortterm@sha256:DIGEST']))
    monkeypatch.setattr(ops,'ssh_command',MagicMock(side_effect=RuntimeError('offline')))
    (config/'agents-oss.env').write_text((config/'agents-oss.env').read_text()+f'DYNREACT_HOST_LOG_DIR={config}/logs\n')
    with pytest.raises(RuntimeError):ops.deploy('oss','abc123')
    assert calls[0]==['docker','pull','192.168.110.176:5000/dynreact-oss-shortterm:abc123']
    assert not any(c[:2]==['docker','rm'] or c[:3]==['docker','run','-d'] for c in calls)


def test_deploy_pins_image_preserves_env_file_and_starts_verbose_one(config,monkeypatch):
    calls=[];pinned='192.168.110.176:5000/dynreact-oss-shortterm@sha256:DIGEST'
    (config/'agents-oss.env').write_text((config/'agents-oss.env').read_text()+f'DYNREACT_HOST_LOG_DIR={config}/logs\n')
    def command(args,**kwargs):
        calls.append(args)
        if args[:3]==['docker','ps','-a']:return ''
        if args[:2]==['docker','inspect']:return 'true'
        return None
    monkeypatch.setattr(ops,'run',command)
    monkeypatch.setattr(ops,'inspect_image',lambda _:dict(Id='ID',RepoDigests=[pinned]))
    monkeypatch.setattr(ops,'ssh_command',lambda *a,**kw:'ID' if a[3][:3]==['docker','image','inspect'] else '')
    ops.deploy('oss','abc123')
    starts=[c for c in calls if c[:3]==['docker','run','-d']]
    assert len(starts)==3
    for c in starts:
        assert c[-2:]==['-v','1']
        assert c[c.index('-k')+1]=='broker:9092'
        assert c[c.index('--env-file')+1]==str(config/'agents-oss.env')
        assert c.index('-v')<c.index(pinned)
        assert f'{config}/ssh-oss:/home/appuser/.ssh:ro' in c
        assert 'DYNREACT_SHORTTERM_IMAGE='+pinned in c
        assert 'python' in c and 'dynreact.shortterm.agents' in c


def inventory():
    old=datetime.now(timezone.utc)-timedelta(days=90)
    def item(digest,created=old):return dict(digest=digest,created=created,configs={'config-'+digest},references=set())
    shared=item('protected')
    child=item('child');index=item('index');index['references']={'child'}
    return [('old',item('old')),('latest',shared),('old-alias',shared),
            ('unknown',item('unknown',None)),('platform',child),('multi',index)]


def test_registry_preview_protects_aliases_unknown_dates_and_index_children(config,monkeypatch,capsys):
    api=MagicMock();api.inventory.return_value=inventory()
    monkeypatch.setattr(ops,'Registry',lambda *a:api)
    ops.registry_action('prune','oss','30')
    api.request.assert_not_called()
    candidates=[line for line in capsys.readouterr().out.splitlines() if line.startswith('CANDIDATE')]
    assert len(candidates)==2
    assert any('old tags=old' in line for line in candidates)
    assert any('index tags=multi' in line for line in candidates)


def test_registry_apply_protects_deployed_configs(config,monkeypatch):
    monkeypatch.setenv('DYNREACT_APPLY','1')
    (config/'agents-oss.env').write_text((config/'agents-oss.env').read_text()+'REGISTRY_SSH_IMAGE=helper\n')
    api=MagicMock();api.inventory.return_value=inventory()
    monkeypatch.setattr(ops,'Registry',lambda *a:api)
    monkeypatch.setattr(ops,'run',lambda *a,**kw:'config-old')
    monkeypatch.setattr(ops,'ssh_command',lambda *a,**kw:'')
    ops.registry_action('prune','oss','30')
    api.request.assert_called_once_with('/v2/dynreact-oss-shortterm/manifests/index',method='DELETE')


def test_registry_unreachable_worker_blocks_every_delete(config,monkeypatch):
    monkeypatch.setenv('DYNREACT_APPLY','1')
    (config/'agents-oss.env').write_text((config/'agents-oss.env').read_text()+'REGISTRY_SSH_IMAGE=helper\n')
    api=MagicMock();api.inventory.return_value=inventory()
    monkeypatch.setattr(ops,'Registry',lambda *a:api)
    monkeypatch.setattr(ops,'run',lambda *a,**kw:'')
    monkeypatch.setattr(ops,'ssh_command',MagicMock(side_effect=RuntimeError('offline')))
    with pytest.raises(RuntimeError):ops.registry_action('prune','oss','30')
    api.request.assert_not_called()


def test_registry_listing_paginates_without_cross_origin_requests():
    api=ops.Registry({},'registry:5000','dynreact-oss-shortterm')
    api.request=MagicMock(side_effect=[({'tags':['a']},{'Link':'</v2/dynreact-oss-shortterm/tags/list?n=1&last=a>; rel="next"'}),({'tags':['b']},{})])
    assert api.tags()==['a','b']
    with pytest.raises(ValueError):api.request=ops.Registry.request.__get__(api);api.request('http://other/secrets')


def pool(monkeypatch):
    clients=[MagicMock(),MagicMock()]
    for c in clients:c.containers.list.return_value=[]
    clients[0].api.containers.return_value=[{'State':'running'}]*3
    clients[1].api.containers.return_value=[{'State':'running'}]
    monkeypatch.setattr(remote_pool.docker,'DockerClient',MagicMock(side_effect=clients))
    return remote_pool.RemoteDockerPool('oss',['ssh://oss@one','ssh://oss@two']),clients


def test_pool_selects_least_active_worker_without_per_container_inspection(monkeypatch):
    p,clients=pool(monkeypatch)
    kwargs=dict(name='oss_MATERIAL_A',labels={'owner':'oss:material'})
    assert p.run(**kwargs)==clients[1].containers.run.return_value
    clients[0].containers.run.assert_not_called()
    clients[1].api.containers.assert_called_once()
    assert kwargs['labels']['dynreact.profile']=='oss'


def test_pool_reconciles_running_retry_and_refuses_unknown_workers(monkeypatch):
    p,clients=pool(monkeypatch)
    old=MagicMock(status='running',labels={'owner':'oss:material'})
    clients[0].containers.list.return_value=[old]
    assert p.run(name='A',labels={'owner':'oss:material'})==old
    clients[1].containers.list.side_effect=RuntimeError('offline')
    with pytest.raises(RuntimeError):p.run(name='A',labels={'owner':'oss:material'})
    for client in clients:client.containers.run.assert_not_called()


def test_registry_reads_config_creation_timestamp_and_unknown_dates():
    api=ops.Registry({},'registry:5000','dynreact-oss-shortterm')
    digest='sha256:'+'a'*64;config='sha256:'+'b'*64
    api.request=MagicMock(side_effect=[({'config':{'digest':config}},{'Docker-Content-Digest':digest}),
                                      ({'created':'2026-01-01T00:00:00Z'}, {})])
    item=api.manifest('old')
    assert item['created']==datetime(2026,1,1,tzinfo=timezone.utc)
    assert item['configs']=={config}
    api.cache.clear()
    api.request=MagicMock(side_effect=[({'config':{'digest':config}},{'Docker-Content-Digest':digest}),
                                      ({'created':'2026-01-01T00:00:00'}, {})])
    assert api.manifest('old')['created'] is None


def test_registry_multiarch_date_requires_every_platform_to_have_a_date():
    api=ops.Registry({},'registry:5000','dynreact-oss-shortterm')
    index='sha256:'+'a'*64;child='sha256:'+'b'*64;config='sha256:'+'c'*64
    api.request=MagicMock(side_effect=[({'manifests':[{'digest':child}]},{'Docker-Content-Digest':index}),
        ({'config':{'digest':config}},{'Docker-Content-Digest':child}),({'config':None},{})])
    item=api.manifest('latest')
    assert item['created'] is None and child in item['references'] and config in item['configs']


def test_worker_limit_fails_without_creating_on_another_unknown_destination(monkeypatch):
    monkeypatch.setenv('DYNREACT_WORKER_LIMIT','1')
    p,clients=pool(monkeypatch)
    with pytest.raises(RuntimeError,match='advisory replica limit'):
        p.run(name='NEW',labels={'owner':'oss:material'})
    for c in clients:c.containers.run.assert_not_called()


def test_nanosecond_timestamps_are_normalized_and_invalid_primary_uses_label():
    assert ops.parse_created('2026-08-28T21:33:02.090628334+02:00') == datetime(
        2026,8,28,19,33,2,90628,tzinfo=timezone.utc)
    assert ops.parse_created('invalid','2026-08-28T19:30:07Z') == datetime(
        2026,8,28,19,30,7,tzinfo=timezone.utc)
    assert ops.parse_created('2026-08-28T21:33:02') is None


def test_no_candidates_exits_before_docker_or_ssh_checks(config,monkeypatch):
    monkeypatch.setenv('DYNREACT_APPLY','1')
    api=MagicMock();api.inventory.return_value=[('unknown',dict(digest='D',created=None,references=set(),configs=set()))]
    monkeypatch.setattr(ops,'Registry',lambda *a:api)
    commands=MagicMock();monkeypatch.setattr(ops,'run',commands)
    ops.registry_action('prune','oss','30')
    commands.assert_not_called();api.request.assert_not_called()


def test_no_local_parents_uses_host_ssh_and_still_protects_deployed_images(config,monkeypatch):
    monkeypatch.setenv('DYNREACT_APPLY','1')
    api=MagicMock();api.inventory.return_value=inventory()
    monkeypatch.setattr(ops,'Registry',lambda *a:api)
    monkeypatch.setattr(ops,'run',lambda *a,**kw:'')
    native=MagicMock(return_value='config-old')
    monkeypatch.setattr(ops,'host_ssh_command',native)
    container=MagicMock();monkeypatch.setattr(ops,'ssh_command',container)
    ops.registry_action('prune','oss','30')
    assert native.call_count==2
    container.assert_not_called()
    api.request.assert_called_once_with('/v2/dynreact-oss-shortterm/manifests/index',method='DELETE')


def test_configuration_uses_agents_profile_file_even_if_old_file_exists(config):
    (config/'oss.env').write_text('OSS_DOCKER_WORKERS=ssh://oss@wrong-host\n')
    path,env,registry,repo,workers,ssh_dir=ops.configuration('oss')
    assert path==config/'agents-oss.env'
    assert workers==['ssh://oss@one','ssh://oss@two']
