"""读 authors.json，统计出生年代分布与出生地 Top 榜。"""
import json
from collections import Counter

with open("authors.json", encoding="utf-8") as f:
    data = json.load(f)

years = [int(item["birthdate"][-4:]) for item in data if item["birthdate"]]
decade = Counter(f"{y // 10 * 10}s" for y in years)
places = Counter(item["birthplace"].removeprefix("in ").rsplit(",", 1)[-1].strip()
                 for item in data if item["birthplace"])

print(f"作者档案: {len(data)} 位")
print(f"出生年份跨度: {min(years)} - {max(years)}")
print("\n出生年代分布:")
for d, n in sorted(decade.items()):
    print(f"  {d:<8} {'█' * n} {n}")
print("\n出生地 Top 5:")
for p, n in places.most_common(5):
    print(f"  {p:<16} {n} 位")
