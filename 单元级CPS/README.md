# 单元级CPS（SDN单元模块）

本目录在系统级CPS基础上拆分出单元级CPS模块，覆盖ARP、TCP、ICMP、IP监控与解析、TCP流分析与自定义协议设计。

## 目录结构
- arp_unit.py：ARP帧结构设计、构造与解析（Windows标准库下用SendARP触发解析）。
- tcp_segment_demo.py：TCP报文段结构设计与“数据字段”演示。
- icmp_scan.py：ICMP回送请求/应答扫描活动主机。
- ip_traffic_monitor.py：按源地址统计IP包数量。
- ip_packet_parser.py：捕获并解析IP数据包。
- tcp_flow_analyzer.py：解析pcap并分析TCP序号/确认号/控制位/窗口。
- reliable_udp.py：基于UDP的有序传输协议示例。
- 实验说明.md：运行步骤与命令行示例。
- 文字说明.md：协议结构与实现说明。

## 重要提示
- 部分功能依赖原始套接字（raw socket），需要以管理员权限运行。
- Windows 标准库无法直接发送以太网帧；ARP发送采用 `SendARP` 触发ARP解析，帧构造与解析以“字节级结构”演示为主。
