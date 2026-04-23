import argparse
import binascii
import ctypes
import socket
import struct


def mac_str_to_bytes(mac):
    parts = mac.split(':')
    if len(parts) != 6:
        raise ValueError('MAC must be like 00:11:22:33:44:55')
    return bytes(int(p, 16) for p in parts)


def mac_bytes_to_str(b):
    return ':'.join(f"{x:02x}" for x in b)


def build_arp_payload(src_mac, src_ip, dst_mac, dst_ip, opcode=1):
    htype = 1
    ptype = 0x0800
    hlen = 6
    plen = 4
    header = struct.pack('!HHBBH', htype, ptype, hlen, plen, opcode)
    return header + src_mac + socket.inet_aton(src_ip) + dst_mac + socket.inet_aton(dst_ip)


def build_ethernet_header(dst_mac, src_mac, eth_type=0x0806):
    return dst_mac + src_mac + struct.pack('!H', eth_type)


def build_arp_frame(src_mac, src_ip, dst_mac, dst_ip, opcode=1):
    eth = build_ethernet_header(dst_mac, src_mac, 0x0806)
    arp = build_arp_payload(src_mac, src_ip, dst_mac, dst_ip, opcode)
    return eth + arp


def parse_arp_frame(frame):
    if len(frame) >= 42:
        eth_dst = mac_bytes_to_str(frame[0:6])
        eth_src = mac_bytes_to_str(frame[6:12])
        eth_type = struct.unpack('!H', frame[12:14])[0]
        arp = frame[14:42]
    else:
        eth_dst = eth_src = None
        eth_type = None
        arp = frame

    if len(arp) < 28:
        raise ValueError('ARP payload too short')

    htype, ptype, hlen, plen, opcode = struct.unpack('!HHBBH', arp[0:8])
    src_mac = mac_bytes_to_str(arp[8:14])
    src_ip = socket.inet_ntoa(arp[14:18])
    dst_mac = mac_bytes_to_str(arp[18:24])
    dst_ip = socket.inet_ntoa(arp[24:28])

    return {
        'eth_dst': eth_dst,
        'eth_src': eth_src,
        'eth_type': eth_type,
        'htype': htype,
        'ptype': ptype,
        'hlen': hlen,
        'plen': plen,
        'opcode': opcode,
        'src_mac': src_mac,
        'src_ip': src_ip,
        'dst_mac': dst_mac,
        'dst_ip': dst_ip
    }


def send_arp_windows(target_ip):
    ip_addr = struct.unpack('!I', socket.inet_aton(target_ip))[0]
    mac_buf = ctypes.create_string_buffer(6)
    buf_len = ctypes.c_ulong(6)
    SendARP = ctypes.windll.Iphlpapi.SendARP
    res = SendARP(ctypes.c_ulong(ip_addr), ctypes.c_ulong(0), mac_buf, ctypes.byref(buf_len))
    if res != 0:
        raise OSError(f'SendARP failed: {res}')
    return mac_bytes_to_str(mac_buf.raw[:buf_len.value])


def cmd_send(args):
    mac = send_arp_windows(args.ip)
    print(f"IP {args.ip} -> MAC {mac}")


def cmd_build(args):
    frame = build_arp_frame(
        mac_str_to_bytes(args.src_mac),
        args.src_ip,
        mac_str_to_bytes(args.dst_mac),
        args.dst_ip,
        opcode=args.opcode
    )
    print(binascii.hexlify(frame).decode('ascii'))


def cmd_parse(args):
    raw = binascii.unhexlify(args.hex.replace(' ', ''))
    info = parse_arp_frame(raw)
    for k, v in info.items():
        print(f"{k}: {v}")


def main():
    parser = argparse.ArgumentParser(description='ARP frame builder/parser (Windows stdlib)')
    sub = parser.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('send', help='SendARP to resolve MAC')
    s.add_argument('ip')
    s.set_defaults(func=cmd_send)

    b = sub.add_parser('build', help='Build Ethernet+ARP frame')
    b.add_argument('--src-mac', required=True)
    b.add_argument('--src-ip', required=True)
    b.add_argument('--dst-mac', required=True)
    b.add_argument('--dst-ip', required=True)
    b.add_argument('--opcode', type=int, default=1)
    b.set_defaults(func=cmd_build)

    p = sub.add_parser('parse', help='Parse Ethernet+ARP or ARP payload hex')
    p.add_argument('--hex', required=True)
    p.set_defaults(func=cmd_parse)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
