#!/usr/bin/env python3
"""Read-only Kafka connectivity diagnosis without logging endpoint/credential values."""
import errno
import os
import socket


def endpoints(value):
    if not value or not value.strip():
        raise ValueError('KAFKA_IP is empty')
    result=[]
    for entry in value.split(','):
        entry=entry.strip()
        if '://' in entry or '/' in entry or '@' in entry:
            raise ValueError('KAFKA_IP must contain host:port entries, without URL scheme or credentials')
        if entry.startswith('['):
            host,separator,port=entry[1:].partition(']:')
        else:
            host,separator,port=entry.rpartition(':')
        if not separator or not host or not port.isdigit() or not 1<=int(port)<=65535:
            raise ValueError('KAFKA_IP contains an invalid host:port entry')
        result.append((host,int(port)))
    return result


def probe(host,port,label,timeout=4):
    try:
        socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    except socket.gaierror:
        print(f'{label}: DNS_FAILED (hostname cannot be resolved; value withheld)')
        return False
    print(f'{label}: DNS_OK')
    try:
        with socket.create_connection((host,port),timeout=timeout):pass
    except (TimeoutError,socket.timeout):
        print(f'{label}: TCP_TIMEOUT (check routing/firewall or an unavailable host)')
        return False
    except OSError as exc:
        reason={errno.EHOSTUNREACH:'HOST_UNREACHABLE',errno.ENETUNREACH:'NETWORK_UNREACHABLE',
                errno.ECONNREFUSED:'CONNECTION_REFUSED'}.get(exc.errno,'TCP_ERROR')
        print(f'{label}: {reason} (errno={exc.errno}; endpoint withheld)')
        return False
    print(f'{label}: TCP_OK')
    return True


def main(admin_factory=None):
    raw=os.getenv('KAFKA_IP','')
    try:bootstrap=endpoints(raw)
    except ValueError as exc:
        print('CONFIG_ERROR:',exc)  # Messages contain no input values.
        return 1
    print(f'Kafka preflight: {len(bootstrap)} bootstrap endpoint(s); values are not printed.')
    reachable=[probe(host,port,f'BOOTSTRAP[{i}]') for i,(host,port) in enumerate(bootstrap,1)]
    if not any(reachable):
        print('FAILED: no bootstrap endpoint is reachable. No topics or containers were modified.')
        return 1
    if admin_factory is None:
        from confluent_kafka.admin import AdminClient
        admin_factory=AdminClient
    try:
        admin=admin_factory({'bootstrap.servers':raw,'log_level':0,'socket.timeout.ms':5000,
                             'socket.connection.setup.timeout.ms':5000})
        metadata=admin.list_topics(timeout=10)
    except Exception:
        print('METADATA_FAILED: TCP was reachable but Kafka metadata could not be obtained; '
              'check endpoint, broker health and protocol/authentication configuration.')
        return 1
    brokers=list(metadata.brokers.values())
    if not brokers:
        print('METADATA_FAILED: no advertised brokers returned')
        return 1
    print(f'METADATA_OK: {len(brokers)} advertised broker(s)')
    advertised=[probe(b.host,b.port,f'ADVERTISED[{i}]') for i,b in enumerate(brokers,1)]
    if not all(advertised):
        print('FAILED: advertised brokers are unreachable; check advertised.listeners and network access.')
        return 1
    if not all(reachable):
        print('FAILED: some configured bootstrap endpoints are unreachable; repair the bootstrap list.')
        return 1
    print('PASS: Kafka bootstrap and advertised brokers are reachable. No topics or containers were modified.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
