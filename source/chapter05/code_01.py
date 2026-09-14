import scrapy

class QuotesJsStaticSpider(scrapy.Spider):
    """路线一：普通请求。页面里的名言是 JS 拼出来的，静态 HTML 里空空如也。"""

    name = "quotesjsstatic"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/js/"]

    def parse(self, response):
        self.logger.info("路线一 普通请求，div.quote 数量 = %d", len(response.css("div.quote")))
