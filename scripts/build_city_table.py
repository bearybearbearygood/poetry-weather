#!/usr/bin/env python3
"""生成全国城市经纬度表 cities_cn.json

数据来源：GeoNames 中国地名库（CC-BY-4.0）
  https://download.geonames.org/export/dump/CN.zip

用法：
  1. 下载并解压，得到 CN.txt（约 126MB）
  2. python3 scripts/build_city_table.py /path/to/CN.txt
  3. 输出到项目根目录 cities_cn.json（约 760KB）

为什么不直接用 Open-Meteo 的地理编码接口：
  它的中国数据只到市镇级，区县几乎缺失，且同名地点容易混淆
  （输入「丽江」会解析到湖南的一个镇）。内置表既准确又不依赖网络。
"""

import collections
import json
import os
import sys

# 行政级别，数字越小越优先
ORDER = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPLA4": 4, "PPL": 5}
KEEP = set(ORDER)

SUFFIX = ("特别行政区", "自治州", "地区", "市", "区", "县", "旗", "盟")

# 这些词说明是居民点/村委会，不是城市名
BAD_WORDS = ("居委会", "村委会", "社区", "街道", "村", "组")

# 村民点（PPL）人口低于此值直接丢掉，否则几十万个村名会淹没城市
MIN_PPL_POPULATION = 50000

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cities_cn.json")


def is_chinese(s):
    return all("\u4e00" <= c <= "\u9fff" or c == "·" for c in s)


def build(geonames_path):
    best = {}
    stats = collections.Counter()

    with open(geonames_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split("\t")
            if len(parts) < 15:
                continue
            if parts[6] != "P" or parts[7] not in KEEP:
                continue

            code = parts[7]
            population = int(parts[14]) if parts[14] else 0

            if code == "PPL" and population < MIN_PPL_POPULATION:
                continue

            try:
                lat, lng = float(parts[4]), float(parts[5])
            except ValueError:
                continue

            # 中国大陆范围粗校验
            if not (3.0 <= lat <= 54.0 and 73.0 <= lng <= 136.0):
                continue

            # 从 alternatenames 里挑中文名，并补一个去后缀的写法
            names = set()
            for alt in parts[3].split(","):
                alt = alt.strip()
                if not alt or not is_chinese(alt) or len(alt) > 10:
                    continue
                if any(bad in alt for bad in BAD_WORDS):
                    continue
                names.add(alt)
                for suf in SUFFIX:
                    if alt.endswith(suf) and len(alt) - len(suf) >= 2:
                        names.add(alt[: -len(suf)])
                        break

            # 同名取行政级别更高、人口更多的那个
            rank = (ORDER.get(code, 9), -population)
            for name in names:
                current = best.get(name)
                if current is None or rank < current[0]:
                    best[name] = (rank, [lng, lat])
                    stats[code] += 1

    return {k: v[1] for k, v in sorted(best.items())}, stats


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"找不到文件：{path}")
        sys.exit(1)

    table, stats = build(path)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"已生成 {OUTPUT}")
    print(f"  条目数：{len(table)}")
    print(f"  文件大小：{size_kb:.0f} KB")
    print(f"  来源分布：{dict(stats.most_common())}")

    for probe in ("丽江", "朝阳", "朝阳区", "喀什", "杭州"):
        print(f"  抽查 {probe}: {table.get(probe)}")


if __name__ == "__main__":
    main()
