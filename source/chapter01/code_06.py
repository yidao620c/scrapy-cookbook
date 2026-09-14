# -*- coding: utf-8 -*-
"""读取 scrapy 导出的 quotes.json，统计作者出镜榜与热门标签。"""
import json
from collections import Counter

with open("quotes.json", encoding="utf-8") as f:
    data = json.load(f)

authors = Counter(item["author"] for item in data)
tags = Counter(tag for item in data for tag in item["tags"])

print(f"名言总数: {len(data)}")
print(f"作者人数: {len(authors)}")
print("\n出镜最多的 5 位作者:")
for name, n in authors.most_common(5):
    print(f"  {name:<20} {n} 句")
print("\n最热门的 5 个标签:")
for name, n in tags.most_common(5):
    print(f"  {name:<16} {n} 次")
