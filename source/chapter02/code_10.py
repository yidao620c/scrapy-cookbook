import scrapy


class AuthorsSpider(scrapy.Spider):
    """两段式抓取：列表页取作者链接，作者页补生平档案。"""

    name = "authors"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/"]

    def parse(self, response):
        # 第一段：名言条目里的作者主页链接。
        # dict.fromkeys 保序去重，同一页重复出现的作者只发一次请求
        links = response.css("div.quote span a::attr(href)").getall()
        for link in dict.fromkeys(links):
            yield response.follow(link, callback=self.parse_author)

        # 第二段：翻页，把 10 页都走一遍
        yield from response.follow_all(css="li.next a", callback=self.parse)

    def parse_author(self, response):
        """作者详情页：字段与页面结构一一对应，缺字段用 default 兜底。"""
        yield {
            "name": response.css("h3.author-title::text").get(default="").strip(),
            "birthdate": response.css(".author-born-date::text").get(default="").strip(),
            "birthplace": response.css(".author-born-location::text").get(default="").strip(),
            "bio": response.css(".author-description::text").get(default="").strip(),
        }
