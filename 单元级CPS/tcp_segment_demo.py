import argparse
import socket
import struct


def build_tcp_header(src_port, dst_port, seq, ack, flags, window=4096):
    offset = 5  # 5 * 4 = 20 bytes
    offset_res = (offset << 4) & 0xF0
    urg = 1 if 'URG' in flags else 0
    ackf = 1 if 'ACK' in flags else 0
    psh = 1 if 'PSH' in flags else 0
    rst = 1 if 'RST' in flags else 0
    syn = 1 if 'SYN' in flags else 0
    fin = 1 if 'FIN' in flags else 0
    flag_bits = (urg << 5) | (ackf << 4) | (psh << 3) | (rst << 2) | (syn << 1) | fin
    checksum = 0
    urg_ptr = 0
    return struct.pack('!HHLLBBHHH', src_port, dst_port, seq, ack, offset_res, flag_bits, window, checksum, urg_ptr)


def parse_tcp_header(data):
    if len(data) < 20:
        raise ValueError('TCP header too short')
    src_port, dst_port, seq, ack, offset_res, flags, window, checksum, urg_ptr = struct.unpack('!HHLLBBHHH', data[:20])
    offset = (offset_res >> 4) * 4
    return {
        'src_port': src_port,
        'dst_port': dst_port,
        'seq': seq,
        'ack': ack,
        'offset': offset,
        'flags': flags,
        'window': window,
        'checksum': checksum,
        'urg_ptr': urg_ptr
    }


def run_server(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, port))
    s.listen(1)
    print(f"[server] listening on {host}:{port}")
    conn, addr = s.accept()
    print(f"[server] connection from {addr}")
    buf = b''
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
    conn.close()
    if len(buf) < 20:
        print('[server] no tcp header received')
        return
    header = parse_tcp_header(buf[:20])
    payload = buf[20:]
    print('[server] tcp header:')
    for k, v in header.items():
        print(f"  {k}: {v}")
    print('[server] payload:')
    try:
        print(payload.decode('utf-8'))
    except Exception:
        print(payload)


def run_client(host, port, payload):
    header = build_tcp_header(12345, port, seq=1, ack=0, flags={'SYN'})
    data = header + payload.encode('utf-8')
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(data)
    s.close()
    print('[client] sent header + payload')


def main():
    parser = argparse.ArgumentParser(description='TCP segment structure demo over normal TCP')
    sub = parser.add_subparsers(dest='mode', required=True)

    ps = sub.add_parser('server')
    ps.add_argument('--host', default='0.0.0.0')
    ps.add_argument('--port', type=int, default=9000)

    pc = sub.add_parser('client')
    pc.add_argument('--host', required=True)
    pc.add_argument('--port', type=int, required=True)
    pc.add_argument('--payload', default='hello tcp segment')

    args = parser.parse_args()
    if args.mode == 'server':
        run_server(args.host, args.port)
    else:
        run_client(args.host, args.port, args.payload)


if __name__ == '__main__':
    main()
