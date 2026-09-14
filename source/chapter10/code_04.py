TABLE = [
    {"channel": "首页", "url": f"{BASE}/books/page/1"},
    {"channel": "第二页", "url": f"{BASE}/books/page/2"},
    {"channel": "第三页", "url": f"{BASE}/books/page/3"},
]

def main():
    settings = get_project_settings()
    settings.set("LOG_LEVEL", "WARNING")
    settings.set("FEEDS", {"out/table.jsonl": {"format": "jsonlines"}})

    process = CrawlerProcess(settings)
    for row in TABLE:
        process.crawl(TableSpider, **row)
    process.start()
