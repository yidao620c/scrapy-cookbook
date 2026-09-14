import scrapy
from scrapy import FormRequest

class QuotesLoginSpider(scrapy.Spider):
    """登录后带会话翻页，每页都确认登录态还在。"""

    name = "quoteslogin"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/login"]

    def parse(self, response):
        # 第一步：从登录页里把隐藏令牌抠出来
        token = response.css('input[name="csrf_token"]::attr(value)').get()
        self.logger.info("第一步 拿到 csrf_token=%s", token)

        # 第二步：连着令牌一起提交，回调就是登录后的落点
        yield FormRequest(
            url="https://quotes.toscrape.com/login",
            formdata={
                "csrf_token": token,
                "username": "feiwuxiong",
                "password": "whatever",
            },
            callback=self.after_login,
        )

    def after_login(self, response):
        # 第三步：用文本特征判断，不要看状态码
        if "Logout" not in response.text:
            self.logger.error("登录失败，还停在登录页：%s", response.url)
            return
        self.logger.info("第三步 登录成功，落点 %s", response.url)
        yield from response.follow_all(css="li.next a", callback=self.parse_page)

    def parse_page(self, response):
        """翻页页面上再确认一次登录态，证明 Cookie 一直跟着。"""
        self.logger.info("翻到 %s，仍然登录中=%s", response.url, "Logout" in response.text)
        for q in response.css("div.quote"):
            yield {
                "text": q.css("span.text::text").get(),
                "author": q.css("small.author::text").get(),
            }
