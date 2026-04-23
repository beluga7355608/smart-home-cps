import argparse
import socket
import struct
import time

FLAG_DATA = 1
FLAG_ACK = 2


def build_packet(seq, ack, flags, payload):
    header = struct.pack('!IIBH', seq, ack, flags, len(payload))
    return header + payload


def parse_packet(data):
    if len(data) < 11:
        return None
    seq, ack, flags, length = struct.unpack('!IIBH', data[:11])
    payload = data[11:11 + length]
    return seq, ack, flags, payload


def run_sender(host, port, count):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    seq = 1
    for i in range(count):
        payload = f"msg-{seq}".encode('utf-8')
        pkt = build_packet(seq, 0, FLAG_DATA, payload)
        while True:
            s.sendto(pkt, (host, port))
            try:
                data, _ = s.recvfrom(1024)
                res = parse_packet(data)
                if res and (res[2] & FLAG_ACK) and res[1] == seq:
                    print(f"[ACK] seq={seq}")
                    break
            except socket.timeout:
                print(f"[RESEND] seq={seq}")
        seq += 1
        time.sleep(0.1)
    s.close()


def run_receiver(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((host, port))
    expected = 1
    buffer = {}
    print(f"[recv] listening on {host}:{port}")
    while True:
        data, addr = s.recvfrom(4096)
        res = parse_packet(data)
        if not res:
            continue
        seq, ack, flags, payload = res
        if flags & FLAG_DATA:
            buffer[seq] = payload
            ack_pkt = build_packet(0, seq, FLAG_ACK, b'')
            s.sendto(ack_pkt, addr)
            while expected in buffer:
                msg = buffer.pop(expected)
                print(f"[DATA] seq={expected} {msg.decode('utf-8', errors='replace')}")
                expected += 1


def main():
    parser = argparse.ArgumentParser(description='Reliable UDP demo with ordered delivery')
    sub = parser.add_subparsers(dest='mode', required=True)

    ps = sub.add_parser('send')
    ps.add_argument('--host', required=True)
    ps.add_argument('--port', type=int, required=True)
    ps.add_argument('--count', type=int, default=5)

    pr = sub.add_parser('recv')
    pr.add_argument('--host', default='0.0.0.0')
    pr.add_argument('--port', type=int, required=True)

    args = parser.parse_args()
    if args.mode == 'send':
        run_sender(args.host, args.port, args.count)
    else:
        run_receiver(args.host, args.port)


if __name__ == '__main__':
    main()
