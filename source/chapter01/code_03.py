import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"                                        # 蜘蛛名，项目内必须唯一
    allowed_domains = ["quotes.toscrape.com"]              # 只允许在这个域内跟进链接
    start_urls = ["https://quotes.toscrape.com/page/1/"]   # 初始请求地址

    def parse(self, response):
        # 一页上有 10 条名言，逐条提取
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
                "tags": quote.css("div.tags a.tag::text").getall(),
            }

        # 找到"下一页"链接就继续跟进，找不到循环自然结束
        next_page = response.css("li.next a::attr(href)").get()
        if next_page is not None:
            yield response.follow(next_page, callback=self.parse)
