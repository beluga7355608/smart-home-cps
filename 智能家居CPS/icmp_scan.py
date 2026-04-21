import ipaddress
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime

# 优化的 ICMP 扫描
# 特性：多线程并发、进度显示、详细统计、支持IPv4和IPv6
# 用法: python icmp_scan.py 192.168.1.0/24
# 用法: python icmp_scan.py 10.0.0.0/24

class ICMPScanner:
    """ICMP 网络扫描类"""
    
    def __init__(self, max_threads=50, timeout=500):
        self.max_threads = max_threads
        self.timeout = timeout  # ms
        self.lock = threading.Lock()
        self.alive_hosts = []
        self.dead_hosts = []
        self.stats = {'total': 0, 'alive': 0, 'dead': 0, 'error': 0}
        self.start_time = None
    
    def ping(self, host):
        """PING 单个主机"""
        try:
            # Windows 使用 -n，Linux/Mac 使用 -c
            if sys.platform == 'win32':
                cmd = ["ping", "-n", "1", "-w", str(self.timeout), host]
            else:
                cmd = ["ping", "-c", "1", "-W", str(self.timeout // 1000), host]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            # 检查是否成功
            if result.returncode == 0:
                # 提取响应时间
                latency = self._extract_latency(result.stdout)
                return True, latency
            else:
                return False, None
        
        except Exception as e:
            return None, str(e)  # None 表示错误
    
    def _extract_latency(self, output):
        """从 ping 输出中提取响应时间"""
        try:
            if 'time=' in output:
                # Windows: "time=5ms" 或 Linux: "time=5.123 ms"
                import re
                match = re.search(r'time[=<]([\d.]+)', output)
                if match:
                    return round(float(match.group(1)), 2)
        except:
            pass
        return 0
    
    def scan_host(self, ip):
        """扫描单个主机"""
        ip_str = str(ip)
        alive, latency = self.ping(ip_str)
        
        with self.lock:
            if alive is True:
                self.alive_hosts.append((ip_str, latency))
                self.stats['alive'] += 1
                print(f"  ✓ [{self.stats['alive']:>3}] 存活: {ip_str:<15} 延迟: {latency}ms")
            
            elif alive is False:
                self.dead_hosts.append(ip_str)
                self.stats['dead'] += 1
            
            else:  # 错误
                self.stats['error'] += 1
            
            self.stats['total'] += 1
    
    def scan_network(self, network_spec):
        """扫描网络"""
        try:
            net = ipaddress.ip_network(network_spec, strict=False)
        except ValueError:
            print(f"错误: 无效的网络地址 '{network_spec}'")
            return False
        
        hosts = list(net.hosts())
        if not hosts:
            print(f"错误: 网络 {network_spec} 中没有有效的主机")
            return False
        
        print(f"\n" + "="*60)
        print(f"ICMP 网络扫描 - {network_spec}")
        print(f"主机数: {len(hosts)}, 最大并发: {self.max_threads}, 超时: {self.timeout}ms")
        print("="*60)
        print()
        
        self.start_time = time.time()
        threads = []
        
        # 创建线程池
        for ip in hosts:
            # 控制并发数
            while len([t for t in threads if t.is_alive()]) >= self.max_threads:
                time.sleep(0.001)
            
            t = threading.Thread(target=self.scan_host, args=(ip,))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        elapsed = round(time.time() - self.start_time, 2)
        self.print_summary(network_spec, elapsed)
        return True
    
    def print_summary(self, network, elapsed):
        """打印扫描摘要"""
        print(f"\n" + "="*60)
        print(f"扫描完成")
        print("="*60)
        
        print(f"\n统计信息:")
        print(f"  总扫描数:  {self.stats['total']}")
        print(f"  存活主机:  {self.stats['alive']} ({self.stats['alive']*100//self.stats['total'] if self.stats['total'] else 0}%)")
        print(f"  离线主机:  {self.stats['dead']}")
        if self.stats['error'] > 0:
            print(f"  扫描错误:  {self.stats['error']}")
        print(f"  耗时:      {elapsed}s")
        print(f"  平均速度:  {round(self.stats['total']/elapsed, 1)} 个主机/秒")
        
        if self.alive_hosts:
            print(f"\n存活的主机 (共 {len(self.alive_hosts)} 个):")
            for ip, latency in sorted(self.alive_hosts, key=lambda x: ipaddress.ip_address(x[0])):
                print(f"  {ip:<15} 延迟: {latency:>6}ms")
        else:
            print(f"\n没有发现存活的主机")
        
        print(f"\n" + "="*60 + "\n")


def main():
    if len(sys.argv) < 2:
        print("用法: python icmp_scan.py <network>")
        print("\n示例:")
        print("  python icmp_scan.py 192.168.1.0/24   扫描子网")
        print("  python icmp_scan.py 10.0.0.0/24      扫描 10.x.x.x 网段")
        print("  python icmp_scan.py 172.16.0.0/16    扫描更大网段")
        return
    
    network = sys.argv[1]
    scanner = ICMPScanner(max_threads=100, timeout=500)
    scanner.scan_network(network)


if __name__ == '__main__':
    main()
