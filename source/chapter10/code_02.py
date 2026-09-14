from scrapy.utils.reactor import install_reactor

REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
install_reactor(REACTOR)  # 这一行必须在下面那行之前

from twisted.internet import reactor  # noqa: E402

from scrapy.crawler import CrawlerRunner  # noqa: E402
from scrapy.utils.log import configure_logging  # noqa: E402
from scrapy.utils.project import get_project_settings  # noqa: E402

def main():
    configure_logging({"LOG_LEVEL": "INFO"})
    print("reactor 类型：", type(reactor).__module__ + "." + type(reactor).__name__)

    runner = CrawlerRunner(get_project_settings())
    runner.crawl("library", max_pages=2)
    runner.crawl("listing")

    d = runner.join()
    d.addBoth(lambda _result: reactor.stop())
    reactor.run()

if __name__ == "__main__":
    main()
