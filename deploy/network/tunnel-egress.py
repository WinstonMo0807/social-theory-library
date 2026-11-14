#!/usr/bin/env python3
"""Route only Cloudflare Tunnel edge ranges through the existing NAS gateway.

No proxy credentials, application data, DNS overrides or public listeners.
The direct path stays the default. Loss of the optional path latches direct
until an operator runs --retry or the NAS reboots; this avoids route flapping.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

TUNNEL = 'social-science-library-cloudflared-1'
GATEWAY = 'mihomo-gateway'
NETWORK = 'stl_tunnel_egress'
FALLBACK = 'stl-tunnel-direct-fallback'
FRONT = 'social-science-library_public_front'
EDGE_RANGES = ('198.41.192.0/24', '198.41.200.0/24')
ROUTE_PROTOCOL = '199'
STATE = Path('/run/stl-tunnel-egress/state.json')


def decision(state, gateway_running, connections, hkg_locations, now):
    if not gateway_running:
        if not state.get('applied_at') and state.get('mode') != 'direct':
            return 'waiting', 'gateway-starting'
        return 'direct', 'gateway-unavailable'
    if state.get('mode') == 'direct':
        return 'direct', state.get('reason', 'direct-latched')
    if now - state.get('applied_at', now) < 60:
        return 'hkg', 'connecting'
    if connections >= 2 and hkg_locations >= 2:
        return 'hkg', 'healthy'
    if state.get('failures', 0) >= 2:
        return 'direct', 'edge-connections-unhealthy'
    return 'hkg', 'checking-connections'


def run(args, timeout=8):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Docker command arguments/configuration may contain private fields.
        raise RuntimeError('Network operation failed: ' + args[0])
    return result.stdout


def inspect(name):
    try:
        return json.loads(run(['docker', 'inspect', name]))[0]
    except (RuntimeError, IndexError):
        return None


def routes(pid, cidr):
    return json.loads(run(['nsenter', '-t', str(pid), '-n', 'ip', '-j', 'route', 'show', 'exact', cidr]))


def direct(pid):
    for cidr in EDGE_RANGES:
        for row in routes(pid, cidr):
            if str(row.get('protocol')) == ROUTE_PROTOCOL:
                run(['nsenter', '-t', str(pid), '-n', 'ip', 'route', 'del', cidr, 'proto', ROUTE_PROTOCOL])


def connect(row):
    if NETWORK not in row['NetworkSettings']['Networks']:
        run(['docker', 'network', 'connect', NETWORK, row['Name']])
        return inspect(row['Name'])
    return row


def metrics(tunnel):
    address = tunnel['NetworkSettings']['Networks'][FRONT]['IPAddress']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://' + address + ':20241/metrics', timeout=3) as response:
        text = response.read().decode()
    match = re.search(r'^cloudflared_tunnel_ha_connections (\d+)$', text, re.M)
    locations = re.findall(r'^cloudflared_tunnel_server_locations\{[^\n]*edge_location="(hkg[^\"]+)"[^\n]*\} 1$', text, re.M)
    return int(match.group(1)) if match else 0, len(locations)


def save(state):
    target = STATE.with_suffix('.tmp')
    target.write_text(json.dumps(state))
    target.chmod(0o600)
    target.replace(STATE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--retry', action='store_true', help='Retry the verified HKG path after a latched fallback')
    parser.add_argument('--direct', action='store_true', help='Return to the default route without deleting other routes')
    args = parser.parse_args()
    import fcntl
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE.parent / 'guard.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = json.loads(STATE.read_text()) if STATE.exists() else {}
        state = {} if args.retry else dict(old)
        tunnel, gateway = inspect(TUNNEL), inspect(GATEWAY)
        if not tunnel or not tunnel['State']['Running']:
            return
        pid = tunnel['State']['Pid']
        if args.direct:
            state = {'mode': 'direct', 'reason': 'operator-direct'}
        elif state.get('tunnel_id') != tunnel['Id']:
            # A recreated connector has no managed routes yet. A latched direct
            # decision is kept; an active HKG preference is applied again.
            state.pop('applied_at', None)
            state['failures'] = 0
        now = time.time()
        alive = bool(gateway and gateway['State']['Running'])
        try:
            connections, hkg = metrics(tunnel)
        except Exception:
            connections, hkg = 0, 0
        mode, reason = decision(state, alive, connections, hkg, now)
        try:
            if mode == 'hkg':
                network = inspect(NETWORK)
                if not network or not network.get('Internal'):
                    raise RuntimeError('Expected isolated internal egress network')
                gateway, tunnel = connect(gateway), connect(tunnel)
                gateway_ip = gateway['NetworkSettings']['Networks'][NETWORK]['IPAddress']
                for cidr in EDGE_RANGES:
                    existing = routes(pid, cidr)
                    if any(str(row.get('protocol')) != ROUTE_PROTOCOL for row in existing):
                        raise RuntimeError('Unmanaged edge route exists')
                    if not any(row.get('gateway') == gateway_ip for row in existing):
                        run(['nsenter', '-t', str(pid), '-n', 'ip', 'route', 'replace', cidr, 'via', gateway_ip, 'proto', ROUTE_PROTOCOL])
                        state['applied_at'] = now
                state.setdefault('applied_at', now)
            else:
                direct(pid)
        except Exception:
            direct(pid)
            mode, reason = 'direct', 'route-setup-failed'
        fallback = inspect(FALLBACK)
        if not fallback:
            raise RuntimeError('The preconfigured HTTP/2 fallback connector is missing')
        if mode != 'hkg' and not fallback['State']['Running']:
            run(['docker', 'start', FALLBACK], timeout=15)
        elif mode == 'hkg' and reason == 'healthy' and fallback['State']['Running']:
            run(['docker', 'stop', '--time', '15', FALLBACK], timeout=25)
        state.update(mode=mode, reason=reason, tunnel_id=tunnel['Id'], checked_at=now,
                     connections=connections, hkg_locations=hkg,
                     failures=state.get('failures', 0) + 1 if reason == 'checking-connections' else 0)
        save(state)
        if (old.get('mode'), old.get('reason')) != (mode, reason):
            print(json.dumps({'mode': mode, 'reason': reason, 'connections': connections, 'hkg_locations': hkg}))


if __name__ == '__main__':
    main()
