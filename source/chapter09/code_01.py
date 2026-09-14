class AsyncLibrarySpider(scrapy.Spider):
    name = "async-library"
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0,
    }

    async def start(self):
        for n in range(1, self.max_pages + 1):
            yield scrapy.Request(f"{BASE}/books/page/{n}", callback=self.parse)

    async def parse(self, response):
        # 这里可以 await 任何异步库，aiohttp、asyncpg、aioredis 都行
        await self._warm_up()
        for li in response.css("li.book"):
            yield BookItem(
                title=li.css("a::text").get(),
                price=li.css("span.price::text").get(),
            )

    async def _warm_up(self):
        await asyncio.sleep(0.01)
        self.crawler.stats.inc_value("async_warmup/calls")
