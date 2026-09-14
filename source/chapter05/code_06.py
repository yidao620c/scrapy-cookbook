import scrapy
from scrapy_playwright.page import PageMethod

class CatalogSpider(scrapy.Spider):
    """把几个常用的 PageMethod 摆在一起，看它们各自返回什么。"""

    name = "catalog"
    allowed_domains = ["quotes.toscrape.com"]

    async def start(self):
        # 这几个 PageMethod 对象建出来之后自己留着引用，
        # 跑完请求就能从 .result 上把返回值读回来
        title = PageMethod("title")
        count = PageMethod("evaluate", "document.querySelectorAll('div.quote').length")
        shot = PageMethod("screenshot", path="out/js_page.png", full_page=True)

        yield scrapy.Request(
            "https://quotes.toscrape.com/js/",
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    # 页面加载完成 != 渲染完成，等节点真的出现再往下走
                    PageMethod("wait_for_selector", "div.quote"),
                    PageMethod("wait_for_load_state", "networkidle"),
                    title,
                    count,
                    shot,
                ],
            },
            callback=self.parse,
            cb_kwargs={"pms": {"title": title, "count": count, "shot": shot}},
        )

    def parse(self, response, pms):
        self.logger.info("page.title() 返回 -> %s", pms["title"].result)
        self.logger.info("page.evaluate() 返回 -> %s", pms["count"].result)
        self.logger.info(
            "page.screenshot() 返回 -> %s 类型，长度 %s",
            type(pms["shot"].result).__name__,
            len(pms["shot"].result or b""),
        )
        self.logger.info("同一个响应，选择器数到 %d 条", len(response.css("div.quote")))
