import json

for name in ("out/quotes_pipeline.jsonl", "out/quotes_feed.jsonl"):
    n = sum(1 for line in open(name, encoding="utf-8") if line.strip())
    print(name, "->", n, "条")
