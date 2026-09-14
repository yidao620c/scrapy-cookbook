class RenderLeanSpider(scrapy.Spider):
    name = "renderlean"
    custom_settings = {
        "PLAYWRIGHT_ABORT_REQUEST": "jsrender.abort.should_abort",
    }
