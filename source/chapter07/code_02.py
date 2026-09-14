class BrowserHeadersMiddleware:
    """把请求头补成浏览器的样子。只补「缺的」，不覆盖调用方显式设过的值。"""

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.headers = crawler.settings.getdict("BROWSER_HEADERS")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        added = 0
        for name, value in self.headers.items():
            # 这里必须判断存在性再赋值。写成 headers.setdefault(name, value) 之后
            # 以为改了值是不对的：更早的中间件（DefaultHeadersMiddleware 在 400 号位）
            # 可能已经填过，setdefault 遇到已有值不会覆盖。
            if name not in request.headers:
                request.headers[name] = value
                added += 1
        if added:
            self.stats.inc_value("headers/filled")
            self.stats.inc_value("headers/filled_total", added)
        return None
