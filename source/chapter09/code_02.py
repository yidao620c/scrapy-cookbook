from scrapy.utils.defer import maybe_deferred_to_future

class AsyncDetailSpider(scrapy.Spider):
    name = "async-detail"

    async def start(self):
        yield scrapy.Request(f"{BASE}/books/page/1", callback=self.parse)

    async def parse(self, response):
        hrefs = response.css("li.book a::attr(href)").getall()[:3]
        for href in hrefs:
            # 直接把下载器当异步客户端用
            resp = await maybe_deferred_to_future(
                self.crawler.engine.download(
                    scrapy.Request(response.urljoin(href))
                )
            )
            yield BookItem(
                title=resp.css("h1.title::text").get(),
                sku=resp.css("p.sku::text").get(),
            )
