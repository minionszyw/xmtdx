"""通达信行业配置文件 (tdxhy.cfg) 解析器。"""

def parse_tdxhy_cfg(content: bytes) -> dict[str, tuple[str, str]]:
    """解析 tdxhy.cfg 字节内容。
    
    返回字典: { "code": (tdx_industry, sw_industry), ... }
    """
    results = {}
    try:
        text = content.decode("gbk", errors="replace")
        for line in text.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3:
                # 格式: 市场|代码|行业1|||行业2
                # 我们只关心 A 股 6 位代码
                code = parts[1]
                if len(code) == 6:
                    tdx_ind = parts[2]
                    sw_ind = parts[5] if len(parts) >= 6 else ""
                    results[code] = (tdx_ind, sw_ind)
    except Exception:
        pass
    return results
