import socket
import threading
import json
import time
import sqlite3
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_socketio import SocketIO

DISCOVERY_PORT = 10000
DATA_PORT = 10001

devices = {}  # device_id -> {type, ip, last_seen, last_value, pending_cmd, last_cmd}
DB_PATH = 'cps_history.db'
alarms = []  # list of {ts, level, device_id, message}
energy_stats = {}  # device_id -> {wh, last_ts}
net_stats = {}  # device_id -> network KPIs
ALLOWED_COMMANDS = {
    'turn_on_light',
    'turn_off_light',
    'turn_on_cooler',
    'turn_off_cooler',
    'turn_on_plug',
    'turn_off_plug',
    'alarm_on',
    'alarm_off',
    'auto_on',
    'auto_off',
    'none'
}
DEVICE_ALLOWED_COMMANDS = {
    'light': {'turn_on_light', 'turn_off_light', 'auto_on', 'auto_off', 'none'},
    'plug': {'turn_on_plug', 'turn_off_plug', 'none'},
    'door': {'alarm_on', 'alarm_off', 'none'},
    'smoke': {'alarm_on', 'alarm_off', 'none'},
    'temp': {'turn_on_cooler', 'turn_off_cooler', 'auto_on', 'auto_off', 'none'}
}
SCENES = {
    'home': {
        'light': 'turn_on_light',
        'temp': 'turn_on_cooler',
        'plug': 'turn_on_plug',
        'door': 'alarm_on',
        'smoke': 'alarm_on'
    },
    'away': {
        'light': 'turn_off_light',
        'temp': 'turn_off_cooler',
        'plug': 'turn_off_plug',
        'door': 'alarm_on',
        'smoke': 'alarm_on'
    },
    'night': {
        'light': 'turn_off_light',
        'temp': 'turn_off_cooler',
        'plug': 'turn_off_plug',
        'door': 'alarm_on',
        'smoke': 'alarm_on'
    }
}
POWER_MAP_W = {
    'light': 12,
    'temp': 800,
    'plug': 60
}


def calc_checksum(device_id, dev_type, value, seq, send_ts):
    raw = f"{device_id}|{dev_type}|{value}|{seq}|{send_ts}"
    return sum(raw.encode('utf-8')) % 256


def ensure_net_stat(device_id):
    return net_stats.setdefault(device_id, {
        'rx_packets': 0,
        'bytes_rx': 0,
        'bad_checksum': 0,
        'lost_packets': 0,
        'last_seq': None,
        'latency_ms_avg': 0.0,
        'latency_samples': 0,
        'duplicate_packets': 0
    })


def update_latency(stat, latency_ms):
    n = stat['latency_samples']
    avg = stat['latency_ms_avg']
    stat['latency_ms_avg'] = (avg * n + latency_ms) / (n + 1)
    stat['latency_samples'] = n + 1


def summarize_net_stats():
    out = []
    total_rx = 0
    total_lost = 0
    total_bad = 0
    weighted_latency_sum = 0.0
    weighted_samples = 0
    for dev_id, s in net_stats.items():
        rx = s['rx_packets']
        lost = s['lost_packets']
        total = rx + lost
        loss_rate = (lost / total) if total > 0 else 0.0
        out.append({
            'device_id': dev_id,
            'rx_packets': rx,
            'lost_packets': lost,
            'loss_rate': round(loss_rate * 100, 2),
            'bad_checksum': s['bad_checksum'],
            'latency_ms_avg': round(s['latency_ms_avg'], 2),
            'duplicate_packets': s['duplicate_packets'],
            'bytes_rx': s['bytes_rx']
        })
        total_rx += rx
        total_lost += lost
        total_bad += s['bad_checksum']
        weighted_latency_sum += s['latency_ms_avg'] * s['latency_samples']
        weighted_samples += s['latency_samples']
    agg_loss = (total_lost / (total_rx + total_lost)) if (total_rx + total_lost) > 0 else 0.0
    agg_latency = (weighted_latency_sum / weighted_samples) if weighted_samples > 0 else 0.0
    return {
        'devices': out,
        'aggregate': {
            'total_rx': total_rx,
            'total_lost': total_lost,
            'total_bad_checksum': total_bad,
            'loss_rate': round(agg_loss * 100, 2),
            'latency_ms_avg': round(agg_latency, 2)
        }
    }


