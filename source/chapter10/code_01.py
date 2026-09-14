import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

def main():
    settings = get_project_settings()
    settings.set("LOG_LEVEL", "INFO")
    process = CrawlerProcess(settings)

    # 这两行只是排队，还没开始跑
    process.crawl("library", max_pages=2)
    process.crawl("listing")

    # 这一行才真正开跑，而且它阻塞到全部结束
    process.start()

if __name__ == "__main__":
    main()
