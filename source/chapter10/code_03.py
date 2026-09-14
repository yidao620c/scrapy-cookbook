import scrapy

class TableSpider(scrapy.Spider):
    """只认配置，不写死任何站点细节。"""

    name = "table"
    allowed_domains = ["127.0.0.1"]

    def __init__(self, url=None, channel=None, item_sel=None, title_sel=None,
                 price_sel=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = url
        self.channel = channel or "default"
        self.item_sel = item_sel or "li.book"
        self.title_sel = title_sel or "a::text"
        self.price_sel = price_sel or "span.price::text"

    async def start(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    def parse(self, response):
        for row in response.css(self.item_sel):
            yield {
                "channel": self.channel,
                "title": row.css(self.title_sel).get(),
                "price": row.css(self.price_sel).get(),
            }
