import subprocess

# ARP 表查看（用于ARP层观察）
# 用法: python arp_table.py

def main():
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True)
        print(out.stdout)
    except Exception as e:
        print("arp failed:", e)


if __name__ == '__main__':
    main()
