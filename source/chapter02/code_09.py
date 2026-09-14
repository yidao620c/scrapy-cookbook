from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule


class AuthorCrawlSpider(CrawlSpider):
    """规则化爬取：翻页和作者页都交给 Rule。"""

    name = "author_crawl"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/"]

    rules = (
        # 作者主页：交给 parse_author，不再往下跟
        Rule(LinkExtractor(allow=r"/author/"), callback="parse_author"),
        # 分页：没有 callback，follow 默认为 True，会一直翻到没有下一页
        Rule(LinkExtractor(allow=r"/page/")),
    )

    def parse_author(self, response):
        yield {
            "name": response.css("h3.author-title::text").get(default="").strip(),
            "birthdate": response.css(".author-born-date::text").get(default="").strip(),
        }
