"""测试 get_report_file 拉取板块文件。"""
import sys
import pathlib

# 添加 src 到 path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from xmtdx import TdxClient

def main():
    print("正在拉取 block_gn.dat (使用 get_report_file) ...")
    with TdxClient.from_best_host() as c:
        data = c.get_report_file("block_gn.dat")
        print(f"成功拉取 {len(data)} 字节。")
        if data:
            print(f"前 16 字节 hex: {data[:16].hex()}")

if __name__ == "__main__":
    main()
