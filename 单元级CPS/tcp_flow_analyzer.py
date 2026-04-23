import argparse
import socket
import struct


def read_pcap(path):
    with open(path, 'rb') as f:
        global_hdr = f.read(24)
        if len(global_hdr) != 24:
            raise ValueError('Invalid pcap')
        magic = struct.unpack('I', global_hdr[:4])[0]
        if magic not in (0xa1b2c3d4, 0xd4c3b2a1):
            raise ValueError('Unsupported pcap format')
        endian = '<' if magic == 0xd4c3b2a1 else '>'
        while True:
            hdr = f.read(16)
            if not hdr:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + 'IIII', hdr)
            data = f.read(incl_len)
            yield ts_sec + ts_usec / 1_000_000, data


def parse_tcp_packet(pkt):
    if len(pkt) < 14 + 20:
        return None
    eth_type = struct.unpack('!H', pkt[12:14])[0]
    if eth_type != 0x0800:
        return None
    ip = pkt[14:]
    ver_ihl = ip[0]
    ihl = (ver_ihl & 0x0F) * 4
    proto = ip[9]
    if proto != 6:
        return None
    src_ip = socket.inet_ntoa(ip[12:16])
    dst_ip = socket.inet_ntoa(ip[16:20])
    tcp = ip[ihl:]
    if len(tcp) < 20:
        return None
    src_port, dst_port, seq, ack, off_res, flags, window = struct.unpack('!HHLLBBH', tcp[:16])
    offset = (off_res >> 4) * 4
    payload = tcp[offset:]
    return {
        'src_ip': src_ip,
        'dst_ip': dst_ip,
        'src_port': src_port,
        'dst_port': dst_port,
        'seq': seq,
        'ack': ack,
        'flags': flags,
        'window': window,
        'payload': payload
    }


def flags_str(flags):
    names = []
    if flags & 0x02:
        names.append('SYN')
    if flags & 0x10:
        names.append('ACK')
    if flags & 0x01:
        names.append('FIN')
    if flags & 0x04:
        names.append('RST')
    if flags & 0x08:
        names.append('PSH')
    if flags & 0x20:
        names.append('URG')
    return '|'.join(names) if names else '-'


def flow_key(pkt):
    return f"{pkt['src_ip']}:{pkt['src_port']}-{pkt['dst_ip']}:{pkt['dst_port']}"


def analyze(path, flow=None):
    flows = {}
    for ts, raw in read_pcap(path):
        pkt = parse_tcp_packet(raw)
        if not pkt:
            continue
        key = flow_key(pkt)
        flows.setdefault(key, []).append((ts, pkt))

    if not flow:
        print('Flows:')
        for k in flows.keys():
            print('  ' + k)
        return

    if flow not in flows:
        print('Flow not found')
        return

    events = flows[flow]
    print(f"Analyze flow: {flow}")
    syn = synack = ack = None
    fin1 = fin2 = None
    for ts, p in events:
        fl = flags_str(p['flags'])
        if fl == 'SYN' and syn is None:
            syn = (ts, p)
        elif fl == 'SYN|ACK' and synack is None:
            synack = (ts, p)
        elif fl == 'ACK' and syn and synack and ack is None:
            ack = (ts, p)
        elif 'FIN' in fl and fin1 is None:
            fin1 = (ts, p)
        elif 'FIN' in fl and fin1 and fin2 is None:
            fin2 = (ts, p)

    if syn:
        print(f"SYN: seq={syn[1]['seq']} ack={syn[1]['ack']} win={syn[1]['window']}")
    if synack:
        print(f"SYN-ACK: seq={synack[1]['seq']} ack={synack[1]['ack']} win={synack[1]['window']}")
    if ack:
        print(f"ACK: seq={ack[1]['seq']} ack={ack[1]['ack']} win={ack[1]['window']}")
    if fin1:
        print(f"FIN-1: seq={fin1[1]['seq']} ack={fin1[1]['ack']} win={fin1[1]['window']}")
    if fin2:
        print(f"FIN-2: seq={fin2[1]['seq']} ack={fin2[1]['ack']} win={fin2[1]['window']}")

    print('Segments:')
    for ts, p in events:
        fl = flags_str(p['flags'])
        print(f"{ts:.6f} {p['src_ip']}:{p['src_port']} -> {p['dst_ip']}:{p['dst_port']} {fl} seq={p['seq']} ack={p['ack']} win={p['window']} len={len(p['payload'])}")
        if p['payload']:
            try:
                print('  payload:', p['payload'].decode('utf-8', errors='replace'))
            except Exception:
                print('  payload:', p['payload'])


def main():
    parser = argparse.ArgumentParser(description='Analyze TCP flow from pcap')
    parser.add_argument('--pcap', required=True)
    parser.add_argument('--flow')
    args = parser.parse_args()
    analyze(args.pcap, args.flow)


if __name__ == '__main__':
    main()
