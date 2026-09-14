import hashlib
import json
import sqlite3
from pathlib import Path

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class EnrichPipeline:
    """补算派生字段：正文长度与去重指纹。"""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        text = adapter.get("text") or ""
        author = adapter.get("author") or ""
        adapter["text_len"] = len(text)
        adapter["fingerprint"] = hashlib.sha1(
            f"{text}|{author}".encode("utf-8")
        ).hexdigest()[:16]
        return item


class DedupPipeline:
    """内存去重。重复的直接 DropItem，后面的管道就不会再看到它。"""

    def __init__(self):
        self.seen = set()
        self.dropped = 0

    def process_item(self, item, spider):
        fp = ItemAdapter(item)["fingerprint"]
        if fp in self.seen:
            self.dropped += 1
            raise DropItem(f"重复名言已丢弃: {fp}")
        self.seen.add(fp)
        return item

    def close_spider(self, spider):
        spider.crawler.stats.set_value("dedup/dropped", self.dropped)
        spider.logger.info("去重管道丢掉了 %d 条重复", self.dropped)
