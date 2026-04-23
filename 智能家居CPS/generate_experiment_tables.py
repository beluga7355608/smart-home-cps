import json
import os
import time

DOC_PATH = '内容与思辨.md'
RESULT_PATH = 'experiment_results.json'

START = '<!-- EXPERIMENT_RESULTS_START -->'
END = '<!-- EXPERIMENT_RESULTS_END -->'


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_table(headers, rows):
    lines = []
    lines.append('| ' + ' | '.join(headers) + ' |')
    lines.append('|' + '|'.join(['---'] * len(headers)) + '|')
    for r in rows:
        lines.append('| ' + ' | '.join(r) + ' |')
    return '\n'.join(lines)


def safe_num(val, digits=2):
    if val is None:
        return '-'
    if isinstance(val, (int, float)):
        return f"{val:.{digits}f}" if isinstance(val, float) else str(val)
    return str(val)


def build_content(results):
    meta = results.get('meta', {})
    duration = meta.get('duration_s', None)
    base_url = meta.get('base_url', '-')
    poll_interval = meta.get('poll_interval_ms', None)

    lines = []
    lines.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"实验基准URL: {base_url}")
    if duration is not None:
        lines.append(f"单组持续时间: {duration}s")
    if poll_interval is not None:
        lines.append(f"轮询间隔: {poll_interval}ms")

    lines.append('')
    lines.append('### 协议对照实验（轮询 vs WebSocket）')

    protocol = results.get('protocol', {})
    rows = []
    for name, perf in protocol.items():
        poll_requests = perf.get('poll_requests')
        req_per_min = '-'
        if duration and isinstance(poll_requests, int) and duration > 0:
            req_per_min = safe_num(poll_requests / duration * 60, 1)
        rows.append([
            name,
            safe_num(poll_requests, 0),
            safe_num(perf.get('tcp_rx'), 0),
            safe_num(perf.get('tcp_latency_ms_avg')),
            safe_num(perf.get('tcp_latency_ms_max')),
            req_per_min
        ])
    if not rows:
        rows = [['-', '-', '-', '-', '-', '-']]
    lines.append(format_table([
        '方案', '轮询请求数', 'TCP接收数', 'TCP平均处理时延(ms)', 'TCP最大处理时延(ms)', '每分钟轮询数'
    ], rows))

    lines.append('')
    lines.append('### 错误注入实验（丢包/延迟）')
    loss_rows = []
    for item in results.get('loss_delay', []):
        perf = item.get('perf', {})
        loss_rows.append([
            safe_num(item.get('drop_rate'), 2),
            safe_num(item.get('delay_ms'), 0),
            safe_num(perf.get('tcp_rx'), 0),
            safe_num(perf.get('tcp_latency_ms_avg')),
            safe_num(perf.get('tcp_latency_ms_max'))
        ])
    if not loss_rows:
        loss_rows = [['-', '-', '-', '-', '-']]
    lines.append(format_table([
        '丢包率', '延迟(ms)', 'TCP接收数', 'TCP平均处理时延(ms)', 'TCP最大处理时延(ms)'
    ], loss_rows))

    lines.append('')
    lines.append('### 并发规模实验（设备数）')
    scale_rows = []
    for item in results.get('scale', []):
        perf = item.get('perf', {})
        scale_rows.append([
            safe_num(item.get('devices'), 0),
            safe_num(perf.get('tcp_rx'), 0),
            safe_num(perf.get('tcp_latency_ms_avg')),
            safe_num(perf.get('tcp_latency_ms_max'))
        ])
    if not scale_rows:
        scale_rows = [['-', '-', '-', '-']]
    lines.append(format_table([
        '设备数量', 'TCP接收数', 'TCP平均处理时延(ms)', 'TCP最大处理时延(ms)'
    ], scale_rows))

    return '\n'.join(lines)


def update_doc(doc_path, content):
    with open(doc_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    if START not in raw or END not in raw:
        raise RuntimeError('Markers not found in doc')
    before = raw.split(START)[0]
    after = raw.split(END)[1]
    updated = before + START + '\n' + content + '\n' + END + after
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(updated)


def main():
    if not os.path.exists(RESULT_PATH):
        print('experiment_results.json not found')
        return
    results = load_json(RESULT_PATH)
    content = build_content(results)
    update_doc(DOC_PATH, content)
    print('updated:', DOC_PATH)


if __name__ == '__main__':
    main()
