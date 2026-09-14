class RandomUserAgentMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.ua_pool = crawler.settings.getlist("UA_POOL") or UA_POOL
        self.enabled = crawler.settings.getbool("RANDOM_UA_ENABLED", True)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        if not self.enabled:
            return None
        request.headers["User-Agent"] = (
            request.meta.get("ua") or random.choice(self.ua_pool)
        )
        self.stats.inc_value("ua_pool/rotated")
        return None
