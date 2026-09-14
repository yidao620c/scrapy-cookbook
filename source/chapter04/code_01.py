import scrapy
from scrapy import FormRequest

class QuotesJarSpider(scrapy.Spider):
    """两个身份同时在线：桶 A 登录，桶 B 匿名，互不串味儿。"""

    name = "quotesjar"
    allowed_domains = ["quotes.toscrape.com"]

    async def start(self):
        # 桶 A 的一条线：先 GET 登录页，再把令牌提交回去
        yield scrapy.Request(
            "https://quotes.toscrape.com/login",
            meta={"cookiejar": "jar_a"},
            callback=self.submit_login,
        )
        # 桶 B 的一条线：同一个站点，但换一个桶，不带登录态
        yield scrapy.Request(
            "https://quotes.toscrape.com/page/2/",
            meta={"cookiejar": "jar_b"},
            callback=self.check_jar_b,
        )

    def submit_login(self, response):
        token = response.css('input[name="csrf_token"]::attr(value)').get()
        yield FormRequest(
            url="https://quotes.toscrape.com/login",
            formdata={"csrf_token": token, "username": "feiwuxiong", "password": "x"},
            meta={"cookiejar": "jar_a"},
            callback=self.check_jar_a,
        )

    def check_jar_a(self, response):
        self.logger.info("桶 A 登录态 = %s", "Logout" in response.text)

    def check_jar_b(self, response):
        self.logger.info("桶 B 登录态 = %s", "Logout" in response.text)