def command_coverage_report():
    report = []
    for dev_id, info in devices.items():
        dev_type = info.get('type')
        allowed = sorted(list(DEVICE_ALLOWED_COMMANDS.get(dev_type, {'none'})))
        concrete = [c for c in allowed if c != 'none']
        report.append({
            'device_id': dev_id,
            'type': dev_type,
            'allowed_commands': allowed,
            'has_specific_command': len(concrete) > 0
        })
    all_ok = all(item['has_specific_command'] for item in report) if report else True
    return {'all_devices_have_commands': all_ok, 'devices': report}


def add_alarm_entry(dev_id, dev_type, value, level, message):
    now_ts = int(time.time())
    devices.setdefault(dev_id, {})
    devices[dev_id].update({'type': dev_type, 'last_seen': time.time(), 'last_value': value})
    try:
        insert_reading(dev_id, dev_type, float(value), now_ts)
    except Exception as e:
        print('[DB] insert error', e)
    alarm = {'ts': now_ts, 'level': level, 'device_id': dev_id, 'message': message}
    alarms.append(alarm)
    socketio.emit('devices', list_devices())
    socketio.emit('reading', {'device_id': dev_id, 'type': dev_type, 'value': value, 'ts': now_ts})
    socketio.emit('alarm', alarm)
    return alarm


def ensure_alarm_enabled(dev_id, dev_type):
    if dev_type not in ('door', 'smoke'):
        return None
    devices.setdefault(dev_id, {})
    if 'alarm_enabled' not in devices[dev_id]:
        devices[dev_id]['alarm_enabled'] = True
    return devices[dev_id]['alarm_enabled']


def ensure_auto_enabled(dev_id, dev_type):
    if dev_type not in ('light', 'temp'):
        return None
    devices.setdefault(dev_id, {})
    if 'auto_enabled' not in devices[dev_id]:
        devices[dev_id]['auto_enabled'] = True
    return devices[dev_id]['auto_enabled']


def ensure_manual_hold(dev_id, dev_type):
    if dev_type not in ('light', 'temp', 'plug'):
        return None
    devices.setdefault(dev_id, {})
    if 'manual_hold' not in devices[dev_id]:
        devices[dev_id]['manual_hold'] = False
    return devices[dev_id]['manual_hold']

# Flask app for visualization
app = Flask(__name__, static_folder='.', static_url_path='')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')


@app.route('/favicon.ico')
def favicon():
    return ('', 204)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            device_type TEXT NOT NULL,
            value REAL NOT NULL,
            ts INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_reading(device_id, device_type, value, ts):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO readings (device_id, device_type, value, ts) VALUES (?, ?, ?, ?)",
        (device_id, device_type, value, ts)
    )
    conn.commit()
    conn.close()


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/devices')
def api_devices():
    out = []
    for dev_id, info in devices.items():
        out.append({
            'device_id': dev_id,
            'type': info.get('type'),
            'ip': info.get('ip'),
            'last_seen': int(info.get('last_seen', 0)),
            'last_value': info.get('last_value'),
            'pending_cmd': info.get('pending_cmd'),
            'last_cmd': info.get('last_cmd'),
            'alarm_enabled': info.get('alarm_enabled'),
            'auto_enabled': info.get('auto_enabled')
        })
    return jsonify(out)


