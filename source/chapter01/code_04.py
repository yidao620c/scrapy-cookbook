import scrapy


class QuotesAsyncSpider(scrapy.Spider):
    """等价写法：用 async def start() 手工给出初始请求。"""

    name = "quotes_async"

    async def start(self):
        urls = [
            "https://quotes.toscrape.com/page/1/",
            "https://quotes.toscrape.com/page/2/",
        ]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        page = response.url.split("/")[-2]
        count = len(response.css("div.quote"))
        self.logger.info("第 %s 页解析到 %d 条名言", page, count)
        for quote in response.css("div.quote"):
            yield {
                "page": page,
                "author": quote.css("small.author::text").get(),
            }
