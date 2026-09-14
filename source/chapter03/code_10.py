from quotesitem.spiders.quotes_item import QuotesItemSpider


class QuotesAliasSpider(QuotesItemSpider):
    """同一份内容挂在两个 URL 上（常见的别名情况），用来验证去重管道。"""

    name = "quotesalias"
    start_urls = [
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/page/1/",
    ]
