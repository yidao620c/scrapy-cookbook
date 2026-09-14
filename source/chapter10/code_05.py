class CatalogContractSpider(scrapy.Spider):
    name = "catalog-contract"

    def parse_detail(self, response):
        """详情页要产出 BookItem，三个字段不缺。

        @url http://127.0.0.1:8413/books/book-00
        @returns item 1
        @scrapes title sku price
        """
        yield BookItem(
            title=response.css("h1.title::text").get(),
            sku=response.css("p.sku::text").get(),
            price=response.css("p.price::text").get(),
        )
