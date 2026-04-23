import argparse
import ipaddress
import socket
import struct
import threading
import time


def checksum(data):
    if len(data) % 2:
        data += b'\x00'
    s = sum(struct.unpack('!%dH' % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return (~s) & 0xFFFF


def build_echo_request(ident, seq):
    header = struct.pack('!BBHHH', 8, 0, 0, ident, seq)
    payload = b'unit-cps-icmp'
    chksum = checksum(header + payload)
    return struct.pack('!BBHHH', 8, 0, chksum, ident, seq) + payload


def ping_once(ip, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    s.settimeout(timeout)
    ident = int(time.time() * 1000) & 0xFFFF
    seq = 1
    packet = build_echo_request(ident, seq)
    start = time.time()
    s.sendto(packet, (ip, 0))
    try:
        data, _ = s.recvfrom(1024)
        icmp_offset = (data[0] & 0x0F) * 4
        icmp = data[icmp_offset:icmp_offset + 8]
        t, code, chk, rid, rseq = struct.unpack('!BBHHH', icmp)
        if t == 0 and rid == ident:
            return True, (time.time() - start) * 1000
    except socket.timeout:
        return False, None
    finally:
        s.close()
    return False, None


def scan_range(start_ip, end_ip, threads=50):
    start = ipaddress.IPv4Address(start_ip)
    end = ipaddress.IPv4Address(end_ip)
    targets = [str(ipaddress.IPv4Address(i)) for i in range(int(start), int(end) + 1)]
    lock = threading.Lock()
    results = []
    idx = 0

    def worker():
        nonlocal idx
        while True:
            with lock:
                if idx >= len(targets):
                    return
                ip = targets[idx]
                idx += 1
            ok, rtt = ping_once(ip)
            if ok:
                with lock:
                    results.append((ip, rtt))
                    print(f"[UP ] {ip} {rtt:.2f}ms")

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return results


def main():
    parser = argparse.ArgumentParser(description='ICMP scan: scanhost Start_IP End_IP')
    parser.add_argument('start_ip')
    parser.add_argument('end_ip')
    parser.add_argument('--threads', type=int, default=50)
    args = parser.parse_args()

    print(f"ICMP scan {args.start_ip} -> {args.end_ip}")
    res = scan_range(args.start_ip, args.end_ip, args.threads)
    print(f"Total alive: {len(res)}")


if __name__ == '__main__':
    main()
