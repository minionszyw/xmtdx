"""验证大文件拉取。"""
import sys
import pathlib
import zipfile
import io

# 添加 src 到 path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from xmtdx import TdxClient

def main():
    print("正在拉取 base_info.zip ...")
    with TdxClient.from_best_host() as c:
        data = c.get_report_file("base_info.zip")
        print(f"成功拉取 {len(data)} 字节。")
        
        if not data:
            print("失败：返回数据为空。")
            return
            
        # 尝试作为 zip 打开验证
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                files = z.namelist()
                print(f"Zip 文件包含 {len(files)} 个文件：{files[:5]}...")
                # 检查是否包含 base_info.txt
                if any("base_info.txt" in f for f in files):
                    print("验证成功：包含 base_info.txt")
        except Exception as e:
            print(f"Zip 校验失败: {e}")
            # 打印前 16 字节 hex
            print(f"Header hex: {data[:16].hex()}")

if __name__ == "__main__":
    main()