@app.route('/api/command', methods=['POST'])
def api_command():
    obj = request.get_json() or {}
    dev_id = obj.get('device_id')
    cmd = obj.get('cmd')
    if not dev_id or not cmd:
        return jsonify({'status': 'error', 'msg': 'missing device_id or cmd'}), 400
    if cmd not in ALLOWED_COMMANDS:
        return jsonify({'status': 'error', 'msg': 'invalid cmd'}), 400
    if dev_id not in devices:
        return jsonify({'status': 'error', 'msg': 'device not found'}), 404
    dev_type = devices.get(dev_id, {}).get('type')
    allowed_for_type = DEVICE_ALLOWED_COMMANDS.get(dev_type, {'none'})
    if cmd not in allowed_for_type:
        return jsonify({'status': 'error', 'msg': f'cmd not allowed for device type {dev_type}'}), 400
    if dev_type in ('door', 'smoke') and cmd in ('alarm_on', 'alarm_off'):
        devices.setdefault(dev_id, {})['alarm_enabled'] = (cmd == 'alarm_on')
        devices.setdefault(dev_id, {})['last_cmd'] = cmd
    if dev_type in ('light', 'temp') and cmd in ('auto_on', 'auto_off'):
        devices.setdefault(dev_id, {})['auto_enabled'] = (cmd == 'auto_on')
        devices.setdefault(dev_id, {})['manual_hold'] = False
        devices.setdefault(dev_id, {})['last_cmd'] = cmd
        return jsonify({'status': 'ok'})
    if dev_type in ('light', 'temp') and cmd in ('turn_on_light', 'turn_off_light', 'turn_on_cooler', 'turn_off_cooler'):
        devices.setdefault(dev_id, {})['auto_enabled'] = False
        devices.setdefault(dev_id, {})['manual_hold'] = False
        devices.setdefault(dev_id, {})['last_cmd'] = cmd
    if dev_type == 'plug' and cmd in ('turn_on_plug', 'turn_off_plug'):
        devices.setdefault(dev_id, {})['manual_hold'] = False
        devices.setdefault(dev_id, {})['last_cmd'] = cmd
    devices.setdefault(dev_id, {})['pending_cmd'] = cmd
    return jsonify({'status': 'ok'})


@app.route('/api/alarm/trigger', methods=['POST'])
def api_alarm_trigger():
    obj = request.get_json() or {}
    dev_id = obj.get('device_id')
    if not dev_id:
        return jsonify({'status': 'error', 'msg': '缺少 device_id'}), 400
    if dev_id not in devices:
        return jsonify({'status': 'error', 'msg': '设备不存在'}), 404
    dev_type = devices.get(dev_id, {}).get('type')
    if dev_type not in ('door', 'smoke'):
        return jsonify({'status': 'error', 'msg': '仅支持门磁/烟雾设备'}), 400
    if ensure_alarm_enabled(dev_id, dev_type) is False:
        return jsonify({'status': 'error', 'msg': '告警已关闭'}), 400
    if dev_type == 'door':
        value = 1
        level = '中'
        message = '门磁打开（手动）'
    else:
        value = 60
        level = '高'
        message = '烟雾浓度高（手动）'
    devices.setdefault(dev_id, {})['pending_cmd'] = 'alarm_on'
    alarm = add_alarm_entry(dev_id, dev_type, value, level, message)
    return jsonify({'status': 'ok', 'alarm': alarm})


@app.route('/api/history')
def api_history():
    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({'status': 'error', 'msg': 'missing device_id'}), 400
    limit = int(request.args.get('limit', '300'))
    since = request.args.get('since')
    until = request.args.get('until')
    params = [device_id]
    where = "device_id = ?"
    if since:
        where += " AND ts >= ?"
        params.append(int(since))
    if until:
        where += " AND ts <= ?"
        params.append(int(until))
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"SELECT device_id, device_type, value, ts FROM readings WHERE {where} ORDER BY ts ASC LIMIT ?",
        (*params, limit)
    )
    rows = cur.fetchall()
    conn.close()
    data = [
        {'device_id': r[0], 'type': r[1], 'value': r[2], 'ts': r[3]}
        for r in rows
    ]
    return jsonify(data)


