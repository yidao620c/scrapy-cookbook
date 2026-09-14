import scrapy


class QuotesSpider(scrapy.Spider):
    """Spider 的四要素与回调链。"""

    name = "quotes"                              # 要素一：唯一的名字
    allowed_domains = ["quotes.toscrape.com"]    # 要素二：域白名单
    start_urls = ["https://quotes.toscrape.com/"]  # 要素三：起始请求

    def parse(self, response):                   # 要素四：默认回调
        self.logger.info("正在处理 %s", response.url)

        # 产出数据
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
            }

        # 产出新任务：作者主页另找函数处理，别挤在 parse 里
        for link in response.css("div.quote span a::attr(href)").getall():
            yield response.follow(link, callback=self.parse_author)

    def parse_author(self, response):
        yield {
            "name": response.css("h3.author-title::text").get(default="").strip(),
            "birthdate": response.css(".author-born-date::text").get(default="").strip(),
        }
