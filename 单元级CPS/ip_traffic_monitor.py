import argparse
import collections
import socket
import time


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    finally:
        s.close()


def monitor(duration, out_csv):
    local_ip = get_local_ip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
    sock.bind((local_ip, 0))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)

    counter = collections.Counter()
    start = time.time()
    try:
        while time.time() - start < duration:
            packet = sock.recvfrom(65535)[0]
            if len(packet) < 20:
                continue
            src = socket.inet_ntoa(packet[12:16])
            counter[src] += 1
    finally:
        sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        sock.close()

    lines = ['src_ip,count']
    for ip, cnt in counter.most_common():
        lines.append(f"{ip},{cnt}")
    with open(out_csv, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Saved: {out_csv}")
    for ip, cnt in counter.most_common(10):
        bar = '#' * min(50, cnt)
        print(f"{ip:<15} {cnt:>6} {bar}")


def main():
    parser = argparse.ArgumentParser(description='Monitor IP packets and count by source IP')
    parser.add_argument('--duration', type=int, default=10)
    parser.add_argument('--out', default='ip_stats.csv')
    args = parser.parse_args()
    monitor(args.duration, args.out)


if __name__ == '__main__':
    main()
