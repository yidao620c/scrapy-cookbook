class JsonlPipeline:
    """写 JSONL。文件在 open_spider 打开、close_spider 关闭。"""

    def open_spider(self, spider):
        path = Path(spider.settings.get("JSONL_PATH", "quotes_pipeline.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("w", encoding="utf-8")
        self.count = 0

    def process_item(self, item, spider):
        self.fh.write(json.dumps(ItemAdapter(item).asdict(), ensure_ascii=False) + "\n")
        self.count += 1
        return item

    def close_spider(self, spider):
        self.fh.close()
        spider.logger.info("JSONL 写出 %d 条", self.count)


class SQLitePipeline:
    """写 SQLite。fingerprint 做主键，天然防重复入库。"""

    def __init__(self):
        self.conn = None
        self.rows = 0

    @classmethod
    def from_crawler(cls, crawler):
        """要用到 settings 的管道就实现这个类方法。"""
        pipeline = cls()
        pipeline.db_path = crawler.settings.get("SQLITE_PATH", "quotes.db")
        return pipeline

    def open_spider(self, spider):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                fingerprint TEXT PRIMARY KEY,
                text        TEXT NOT NULL,
                author      TEXT,
                author_slug TEXT,
                tags        TEXT,
                text_len    INTEGER
            )
            """
        )

    def process_item(self, item, spider):
        a = ItemAdapter(item)
        self.conn.execute(
            "INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?,?)",
            (a["fingerprint"], a["text"], a["author"], a["author_slug"],
             ",".join(a.get("tags") or []), a["text_len"]),
        )
        self.rows += 1
        return item

    def close_spider(self, spider):
        self.conn.commit()
        self.conn.close()
        spider.logger.info("SQLite 写入 %d 条 → %s", self.rows, self.db_path)
