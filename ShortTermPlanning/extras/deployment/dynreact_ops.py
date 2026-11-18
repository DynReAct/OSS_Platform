#!/usr/bin/env python3
"""Profile-specific DynReAct deployment and Registry V2 maintenance (stdlib only)."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ACCEPT = ', '.join(('application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json'))


def read_env(path):
    values = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'): continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key):
            raise ValueError(f'Invalid Docker env-file entry at line {number}')
        if value.startswith(('"', "'")):
            raise ValueError('Use literal Docker KEY=value syntax without shell quotes')
        values[key] = value
    return values


def configuration(profile):
    if profile not in ('ras','oss'): raise ValueError('profile must be ras or oss')
    directory = Path(os.getenv('DYNREACT_CONFIG_DIR','/etc/dynreact'))
    path = directory/f'agents-{profile}.env'
    env = read_env(path)
    print(f'Configuration: {path}',file=sys.stderr)
    declared = env.get('DYNREACT_PROFILE', profile)
    if declared != profile: raise ValueError('Profile and env-file disagree')
    repository = env.get('IMAGE_NAME',f'dynreact-{profile}-shortterm')
    if not re.fullmatch(r'[a-z0-9]+(?:[._/-][a-z0-9]+)*', repository):
        raise ValueError('Invalid IMAGE_NAME repository')
    registry = env.get('LOCAL_REGISTRY','192.168.110.176:5000/').rstrip('/')
    if '://' in registry or not registry or '/' in registry:
        raise ValueError('LOCAL_REGISTRY must be host[:port]/; put repository paths in IMAGE_NAME')
    endpoints = list(dict.fromkeys(v.strip() for v in env.get(f'{profile.upper()}_DOCKER_WORKERS','').split(',') if v.strip()))
    for endpoint in endpoints:
        u = urlsplit(endpoint)
        if (u.scheme != 'ssh' or not u.hostname or u.username != profile or u.password
                or u.path not in ('','/') or u.query or u.fragment):
            raise ValueError(f'Use ssh://{profile}@host[:port] worker endpoints')
    ssh_dir = Path(env.get('DYNREACT_SSH_DIR',str(directory/f'ssh-{profile}')))
    return path, env, registry, repository, endpoints, ssh_dir


def run(args, *, stdin=None, capture=False):
    result = subprocess.run(args, input=stdin, text=True, capture_output=capture, timeout=300)
    if result.returncode:
        # Do not echo env files, credentials, or arbitrary remote output.
        raise RuntimeError(f'Command failed ({result.returncode}): {args[0]} {args[1] if len(args)>1 else ""}')
    return result.stdout.strip() if capture else None


def inspect_image(image):
    return json.loads(run(['docker','image','inspect',image],capture=True))[0]


def ssh_command(image, ssh_dir, endpoint, command, stdin=None, capture=False):
    u = urlsplit(endpoint)
    args = ['docker','run','--rm','-i','--network','host','--user','appuser',
        '-v',f'{ssh_dir}:/home/appuser/.ssh:ro','--entrypoint','ssh', image,
        '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes', '-o','IdentitiesOnly=yes',
        '-o','ConnectTimeout=10']
    if u.port: args += ['-p',str(u.port)]
    args += [f'{u.username}@{u.hostname}', shlex.join(command)]
    return run(args,stdin=stdin,capture=capture)


CLEAN_IMAGES = r'''
set -eu
repository=$1
keep=$2
ids=$(docker ps -aq)
used=$(if [ -n "$ids" ]; then docker inspect --format '{{.Image}}' $ids; fi)
docker image ls --no-trunc --format '{{.Repository}} {{.Tag}} {{.ID}}' "$repository" |
while read -r repo tag ident; do
    [ "$repo" = "$repository" ] || continue
    [ "$tag" != '<none>' ] || continue
    [ "$ident" != "$keep" ] || continue
    if printf '%s\n' "$used" | grep -Fxq "$ident"; then
        echo "Keeping in-use image $repo:$tag"
    else
        docker image rm "$repo:$tag"
    fi
done
'''


def deploy(profile, revision):
    path, env, registry, repository, workers, ssh_dir = configuration(profile)
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',revision):
        raise ValueError('Revision must be a valid existing registry tag')
    if not workers: raise ValueError(f'{profile.upper()}_DOCKER_WORKERS is required')
    if not env.get('KAFKA_IP'): raise ValueError('KAFKA_IP is required by the parent CLI')
    if not (ssh_dir/'known_hosts').is_file() or not any((ssh_dir/k).is_file() for k in ('id_ed25519','id_rsa')):
        raise ValueError(f'Missing SSH key or known_hosts in {ssh_dir}')
    tag = env.get('IMAGE_TAG_TEMPLATE','{revision}').replace('{revision}',revision)
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',tag): raise ValueError('Invalid IMAGE_TAG_TEMPLATE result')
    repo = f'{registry}/{repository}'
    image = f'{repo}:{tag}'
    prefix = env.get('CONTAINER_NAME_PREFIX',f'dynreact-{profile}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',prefix): raise ValueError('Invalid CONTAINER_NAME_PREFIX')
    names = [f'{prefix}-{role}-base' for role in ('log','equipment','material')]
    print(f'Profile={profile}; image={image}; parents=local; workers={",".join(workers)}',flush=True)
    if os.getenv('DYNREACT_DRY_RUN') == '1':
        print(f'Would preload image, verify workers, replace {names}, and clean unused older repository tags.')
        return
    run(['docker','pull',image])
    info = inspect_image(image)
    pinned = next((r for r in info.get('RepoDigests',[]) if r.startswith(repo+'@')),None)
    if not pinned: raise RuntimeError('Cannot pin the pulled image by registry digest')
    run(['docker','run','--rm','--entrypoint','sh',pinned,'-c',
        'command -v ssh >/dev/null && test -f /app/shortterm/dynreact/shortterm/common/remote_pool.py'])
    log_dir = env.get('DYNREACT_HOST_LOG_DIR',f'/var/log/dynreact/{profile}')
    remote_log = env.get('DYNREACT_WORKER_LOG_DIR',f'/home/{profile}/dynreact-logs')
    Path(log_dir).mkdir(parents=True,exist_ok=True)
    for worker in workers:
        ssh_command(pinned,ssh_dir,worker,['docker','info'],capture=True)
        ssh_command(pinned,ssh_dir,worker,['mkdir','-p',remote_log])
        ssh_command(pinned,ssh_dir,worker,['docker','pull',pinned])
        remote_id = ssh_command(pinned,ssh_dir,worker,['docker','image','inspect',pinned,'--format','{{.Id}}'],capture=True)
        if remote_id != info['Id']: raise RuntimeError(f'Worker image differs: {worker}; check CPU architecture')
        ssh_command(pinned,ssh_dir,worker,['docker','tag',pinned,image])
    # Preflight all existing parent names before removing any of them.
    existing = set(run(['docker','ps','-a','--format','{{.Names}}'],capture=True).splitlines())
    for name in names:
        if name in existing:
            labels = json.loads(run(['docker','inspect','--format','{{json .Config.Labels}}',name],capture=True)) or {}
            if labels.get('dynreact.profile') != profile or labels.get('dynreact.kind') != 'base':
                raise RuntimeError(f'Refusing to replace unmanaged or other-profile container {name}')
    overrides = dict(DYNREACT_PROFILE=profile,CONTAINER_NAME_PREFIX=prefix,LOCAL_REGISTRY=registry+'/',
        IMAGE_NAME=repository, IMAGE_TAG=tag, DYNREACT_SHORTTERM_IMAGE=pinned,
        LOG_FILE_PATH='/var/log/dynreact-logs',DYNREACT_WORKER_LOG_DIR=remote_log,
        DOCKER_NETWORK=env.get('DOCKER_NETWORK','host'),
        KAFKA_TOPIC_PREFIX=env.get('KAFKA_TOPIC_PREFIX',f'Dynreact_{profile.upper()}'),
        TOPIC_GEN=env.get('TOPIC_GEN',f'Dynreact-{profile.upper()}-Gen'),
        TOPIC_CALLBACK=env.get('TOPIC_CALLBACK',f'Dynreact-{profile.upper()}-Callback'))
    for role,name in zip(('log','equipment','material'),names):
        if name in existing: run(['docker','rm','-f',name])
        args=['docker','run','-d','--env-file',str(path),'--name',name,'--restart','unless-stopped',
            '--network',overrides['DOCKER_NETWORK'],'--entrypoint','/usr/local/bin/entrypoint.sh',
            '--label',f'dynreact.profile={profile}','--label','dynreact.kind=base',
            '-v','/var/run/docker.sock:/var/run/docker.sock:rw',
            '-v',f'{log_dir}:/var/log/dynreact-logs:rw','-v',f'{ssh_dir}:/home/appuser/.ssh:ro']
        for key,value in overrides.items(): args += ['-e',f'{key}={value}']
        args += [pinned,'python','-m','dynreact.shortterm.agents',role,'base','-k',env['KAFKA_IP'],'-v','1']
        run(args)
        state = run(['docker','inspect','--format','{{.State.Running}}',name],capture=True)
        if state != 'true': raise RuntimeError(f'Parent exited: inspect docker logs {name}')
    for worker in workers:
        ssh_command(pinned,ssh_dir,worker,['sh','-s','--',repo,info['Id']],stdin=CLEAN_IMAGES)
    run(['sh','-s','--',repo,info['Id']],stdin=CLEAN_IMAGES)
    print('Parents started; verify docker logs and a small auction before production load.')


def parse_created(*values):
    """Parse OCI/Docker timestamps on Python versions with microsecond-only ISO support."""
    for text in values:
        if not isinstance(text,str): continue
        text=text.strip()
        text=re.sub(r'(\d{2}:\d{2}:\d{2})\.(\d+)',
                    lambda m:m.group(1)+'.'+m.group(2)[:6].ljust(6,'0'),text)
        if text.endswith('Z'):text=text[:-1]+'+00:00'
        try:
            value=datetime.fromisoformat(text)
            if value.tzinfo is not None:return value.astimezone(timezone.utc)
        except (ValueError,TypeError):continue
    return None


def host_ssh_command(ssh_dir,endpoint,command,capture=False):
    """Use the deployment host's SSH client when no parent/helper image is available."""
    if not shutil.which('ssh'):
        raise RuntimeError('Install the host OpenSSH client or configure REGISTRY_SSH_IMAGE')
    key=next((ssh_dir/name for name in ('id_ed25519','id_rsa')
              if (ssh_dir/name).is_file() and os.access(ssh_dir/name,os.R_OK)),None)
    hosts=ssh_dir/'known_hosts'
    if key is None or not hosts.is_file() or not os.access(hosts,os.R_OK):
        raise RuntimeError(f'Host SSH needs a readable private key and known_hosts in {ssh_dir}; '
                           'run as an authorized user or configure REGISTRY_SSH_IMAGE')
    u=urlsplit(endpoint)
    args=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
          '-o','IdentitiesOnly=yes','-o','ConnectTimeout=10',
          '-o',f'UserKnownHostsFile={hosts}','-i',str(key)]
    if (ssh_dir/'config').is_file():args[1:1]=['-F',str(ssh_dir/'config')]
    if u.port:args+=['-p',str(u.port)]
    args += [f'{u.username}@{u.hostname}',shlex.join(command)]
    return run(args,capture=capture)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        # Never forward registry credentials to another origin.
        raise RuntimeError('Registry redirect refused; configure the final registry URL')


