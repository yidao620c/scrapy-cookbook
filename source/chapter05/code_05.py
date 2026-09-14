import scrapy
from scrapy_playwright.page import PageMethod

class QuotesJsRenderSpider(scrapy.Spider):
    """路线三：交给浏览器把页面渲染好，再按普通选择器抓。"""

    name = "quotesjsrender"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/js/"]

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        # 等名言节点真的出现，别让框架拿到半成品页面
                        PageMethod("wait_for_selector", "div.quote"),
                    ],
                },
            )

    def parse(self, response):
        quotes = response.css("div.quote")
        self.logger.info("路线三 浏览器渲染后，div.quote 数量 = %d", len(quotes))
        for q in quotes:
            yield {
                "text": q.css("span.text::text").get(),
                "author": q.css("small.author::text").get(),
                "tags": q.css("div.tags a.tag::text").getall(),
            }
