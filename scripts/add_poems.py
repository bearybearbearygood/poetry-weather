#!/usr/bin/env python3
"""向诗词库追加诗词（带校验）

用法:
    python3 add_poems.py <additions.json> [--dry-run]

additions.json 格式（顶层 key 为天气类别）:
    {
      "clear": [
        {"title": "秋词", "dynasty": "唐", "author": "刘禹锡",
         "lines": ["晴空一鹤排云上，", "便引诗情到碧霄。"], "season": "autumn"}
      ]
    }

校验规则（与墨水屏渲染约束对齐）:
    1. 必须有 title / dynasty / author / lines / season 五个字段
    2. lines 恰好 2 行（dot_api.py 只取 lines[:2]）
    3. 每行 5~9 个字符（含标点）；超出 9 会顶破 296px 屏宽（字号 20）
    4. season 取值 ∈ {spring, summer, autumn, winter, all}
    5. 同一类别内不允许出现重复的 title|author

注意：新增诗词后必须重跑 scripts/subset_font.py 重新生成子集字体，
否则新字在墨水屏上会渲染成空白。
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
POETRY_PATH = os.path.join(PROJECT_DIR, "poetry.json")

VALID_SEASONS = {"spring", "summer", "autumn", "winter", "all"}
REQUIRED_FIELDS = ("title", "dynasty", "author", "lines", "season")
MIN_LINE, MAX_LINE = 5, 9


def key_of(p):
    return f'{p.get("title", "")}|{p.get("author", "")}'


def validate(category, poem, existing_keys):
    """返回错误信息列表，空列表表示通过"""
    errs = []
    for f in REQUIRED_FIELDS:
        if f not in poem:
            errs.append(f"缺少字段 {f}")
    if errs:
        return errs

    lines = poem["lines"]
    if not isinstance(lines, list) or len(lines) != 2:
        errs.append(f"lines 必须恰好 2 行，当前 {len(lines) if isinstance(lines, list) else type(lines).__name__}")
    else:
        for i, ln in enumerate(lines, 1):
            n = len(ln)
            if not (MIN_LINE <= n <= MAX_LINE):
                errs.append(f"第 {i} 行 {n} 字符（需 {MIN_LINE}~{MAX_LINE}）: {ln!r}")

    if poem["season"] not in VALID_SEASONS:
        errs.append(f"season={poem['season']!r} 非法，可选 {sorted(VALID_SEASONS)}")

    k = key_of(poem)
    if k in existing_keys.get(category, set()):
        errs.append(f"类别 {category} 内已存在同名同作者: {k}")
    return errs


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)

    with open(args[0], encoding="utf-8") as f:
        additions = json.load(f)
    with open(POETRY_PATH, encoding="utf-8") as f:
        db = json.load(f)

    existing_keys = {cat: {key_of(p) for p in poems} for cat, poems in db.items()}

    before = {cat: len(v) for cat, v in db.items()}
    all_errs = []
    staged = {}

    for category, poems in additions.items():
        if category not in db:
            all_errs.append(f"[{category}] 未知类别，诗库中没有这个 key")
            continue
        seen = set(existing_keys[category])
        for p in poems:
            errs = validate(category, p, existing_keys)
            k = key_of(p)
            if k in seen:
                errs.append(f"本次新增内重复: {k}")
            if errs:
                all_errs.append(f"[{category}] {p.get('title', '?')}: " + "; ".join(errs))
                continue
            seen.add(k)
            staged.setdefault(category, []).append(p)

    if all_errs:
        print("校验未通过，未写入任何改动：")
        for e in all_errs:
            print("  ✗", e)
        sys.exit(1)

    total_new = sum(len(v) for v in staged.values())
    print(f"校验通过，待新增 {total_new} 首")
    for category, poems in staged.items():
        db[category].extend(poems)
        print(f"  {category:<16} {before[category]:>3} → {len(db[category]):>3}  （+{len(poems)}）")

    total_before = sum(before.values())
    total_after = sum(len(v) for v in db.values())
    print(f"\n全库条目: {total_before} → {total_after}")

    if dry_run:
        print("\n--dry-run：未写入文件")
        return

    with open(POETRY_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n已写入 {POETRY_PATH}")
    print("提醒：请重跑 scripts/subset_font.py 重新生成子集字体，否则新字会缺字。")


if __name__ == "__main__":
    main()
