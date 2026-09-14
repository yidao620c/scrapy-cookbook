import json

import scrapy

class QuotesJsDataSpider(scrapy.Spider):
    """路线二：页面里既然有现成数据，就直接把 JSON 抠出来。"""

    name = "quotesjsdata"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/js/"]

    def parse(self, response):
        script = response.xpath('//script[contains(text(), "var data")]/text()').get()
        if not script:
            self.logger.error("路线二 没找到内嵌数据源")
            return
        start = script.find("var data = [") + len("var data = ")
        data, _ = json.JSONDecoder().raw_decode(script[start:])
        self.logger.info("路线二 内嵌数据源，拿到 %d 条", len(data))
        for row in data:
            yield {
                "text": row["text"],
                "author": row["author"]["name"],
                "tags": row["tags"],
            }
