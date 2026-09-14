import scrapy

from quotesitem.items import QuoteItem
from quotesitem.loaders import QuoteLoader


class QuotesItemSpider(scrapy.Spider):
    """抓名言 → ItemLoader 清洗 → 管道去重落库。"""

    name = "quotesitem"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/"]

    def parse(self, response):
        for box in response.css("div.quote"):
            loader = QuoteLoader(item=QuoteItem(), selector=box)
            loader.add_css("text", "span.text::text")
            loader.add_css("author", "small.author::text")
            loader.add_css("author_slug", "span a::attr(href)")
            loader.add_css("tags", "div.tags a.tag::text")
            yield loader.load_item()

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
