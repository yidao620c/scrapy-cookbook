class SlowPipeline:
    def __init__(self, sleep_ms, crawler):
        self.sleep_ms = sleep_ms
        self.crawler = crawler
        self.stats = crawler.stats

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.getint("PIPELINE_SLEEP_MS", 0), crawler)

    def process_item(self, item):
        if self.sleep_ms:
            time.sleep(self.sleep_ms / 1000.0)
            self.stats.inc_value("pipeline/slept")
        return item