class Registry:
    def __init__(self,env,registry,repository):
        self.base=env.get('REGISTRY_URL',f'http://{registry}').rstrip('/')
        u=urlsplit(self.base)
        if u.scheme not in ('http','https') or not u.netloc or u.username or u.path not in ('','/'):
            raise ValueError('REGISTRY_URL must be an HTTP(S) origin')
        self.repo=repository
        self.headers={'Accept':ACCEPT}
        token=os.getenv('DYNREACT_REGISTRY_TOKEN')
        user=os.getenv('DYNREACT_REGISTRY_USER')
        password=os.getenv('DYNREACT_REGISTRY_PASSWORD')
        if token: self.headers['Authorization']='Bearer '+token
        elif user and password:
            self.headers['Authorization']='Basic '+base64.b64encode(f'{user}:{password}'.encode()).decode()
        self.opener=build_opener(NoRedirect)
        self.cache={}

    def request(self,path,method='GET'):
        url=urljoin(self.base+'/',path)
        if urlsplit(url).netloc!=urlsplit(self.base).netloc or urlsplit(url).scheme!=urlsplit(self.base).scheme:
            raise ValueError('Cross-origin registry request refused')
        with self.opener.open(Request(url,headers=self.headers,method=method),timeout=30) as response:
            raw=response.read()
            return (json.loads(raw) if raw else None),dict(response.headers.items())

    def tags(self):
        path=f'/v2/{self.repo}/tags/list?n=100'
        values=[];seen=set()
        while path:
            if path in seen:raise ValueError('Registry pagination loop')
            seen.add(path)
            body,headers=self.request(path)
            values.extend(body.get('tags') or [])
            link=next((v for k,v in headers.items() if k.lower()=='link'),'')
            match=re.search(r'<([^>]+)>;\s*rel="?next"?',link)
            path=match.group(1) if match else None
            if path and urlsplit(path).path != f'/v2/{self.repo}/tags/list':
                raise ValueError('Unexpected registry pagination path')
        return sorted(set(values))

    def manifest(self,reference):
        if reference in self.cache:return self.cache[reference]
        body,headers=self.request(f'/v2/{self.repo}/manifests/{quote(reference,safe=":")}')
        digest=next((v for k,v in headers.items() if k.lower()=='docker-content-digest'),None)
        if not digest or not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
            raise ValueError('Missing/unsupported manifest digest')
        if 'manifests' in body:
            children=[self.manifest(row['digest']) for row in body['manifests']]
            dates=[c['created'] for c in children]
            created=max(dates) if dates and all(dates) else None
            configs=set().union(*(c['configs'] for c in children)) if children else set()
            references={c['digest'] for c in children}
            for child in children:references.update(child['references'])
        else:
            config=body.get('config',{}).get('digest')
            if not config or not re.fullmatch(r'sha256:[0-9a-f]{64}',config):
                raise ValueError('Manifest lacks a valid config digest')
            data,_=self.request(f'/v2/{self.repo}/blobs/{config}')
            created=parse_created(data.get('created'),
                ((data.get('config') or {}).get('Labels') or {}).get('org.opencontainers.image.created'))
            configs={config};references=set()
        result=dict(digest=digest,created=created,configs=configs,references=references)
        self.cache[reference]=result
        return result

    def inventory(self):
        return [(tag,self.manifest(tag)) for tag in self.tags()]


