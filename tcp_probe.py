import socket
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime

# 优化的 TCP 连通性探测
# 特性：支持并发扫描、端口范围、详细信息、连接统计
# 用法1: python tcp_probe.py 127.0.0.1 10001          (单个端口)
# 用法2: python tcp_probe.py 127.0.0.1 10000-10010   (端口范围)
# 用法3: python tcp_probe.py 192.168.1.1 22,80,443   (多个端口)

class TCPProbe:
    """TCP 连通性探测类"""
    
    def __init__(self, timeout=2, max_threads=20):
        self.timeout = timeout
        self.max_threads = max_threads
        self.lock = threading.Lock()
        self.results = defaultdict(list)  # port -> [status, info]
        self.stats = {'success': 0, 'failed': 0, 'total': 0}
    
    def parse_ports(self, port_spec):
        """解析端口规范"""
        ports = []
        try:
            # 单个端口
            if ',' not in port_spec and '-' not in port_spec:
                ports.append(int(port_spec))
            # 端口范围: 10000-10010
            elif '-' in port_spec:
                start, end = map(int, port_spec.split('-'))
                ports = list(range(start, end + 1))
            # 多个端口: 22,80,443
            else:
                ports = [int(p.strip()) for p in port_spec.split(',')]
        except ValueError:
            print(f"错误: 端口格式不正确 '{port_spec}'")
            return []
        
        return [p for p in ports if 1 <= p <= 65535]
    
    def probe_port(self, host, port):
        """探测单个端口"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        
        start_time = time.time()
        info = {'port': port, 'status': 'closed', 'latency': 0, 'error': None}
        
        try:
            sock.connect((host, port))
            info['status'] = 'open'
            info['latency'] = round((time.time() - start_time) * 1000, 2)  # ms
            
            with self.lock:
                self.results[port].append(('open', info))
                self.stats['success'] += 1
        
        except socket.timeout:
            info['status'] = 'timeout'
            info['error'] = 'Connection timeout'
            with self.lock:
                self.results[port].append(('timeout', info))
                self.stats['failed'] += 1
        
        except ConnectionRefusedError:
            info['status'] = 'refused'
            info['error'] = 'Connection refused'
            with self.lock:
                self.results[port].append(('refused', info))
                self.stats['failed'] += 1
        
        except Exception as e:
            info['status'] = 'error'
            info['error'] = str(e)
            with self.lock:
                self.results[port].append(('error', info))
                self.stats['failed'] += 1
        
        finally:
            try:
                sock.close()
            except:
                pass
            
            with self.lock:
                self.stats['total'] += 1
    
    def scan(self, host, ports):
        """并发扫描多个端口"""
        if not ports:
            print("错误: 没有有效的端口")
            return False
        
        threads = []
        print(f"\n开始扫描 {host}，共 {len(ports)} 个端口")
        print(f"超时设置: {self.timeout}s，最大并发: {self.max_threads}\n")
        
        start_time = time.time()
        
        # 创建线程池
        for port in ports:
            # 控制并发数
            while len([t for t in threads if t.is_alive()]) >= self.max_threads:
                time.sleep(0.01)
            
            t = threading.Thread(target=self.probe_port, args=(host, port))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        elapsed = round(time.time() - start_time, 2)
        return elapsed
    
    def print_summary(self, host):
        """打印扫描结果"""
        open_ports = [port for port, results in self.results.items() if results and results[0][0] == 'open']
        
        print("\n" + "="*60)
        print(f"TCP 扫描结果 - {host}")
        print("="*60)
        
        print(f"\n统计信息:")
        print(f"  总扫描数:  {self.stats['total']}")
        print(f"  开放端口:  {self.stats['success']}")
        print(f"  关闭端口:  {self.stats['failed']}")
        
        if open_ports:
            print(f"\n开放的端口:")
            for port in sorted(open_ports):
                if self.results[port]:
                    status, info = self.results[port][0]
                    print(f"  [{status.upper():^8}] 端口 {port:5} - 响应时间: {info['latency']}ms")
        else:
            print(f"\n没有发现开放的端口")
        
        print(f"\n所有结果详情:")
        for port in sorted(self.results.keys()):
            if self.results[port]:
                status, info = self.results[port][0]
                print(f"  端口 {port:5}: [{status.upper():^8}] ", end="")
                if info['error']:
                    print(f"错误: {info['error']}")
                else:
                    print(f"延迟: {info['latency']}ms")
        
        print("="*60 + "\n")


def main():
    if len(sys.argv) < 3:
        print("用法:")
        print("  python tcp_probe.py <host> <port>              单个端口")
        print("  python tcp_probe.py <host> <port1-port2>       端口范围")
        print("  python tcp_probe.py <host> <port1,port2,...>   多个端口")
        print("\n示例:")
        print("  python tcp_probe.py 127.0.0.1 10001")
        print("  python tcp_probe.py 127.0.0.1 10000-10010")
        print("  python tcp_probe.py 192.168.1.1 22,80,443,3306")
        return
    
    host = sys.argv[1]
    port_spec = sys.argv[2]
    
    probe = TCPProbe(timeout=2, max_threads=50)
    ports = probe.parse_ports(port_spec)
    
    if ports:
        elapsed = probe.scan(host, ports)
        probe.print_summary(host)
        print(f"扫描耗时: {elapsed}s")
    else:
        print("错误: 无法解析端口")


if __name__ == '__main__':
    main()
