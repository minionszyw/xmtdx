"""实测板块信息获取。"""
import sys
import pathlib

# 添加 src 到 path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from xmtdx import TdxClient

def main():
    print("正在寻找最优服务器...")
    try:
        with TdxClient.from_best_host() as c:
            print(f"已连接到: {c._host}")
            
            # 尝试获取概念板块 (block_gn.dat)
            filename = "block_gn.dat"
            print(f"正在获取 {filename} ...")
            blocks = c.get_block_info(filename)
            
            print(f"成功获取 {len(blocks)} 个板块。")
            
            # 打印前 5 个板块及其前 3 个股票
            for b in blocks[:5]:
                print(f"板块名称: {b.name:<12} 股票数: {b.count:<5} 样例: {b.codes[:3]}")
                
            if not blocks:
                print("警告：未获取到任何板块数据。")
                
    except Exception as e:
        print(f"实测失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
