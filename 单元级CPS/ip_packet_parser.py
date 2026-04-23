import argparse
import socket
import struct
import time


def parse_ip_header(packet):
    ver_ihl = packet[0]
    version = ver_ihl >> 4
    ihl = (ver_ihl & 0x0F) * 4
    total_len = struct.unpack('!H', packet[2:4])[0]
    ident = struct.unpack('!H', packet[4:6])[0]
    flags_frag = struct.unpack('!H', packet[6:8])[0]
    flags = flags_frag >> 13
    frag_offset = flags_frag & 0x1FFF
    ttl = packet[8]
    proto = packet[9]
    checksum = struct.unpack('!H', packet[10:12])[0]
    src = socket.inet_ntoa(packet[12:16])
    dst = socket.inet_ntoa(packet[16:20])
    return {
        'version': version,
        'ihl': ihl,
        'total_len': total_len,
        'id': ident,
        'flags': flags,
        'frag_offset': frag_offset,
        'ttl': ttl,
        'protocol': proto,
        'checksum': checksum,
        'src': src,
        'dst': dst
    }


def capture_and_parse(count, log_path):
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
    local_ip = get_local_ip()
    s.bind((local_ip, 0))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    s.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)

    logs = []
    try:
        for _ in range(count):
            pkt = s.recvfrom(65535)[0]
            if len(pkt) < 20:
                continue
            info = parse_ip_header(pkt)
            line = f"{int(time.time())} {info}"
            logs.append(line)
            print(line)
    finally:
        s.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        s.close()

    if log_path:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(logs))


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser(description='Capture and parse IP packets')
    parser.add_argument('--count', type=int, default=5)
    parser.add_argument('--log', default='ip_parse.log')
    args = parser.parse_args()
    capture_and_parse(args.count, args.log)


if __name__ == '__main__':
    main()