def registry_action(action,profile,days=None):
    _,env,registry,repo,workers,ssh_dir=configuration(profile)
    registry_api=Registry(env,registry,repo)
    inventory=registry_api.inventory()
    now=datetime.now(timezone.utc)
    for tag,item in inventory:
        date=item['created'].isoformat() if item['created'] else 'UNKNOWN'
        print(f'{tag}\t{date}\t{item["digest"]}')
    if action=='list':return
    if not re.fullmatch(r'\d+',days or ''): raise ValueError('X must be a nonnegative integer number of days')
    cutoff=now-timedelta(days=int(days))
    protected={tag.strip() for tag in env.get('REGISTRY_PROTECTED_TAGS','latest,stable,production').split(',') if tag.strip()}
    # A digest is one deletion unit: every alias must be old and unprotected.
    blocked={item['digest'] for tag,item in inventory
             if tag in protected or not item['created'] or item['created']>=cutoff}
    # Never remove a tagged platform manifest referenced by an index, even an old index.
    referenced=set().union(*(item['references'] for _,item in inventory)) if inventory else set()
    candidates={item['digest']:item for _,item in inventory
                if item['digest'] not in blocked|referenced}
    for digest in candidates:
        aliases=[tag for tag,item in inventory if item['digest']==digest]
        print(f'CANDIDATE {digest} tags={",".join(aliases)}')
    if not candidates:
        print('No eligible manifests: nothing to delete; no Docker/SSH deployment checks needed.')
        return
    if os.getenv('DYNREACT_APPLY')!='1':
        print('Preview only. Set DYNREACT_APPLY=1 to delete these manifests. No automatic garbage collection.')
        return
    if not workers:raise ValueError('Configured workers are required to check deployed images before deletion')
    # A local copy of the profile image is used only as an SSH client, with the same identity as parents.
    helper=env.get('REGISTRY_SSH_IMAGE')
    if not helper:
        parents=run(['docker','ps','-a','--filter',f'label=dynreact.profile={profile}',
            '--filter','label=dynreact.kind=base','--format','{{.Names}}'],capture=True).splitlines()
        if parents:
            helper=run(['docker','inspect','--format','{{.Config.Image}}',parents[0]],capture=True)
        else:
            print('No profile parents here: using host SSH with the profile credentials.')
    collect='set -e; ids=$(docker ps -aq); if [ -n "$ids" ]; then docker inspect --format \'{{.Image}}\' $ids; fi'
    used=set(run(['sh','-c',collect],capture=True).splitlines())
    for worker in workers:
        if helper:
            remote=ssh_command(helper,ssh_dir,worker,['sh','-c',collect],capture=True)
        else:
            remote=host_ssh_command(ssh_dir,worker,['sh','-c',collect],capture=True)
        used.update(remote.splitlines())
    # Recheck aliases immediately before deletion, protecting concurrent retagging.
    registry_api.cache.clear()
    refreshed=registry_api.inventory()
    for digest,item in candidates.items():
        if item['configs'] & used:
            print(f'KEEP deployed image {digest}');continue
        aliases=[(tag,m) for tag,m in refreshed if m['digest']==digest]
        if not aliases or any(tag in protected or not m['created'] or m['created']>=cutoff for tag,m in aliases):
            print(f'KEEP changed/protected image {digest}');continue
        registry_api.request(f'/v2/{repo}/manifests/{digest}',method='DELETE')
        print(f'DELETED {digest}')


def main():
    if len(sys.argv)<3:raise ValueError('Usage: deploy|list|prune ras|oss [revision|days]')
    action,profile=sys.argv[1:3]
    if action=='deploy' and len(sys.argv)==4:deploy(profile,sys.argv[3])
    elif action=='list' and len(sys.argv)==3:registry_action(action,profile)
    elif action=='prune' and len(sys.argv)==4:registry_action(action,profile,sys.argv[3])
    else:raise ValueError('Invalid command or number of parameters')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        sys.exit(1)
