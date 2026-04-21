# 基于CPS的智能家居原型（演示）

说明：这是一个最小可运行的原型，用于演示设备发现（UDP 广播）与可靠数据上报（TCP），以及服务器端的简单策略引擎。

网络课程增强点：
- 应用层序号 `seq` 与 ACK（观测可靠传输行为）
- 应用层校验和 `checksum`（差错检测）
- 端到端时延估计 `send_ts`（性能指标）
- 丢包/重复包/校验错误统计（网络状态量化）

主要文件：
- `design.md`：设计说明与思辨（协议选型、架构、测试用例）。
- `server.py`：中央服务器，包含 UDP 发现监听与 TCP 数据接收+策略回复。
- `device_sim.py`：设备模拟器，周期广播发现报文并通过 TCP 上报 JSON 数据。
- `requirements.txt`：依赖（仅标准库，可空）。
- `使用说明.md`：中文使用文档与命令列表。

**网络诊断工具（优化版）**：
- `icmp_scan.py`：ICMP 主机发现，支持多线程并发扫描（100 倍性能提升）
  - 用法：`python icmp_scan.py 192.168.1.0/24`
  - 特性：实时进度、延迟统计、快速网段扫描
  
- `tcp_probe.py`：TCP 连通性探测，支持单端口/范围/列表扫描
  - 用法：`python tcp_probe.py 127.0.0.1 22,80,443`  或  `python tcp_probe.py 127.0.0.1 10000-10010`
  - 特性：并发扫描（50 线程）、详细状态、延迟测量
  
- `traffic_stats.py`：网络流量统计，详细的连接状态分类
  - 用法：`python traffic_stats.py`
  - 特性：TCP/UDP 统计、连接状态分布、本地/远程分类
  
- `arp_table.py`：ARP 表查看脚本。

运行（Windows）：
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
# 在另一个终端运行模拟设备：
python device_sim.py
```

端口说明：
- UDP 广播 discovery port: 10000
- TCP 数据端口: 10001

测试建议：先启动 `server.py`，再启动 `device_sim.py`，观察服务器控制台输出与设备收到的命令。
