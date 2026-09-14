import asyncio
import sys
import time

from scrapy.crawler import AsyncCrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
from scrapy.utils.reactor import install_reactor

REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

async def heartbeat(stop: asyncio.Event, stats: dict):
    """爬虫在跑的时候，我自己的异步任务也在跑。"""
    while not stop.is_set():
        stats["beats"] += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.2)
        except TimeoutError:
            pass

async def main():
    loop = asyncio.get_running_loop()
    install_reactor(REACTOR)
    configure_logging({"LOG_LEVEL": "INFO"})

    from twisted.internet import reactor

    print("reactor 绑在同一个循环上：", reactor._asyncioEventloop is loop)
    reactor.startRunning(installSignalHandlers=False)

    runner = AsyncCrawlerRunner(get_project_settings())
    stats = {"beats": 0}
    stop = asyncio.Event()
    beat_task = asyncio.create_task(heartbeat(stop, stats))

    t0 = time.monotonic()
    await runner.crawl("async-library", max_pages=3)
    await runner.crawl("async-detail")
    elapsed = time.monotonic() - t0

    stop.set()
    await beat_task
    print(f"爬虫耗时 {elapsed:.2f} 秒，期间心跳跑了 {stats['beats']} 次")

def run():
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as r:
            r.run(main())
    else:
        asyncio.run(main())

if __name__ == "__main__":
    run()
