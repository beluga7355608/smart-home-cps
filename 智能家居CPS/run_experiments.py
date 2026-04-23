import argparse
import json
import subprocess
import sys
import time
from urllib.request import urlopen, Request

DEFAULT_PYTHON = sys.executable


def fetch_json(url, timeout=5):
    req = Request(url, headers={'User-Agent': 'exp-client'})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode('utf-8')
    return json.loads(data)


def run_duration(seconds, interval_s, sample_func):
    end_ts = time.time() + seconds
    samples = []
    while time.time() < end_ts:
        try:
            samples.append(sample_func())
        except Exception:
            pass
        time.sleep(interval_s)
    return samples


def avg(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def summarize_perf(samples):
    if not samples:
        return {}
    last = samples[-1]
    return {
        'poll_requests': last.get('poll_requests'),
        'tcp_rx': last.get('tcp_rx'),
        'tcp_latency_ms_avg': last.get('tcp_latency_ms_avg'),
        'tcp_latency_ms_max': last.get('tcp_latency_ms_max')
    }


def run_cmd(cmd, cwd):
    return subprocess.Popen(cmd, cwd=cwd)


def main():
    parser = argparse.ArgumentParser(description='Run experiments and collect basic stats.')
    parser.add_argument('--cwd', default='.', help='project folder')
    parser.add_argument('--base-url', default='http://127.0.0.1:5000', help='server base url')
    parser.add_argument('--duration', type=int, default=120, help='seconds per experiment')
    parser.add_argument('--interval', type=float, default=2.0, help='sampling interval seconds')
    parser.add_argument('--devices', type=str, default='5,20,50', help='device counts')
    parser.add_argument('--drop-rates', type=str, default='0,0.05,0.1,0.2', help='drop rates')
    parser.add_argument('--delay-ms', type=str, default='0,50,100,200', help='extra delay ms')
    parser.add_argument('--poll-interval-ms', type=int, default=1000, help='polling interval in ms')
    parser.add_argument('--python', default=DEFAULT_PYTHON, help='python executable')
    args = parser.parse_args()

    base = args.base_url.rstrip('/')
    perf_url = base + '/api/perf'
    poll_url = base + '/api/poll'

    results = {
        'meta': {
            'duration_s': args.duration,
            'interval_s': args.interval,
            'poll_interval_ms': args.poll_interval_ms,
            'base_url': base
        },
        'protocol': {},
        'loss_delay': [],
        'scale': []
    }

    print('[EXP] protocol comparison: polling vs websocket (poll endpoint only)')
    # protocol comparison uses /api/poll as polling workload
    def sample_perf():
        _ = fetch_json(poll_url)
        return fetch_json(perf_url)

    samples = run_duration(args.duration, args.interval, sample_perf)
    results['protocol']['polling'] = summarize_perf(samples)

    # loss/delay experiments
    drop_rates = [float(x) for x in args.drop_rates.split(',') if x.strip()]
    delays = [int(x) for x in args.delay_ms.split(',') if x.strip()]

    for drop, delay in zip(drop_rates, delays):
        print(f'[EXP] loss/delay: drop={drop} delay={delay}ms')
        sim = run_cmd([
            args.python, 'device_sim.py',
            '--drop-rate', str(drop),
            '--delay-ms', str(delay),
            '--num-devices', '5',
            '--interval-min', '5',
            '--interval-max', '10'
        ], args.cwd)
        time.sleep(2)
        samples = run_duration(args.duration, args.interval, lambda: fetch_json(perf_url))
        sim.terminate()
        results['loss_delay'].append({
            'drop_rate': drop,
            'delay_ms': delay,
            'perf': summarize_perf(samples)
        })

    # scale experiments
    counts = [int(x) for x in args.devices.split(',') if x.strip()]
    for n in counts:
        print(f'[EXP] scale: devices={n}')
        sim = run_cmd([
            args.python, 'device_sim.py',
            '--num-devices', str(n)
        ], args.cwd)
        time.sleep(2)
        samples = run_duration(args.duration, args.interval, lambda: fetch_json(perf_url))
        sim.terminate()
        results['scale'].append({
            'devices': n,
            'perf': summarize_perf(samples)
        })

    out_path = 'experiment_results.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=True, indent=2)
    print('[EXP] done. results ->', out_path)


if __name__ == '__main__':
    main()
