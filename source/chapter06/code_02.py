import scrapy

from bookmedia.items import BookItem

class BookCoverSpider(scrapy.Spider):
    name = "bookcovers"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    max_pages = 3

    def parse(self, response):
        page_no = int(response.meta.get("page_no", 1))
        for card in response.css("article.product_pod"):
            link = card.css("h3 a")
            yield BookItem(
                title=(link.attrib.get("title") or "").strip(),
                price=card.css("p.price_color::text").get(default="").strip(),
                detail_url=response.urljoin(link.attrib.get("href") or ""),
                # 字段名必须是 image_urls，而且是绝对地址
                image_urls=[response.urljoin(card.css("img::attr(src)").get())],
            )

        nxt = response.css("li.next a::attr(href)").get()
        if nxt and page_no < self.max_pages:
            yield response.follow(
                nxt, callback=self.parse, meta={"page_no": page_no + 1}
            )