@app.route('/api/alarms')
def api_alarms():
    return jsonify(alarms[-50:])


@app.route('/api/energy')
def api_energy():
    out = []
    for dev_id, info in energy_stats.items():
        out.append({'device_id': dev_id, 'wh': round(info.get('wh', 0), 2)})
    return jsonify(out)


@app.route('/api/alarms/export')
def api_alarms_export():
    lines = ["ts,level,device_id,message"]
    for a in alarms:
        lines.append(f"{a.get('ts')},{a.get('level')},{a.get('device_id')},{a.get('message')}")
    csv_data = "\n".join(lines)
    return Response(csv_data, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=alarms.csv'})


@app.route('/api/scenes')
def api_scenes():
    return jsonify(list(SCENES.keys()))


@app.route('/api/scene/apply', methods=['POST'])
def api_scene_apply():
    obj = request.get_json() or {}
    scene = obj.get('scene')
    if scene not in SCENES:
        return jsonify({'status': 'error', 'msg': 'invalid scene'}), 400
    mapping = SCENES[scene]
    for dev_id, info in devices.items():
        cmd = mapping.get(info.get('type'))
        if scene == 'home' and info.get('type') in ('light', 'temp'):
            info['auto_enabled'] = True
            info['manual_hold'] = False
            info['last_cmd'] = 'auto_on'
            continue
        if scene in ('away', 'night') and info.get('type') in ('light', 'temp'):
            info['auto_enabled'] = False
            info['manual_hold'] = True
        if cmd and cmd in DEVICE_ALLOWED_COMMANDS.get(info.get('type'), {'none'}):
            if info.get('type') in ('door', 'smoke') and cmd in ('alarm_on', 'alarm_off'):
                info['alarm_enabled'] = (cmd == 'alarm_on')
                info['last_cmd'] = cmd
            if info.get('type') in ('light', 'temp', 'plug'):
                if scene in ('away', 'night') and info.get('type') == 'plug':
                    info['manual_hold'] = True
                info['last_cmd'] = cmd
            info['pending_cmd'] = cmd
    socketio.emit('devices', list_devices())
    return jsonify({'status': 'ok', 'scene': scene})


@app.route('/api/summary')
def api_summary():
    total = len(devices)
    online = total
    alarm_count = len(alarms)
    energy_total = round(sum(v.get('wh', 0) for v in energy_stats.values()), 2)
    net = summarize_net_stats()['aggregate']
    return jsonify({
        'total_devices': total,
        'online_devices': online,
        'alarm_count': alarm_count,
        'energy_wh': energy_total,
        'loss_rate': net['loss_rate'],
        'latency_ms_avg': net['latency_ms_avg']
    })


@app.route('/api/netstats')
def api_netstats():
    return jsonify(summarize_net_stats())


@app.route('/api/command-coverage')
def api_command_coverage():
    return jsonify(command_coverage_report())


@socketio.on('connect')
def on_connect():
    socketio.emit('devices', list_devices())


def list_devices():
    out = []
    for dev_id, info in devices.items():
        out.append({
            'device_id': dev_id,
            'type': info.get('type'),
            'ip': info.get('ip'),
            'last_seen': int(info.get('last_seen', 0)),
            'last_value': info.get('last_value'),
            'pending_cmd': info.get('pending_cmd'),
            'last_cmd': info.get('last_cmd'),
            'alarm_enabled': info.get('alarm_enabled'),
            'auto_enabled': info.get('auto_enabled')
        })
    return out

def udp_discovery_listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', DISCOVERY_PORT))
    print(f"[DISCOVERY] UDP listener started on port {DISCOVERY_PORT}")
    while True:
        try:
            data, addr = s.recvfrom(4096)
            try:
                obj = json.loads(data.decode('utf-8'))
                dev_id = obj.get('device_id')
                dev_type = obj.get('type')
                if dev_id:
                    prev = devices.get(dev_id, {})
                    devices[dev_id] = {
                        'type': dev_type,
                        'ip': addr[0],
                        'last_seen': time.time(),
                        'last_value': prev.get('last_value'),
                        'pending_cmd': prev.get('pending_cmd'),
                        'last_cmd': prev.get('last_cmd'),
                        'alarm_enabled': prev.get('alarm_enabled'),
                        'auto_enabled': prev.get('auto_enabled'),
                        'manual_hold': prev.get('manual_hold')
                    }
                    ensure_alarm_enabled(dev_id, dev_type)
                    ensure_auto_enabled(dev_id, dev_type)
                    ensure_manual_hold(dev_id, dev_type)
                    print(f"[DISCOVERY] {dev_id} ({dev_type}) discovered from {addr[0]}")
                    socketio.emit('devices', list_devices())
            except Exception as e:
                print('[DISCOVERY] invalid packet', e)
        except Exception as e:
            print('[DISCOVERY] socket error', e)

def apply_policy(dev_id, dev_type, value):
    # 优先处理人工下发命令（pending_cmd）
    pending = devices.get(dev_id, {}).pop('pending_cmd', None)
    if pending and pending in DEVICE_ALLOWED_COMMANDS.get(dev_type, {'none'}):
        return {'cmd': pending}
    if dev_type == 'light':
        if ensure_auto_enabled(dev_id, dev_type) is not True:
            return {'cmd': 'none'}
        try:
            v = float(value)
            if v < 30:
                return {'cmd': 'turn_on_light'}
            if v > 60:
                return {'cmd': 'turn_off_light'}
        except:
            pass
    if dev_type == 'temp':
        if ensure_auto_enabled(dev_id, dev_type) is not True:
            return {'cmd': 'none'}
        try:
            v = float(value)
            if v > 28:
                return {'cmd': 'turn_on_cooler'}
            if v < 24:
                return {'cmd': 'turn_off_cooler'}
        except:
            pass
    if dev_type == 'door':
        if ensure_alarm_enabled(dev_id, dev_type) is False:
            return {'cmd': 'none'}
        if str(value) == '1':
            return {'cmd': 'alarm_on'}
        return {'cmd': 'none'}
    if dev_type == 'smoke':
        try:
            v = float(value)
            if ensure_alarm_enabled(dev_id, dev_type) is False:
                return {'cmd': 'none'}
            if v >= 50:
                return {'cmd': 'alarm_on'}
            return {'cmd': 'none'}
        except:
            pass
    return {'cmd': 'none'}

def tcp_data_handler(conn, addr):
    try:
        data = conn.recv(4096)
        if not data:
            return
        obj = json.loads(data.decode('utf-8'))
        dev_id = obj.get('device_id')
        dev_type = obj.get('type')
        value = obj.get('value')
        seq = int(obj.get('seq', 0))
        send_ts = float(obj.get('send_ts', 0))
        recv_checksum = int(obj.get('checksum', -1))
        ts = int(time.time())
        now = time.time()

        stat = ensure_net_stat(dev_id)
        stat['bytes_rx'] += len(data)

        # 丢包/重复统计（基于应用层序号）
        last_seq = stat.get('last_seq')
        if last_seq is None:
            stat['last_seq'] = seq
        else:
            if seq > last_seq + 1:
                stat['lost_packets'] += (seq - last_seq - 1)
                stat['last_seq'] = seq
            elif seq <= last_seq:
                stat['duplicate_packets'] += 1
            else:
                stat['last_seq'] = seq

        # 校验和检测
        expected_checksum = calc_checksum(dev_id, dev_type, value, seq, send_ts)
        if recv_checksum != expected_checksum:
            stat['bad_checksum'] += 1
            alarms.append({'ts': int(now), 'level': '高', 'device_id': dev_id, 'message': '校验和错误'})
            conn.sendall(json.dumps({'cmd': 'none', 'ack_seq': seq, 'status': 'checksum_error'}).encode('utf-8'))
            socketio.emit('alarm', alarms[-1])
            socketio.emit('netstats', summarize_net_stats())
            return

        # 端到端时延估计（应用层时间戳）
        if send_ts > 0:
            latency_ms = max(0.0, (now - send_ts) * 1000)
            update_latency(stat, latency_ms)

        stat['rx_packets'] += 1

        devices.setdefault(dev_id, {})
        prev_last_value = devices[dev_id].get('last_value')
        devices[dev_id].update({'type': dev_type, 'ip': addr[0], 'last_seen': time.time(), 'last_value': value})
        ensure_alarm_enabled(dev_id, dev_type)
        ensure_auto_enabled(dev_id, dev_type)
        ensure_manual_hold(dev_id, dev_type)
        if dev_type in ('light', 'temp', 'plug') and devices[dev_id].get('manual_hold') is True:
            value = prev_last_value if prev_last_value is not None else value
            devices[dev_id]['last_value'] = value
        print(f"[DATA] From {dev_id}@{addr[0]} type={dev_type} value={value} seq={seq}")
        now_ts = int(time.time())
        if dev_type in POWER_MAP_W:
            stat = energy_stats.setdefault(dev_id, {'wh': 0.0, 'last_ts': now_ts})
            delta_s = max(0, now_ts - stat.get('last_ts', now_ts))
            stat['wh'] += POWER_MAP_W[dev_type] * (delta_s / 3600)
            stat['last_ts'] = now_ts
        try:
            insert_reading(dev_id, dev_type, float(value), ts)
        except Exception as e:
            print('[DB] insert error', e)
        if dev_type == 'smoke' and ensure_alarm_enabled(dev_id, dev_type) is not False:
            try:
                v = float(value)
                if v >= 50:
                    alarms.append({'ts': now_ts, 'level': '高', 'device_id': dev_id, 'message': '烟雾浓度高'})
            except Exception:
                pass
        if dev_type == 'door' and ensure_alarm_enabled(dev_id, dev_type) is not False and str(value) == '1':
            alarms.append({'ts': now_ts, 'level': '中', 'device_id': dev_id, 'message': '门磁打开'})
        response = apply_policy(dev_id, dev_type, value)
        cmd_sent = response.get('cmd')
        if cmd_sent and cmd_sent != 'none':
            devices[dev_id]['last_cmd'] = cmd_sent
        response['ack_seq'] = seq
        response['server_ts'] = now
        conn.sendall(json.dumps(response).encode('utf-8'))
        socketio.emit('devices', list_devices())
        socketio.emit('reading', {'device_id': dev_id, 'type': dev_type, 'value': value, 'ts': ts})
        if dev_type in ('smoke', 'door') and len(alarms) > 0:
            socketio.emit('alarm', alarms[-1])
        socketio.emit('energy', [{'device_id': k, 'wh': round(v.get('wh', 0), 2)} for k, v in energy_stats.items()])
        socketio.emit('netstats', summarize_net_stats())
    except Exception as e:
        print('[DATA] handler error', e)
    finally:
        try:
            conn.close()
        except:
            pass

def tcp_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', DATA_PORT))
    s.listen(8)
    print(f"[DATA] TCP server listening on port {DATA_PORT}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=tcp_data_handler, args=(conn, addr), daemon=True).start()

def monitor_loop():
    while True:
        now = time.time()
        # 清理超时设备（超过30s未见）
        removed = []
        for dev, info in list(devices.items()):
            if now - info.get('last_seen', 0) > 30:
                removed.append(dev)
        for d in removed:
            devices.pop(d, None)
            print(f"[MONITOR] removed stale device {d}")
        time.sleep(5)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=udp_discovery_listener, daemon=True).start()
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=monitor_loop, daemon=True).start()
    print('[MAIN] Server running. HTTP dashboard available at http://127.0.0.1:5000')
    # 开发环境下允许使用 Werkzeug，避免 Flask-SocketIO 在 debug=False 下拒绝启动。
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
