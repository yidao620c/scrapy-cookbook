class RotateProxyMiddleware:
    """每个请求从池子里挑一个代理，写进 request.meta["proxy"]。

    真正把代理用起来的是内置的 HttpProxyMiddleware（默认 750 号位），
    它读的正是 request.meta["proxy"]。所以本中间件的号位必须比 750 小。
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.pool = crawler.settings.getlist("PROXY_POOL")
        self.enabled = crawler.settings.getbool("ROTATE_PROXY_ENABLED", False)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        if not self.enabled or not self.pool:
            return None
        # 已经指定过代理的请求不要覆盖（比如某个请求必须走固定出口 IP）
        if request.meta.get("proxy"):
            return None
        request.meta["proxy"] = random.choice(self.pool)
        self.stats.inc_value("proxy/assigned")
        return None

    def process_exception(self, request, exception):
        """代理挂了就把这个请求记一笔，真实项目里应该把它从池子里剔除。"""
        if request.meta.get("proxy"):
            self.stats.inc_value("proxy/failed")
        return None
