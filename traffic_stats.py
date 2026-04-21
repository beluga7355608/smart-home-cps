import subprocess
import sys
import re
from collections import defaultdict
from datetime import datetime

# 优化的流量统计模块
# 特性：跨平台支持、详细的连接统计、按状态分类、按地址分类
# 用法: python traffic_stats.py

class TrafficStats:
    """网络流量统计类"""
    
    def __init__(self):
        self.stats = {
            'tcp_total': 0,
            'udp_total': 0,
            'tcp_by_state': defaultdict(int),
            'tcp_established': 0,
            'tcp_listening': 0,
            'local_connections': 0,
            'remote_connections': 0,
        }
    
    def parse_netstat_windows(self, output):
        """解析 Windows netstat 输出"""
        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            if not line or 'Proto' in line:
                continue
            
            parts = line.split()
            if not parts:
                continue
            
            proto = parts[0].upper()
            
            if proto == 'TCP':
                self.stats['tcp_total'] += 1
                # 获取连接状态（最后一个字段）
                state = parts[-1] if len(parts) > 3 else 'UNKNOWN'
                self.stats['tcp_by_state'][state] += 1
                
                if state == 'ESTABLISHED':
                    self.stats['tcp_established'] += 1
                elif state == 'LISTENING':
                    self.stats['tcp_listening'] += 1
                
                # 分类本地和远程连接
                if len(parts) >= 2:
                    addr = parts[1]
                    if self._is_local_addr(addr):
                        self.stats['local_connections'] += 1
                    else:
                        self.stats['remote_connections'] += 1
            
            elif proto == 'UDP':
                self.stats['udp_total'] += 1
    
    def parse_netstat_linux(self, output):
        """解析 Linux netstat 输出"""
        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Proto'):
                continue
            
            parts = line.split()
            if not parts:
                continue
            
            proto = parts[0].lower()
            
            if proto == 'tcp':
                self.stats['tcp_total'] += 1
                state = parts[-1] if len(parts) >= 6 else 'UNKNOWN'
                self.stats['tcp_by_state'][state] += 1
                
                if state == 'ESTABLISHED':
                    self.stats['tcp_established'] += 1
                elif state == 'LISTEN':
                    self.stats['tcp_listening'] += 1
            
            elif proto == 'udp':
                self.stats['udp_total'] += 1
    
    def _is_local_addr(self, addr):
        """判断地址是否为本地地址"""
        return addr.startswith('127.') or addr.startswith('localhost') or ':' in addr
    
    def collect_stats(self):
        """收集网络统计信息"""
        try:
            # 根据操作系统调用不同的 netstat 命令
            if sys.platform == 'win32':
                cmd = ["netstat", "-ano"]
            else:
                cmd = ["netstat", "-tn"]  # Linux/Mac
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                if sys.platform == 'win32':
                    self.parse_netstat_windows(result.stdout)
                else:
                    self.parse_netstat_linux(result.stdout)
            else:
                print(f"错误: netstat 命令失败 (返回码: {result.returncode})")
                return False
            
            return True
        
        except FileNotFoundError:
            print("错误: netstat 命令未找到")
            return False
        except subprocess.TimeoutExpired:
            print("错误: netstat 命令超时")
            return False
        except Exception as e:
            print(f"错误: {e}")
            return False
    
    def print_summary(self):
        """打印统计摘要"""
        print("\n" + "="*50)
        print(f"网络流量统计 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*50)
        
        print(f"\n连接总数统计:")
        print(f"  TCP 连接总数:     {self.stats['tcp_total']:>6}")
        print(f"  UDP 端点总数:     {self.stats['udp_total']:>6}")
        print(f"  总计:            {self.stats['tcp_total'] + self.stats['udp_total']:>6}")
        
        print(f"\nTCP 连接状态分布:")
        print(f"  已建立(ESTABLISHED): {self.stats['tcp_established']:>6}")
        print(f"  监听(LISTENING):    {self.stats['tcp_listening']:>6}")
        
        if self.stats['tcp_by_state']:
            print(f"\n  所有状态分布:")
            for state, count in sorted(self.stats['tcp_by_state'].items(), key=lambda x: x[1], reverse=True):
                print(f"    {state:<20} {count:>6}")
        
        print(f"\n连接分类:")
        print(f"  本地连接:  {self.stats['local_connections']:>6}")
        print(f"  远程连接:  {self.stats['remote_connections']:>6}")
        
        print("="*50 + "\n")
    
    def get_dict(self):
        """返回统计数据字典"""
        return dict(self.stats)


def main():
    """主函数"""
    stats = TrafficStats()
    
    if stats.collect_stats():
        stats.print_summary()
        return stats.get_dict()
    else:
        return None


if __name__ == '__main__':
    main()
