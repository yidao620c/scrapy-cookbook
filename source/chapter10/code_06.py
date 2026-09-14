process = CrawlerProcess(get_project_settings())
crawler = process.create_crawler("pages")      # 这一步返回 crawler
crawler.signals.connect(on_spider_opened, signal=signals.spider_opened)
process.crawl(crawler, n=50)
process.start()
