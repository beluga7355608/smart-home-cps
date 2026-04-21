import socket
import json
import threading
import time
import random

DISCOVERY_PORT = 10000
DATA_PORT = 10001
SIMULATE_DROP_RATE = 0.05
MAX_RETRY = 2

devices = [
    {'device_id': 'temp01', 'type': 'temp'},
    {'device_id': 'light01', 'type': 'light'},
    {'device_id': 'door01', 'type': 'door'},
    {'device_id': 'smoke01', 'type': 'smoke'},
    {'device_id': 'plug01', 'type': 'plug'}
]

device_state = {
    'temp01': {'cooler': 'off'},
    'light01': {'light': 'off'},
    'door01': {'door': 'closed', 'alarm': 'off'},
    'smoke01': {'alarm': 'off'},
    'plug01': {'power': 'on'}
}

seq_state = {d['device_id']: 0 for d in devices}


def calc_checksum(device_id, dev_type, value, seq, send_ts):
    raw = f"{device_id}|{dev_type}|{value}|{seq}|{send_ts}"
    return sum(raw.encode('utf-8')) % 256

def send_discovery(dev):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = json.dumps({'device_id': dev['device_id'], 'type': dev['type']}).encode('utf-8')
    while True:
        try:
            s.sendto(msg, ('<broadcast>', DISCOVERY_PORT))
        except Exception as e:
            print('[DISCOVER SEND] error', e)
        time.sleep(10)

def report_loop(dev):
    while True:
        try:
            seq_state[dev['device_id']] += 1
            seq = seq_state[dev['device_id']]
            if dev['type'] == 'temp':
                value = round(20 + random.random() * 12, 1)
            elif dev['type'] == 'door':
                value = 1 if random.random() < 0.1 else 0
                device_state[dev['device_id']]['door'] = 'open' if value == 1 else 'closed'
            elif dev['type'] == 'smoke':
                base = 10 + random.random() * 10
                spike = 60 if random.random() < 0.05 else 0
                value = round(base + spike, 1)
            elif dev['type'] == 'plug':
                value = round(30 + random.random() * 40, 1)
            else:
                value = round(random.random() * 100, 1)

            # 模拟链路丢包（便于展示丢包率统计）
            if random.random() < SIMULATE_DROP_RATE:
                print(f"[DROP] {dev['device_id']} seq={seq} dropped before send")
                time.sleep(5 + random.random() * 5)
                continue

            send_ts = time.time()
            payload = {
                'device_id': dev['device_id'],
                'type': dev['type'],
                'value': value,
                'seq': seq,
                'send_ts': send_ts,
                'checksum': calc_checksum(dev['device_id'], dev['type'], value, seq, send_ts)
            }

            sent = False
            for attempt in range(MAX_RETRY + 1):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect(('127.0.0.1', DATA_PORT))
                    s.sendall(json.dumps(payload).encode('utf-8'))
                    try:
                        data = s.recv(4096)
                        if data:
                            handle_command(dev['device_id'], data.decode('utf-8'))
                    except Exception:
                        pass
                    s.close()
                    sent = True
                    break
                except Exception as e:
                    print(f"[REPORT] {dev['device_id']} seq={seq} attempt={attempt+1} error: {e}")
                    time.sleep(0.5 * (attempt + 1))
            if not sent:
                print(f"[REPORT] {dev['device_id']} seq={seq} all retries failed")
        except Exception as e:
            print(f"[REPORT] {dev['device_id']} error: {e}")
        time.sleep(5 + random.random() * 5)

def handle_command(device_id, raw):
    try:
        obj = json.loads(raw)
    except Exception:
        print(f"[RESP] {device_id} got (raw): {raw}")
        return
    cmd = obj.get('cmd', 'none')
    ack_seq = obj.get('ack_seq')
    if ack_seq is not None:
        print(f"[ACK] {device_id} ack_seq={ack_seq} status={obj.get('status', 'ok')}")
    if cmd == 'none':
        print(f"[RESP] {device_id} got: none")
        return
    # 模拟设备动作
    if cmd == 'turn_on_light':
        device_state[device_id]['light'] = 'on'
    elif cmd == 'turn_off_light':
        device_state[device_id]['light'] = 'off'
    elif cmd == 'turn_on_cooler':
        device_state[device_id]['cooler'] = 'on'
    elif cmd == 'turn_off_cooler':
        device_state[device_id]['cooler'] = 'off'
    elif cmd == 'turn_on_plug':
        device_state[device_id]['power'] = 'on'
    elif cmd == 'turn_off_plug':
        device_state[device_id]['power'] = 'off'
    elif cmd == 'alarm_on':
        if device_id in device_state:
            device_state[device_id]['alarm'] = 'on'
    elif cmd == 'alarm_off':
        if device_id in device_state:
            device_state[device_id]['alarm'] = 'off'
    print(f"[RESP] {device_id} cmd={cmd} state={device_state.get(device_id)}")

if __name__ == '__main__':
    for d in devices:
        threading.Thread(target=send_discovery, args=(d,), daemon=True).start()
        threading.Thread(target=report_loop, args=(d,), daemon=True).start()
    print('[SIM] device simulator running. Ctrl-C to stop.')
    while True:
        time.sleep(1)
