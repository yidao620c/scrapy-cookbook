# 每天15分钟玩转Scrapy09 - 异步

## 开场

前面几篇的爬虫，回调都写成同步的样子。`def parse` 里 yield 几个 Request，剩下的交给框架。

其实底下的世界不是同步的。Scrapy 从 2.13 起就换了底盘，2.19 的默认 reactor 已经是 asyncio 版本。你写的每个回调，都在一个 asyncio 事件循环上跑着，只是框架替你把这一层藏起来了。

这一篇讲两件事。回调改成协程之后多了什么能力，以及当你的程序自己就是一个 asyncio 应用的时候，怎么让爬虫在这个循环里一起跑。

第二件事是这一篇的重头。里面有三个硬条件，少一条就静默卡死，一条报错都没有。你想想看，爬虫正常打开、正常关闭、日志干干净净，可就是一个请求都没发出去。说实话，我花了挺久才定位到最里面那一层。

每一段输出都真跑过，目录和统计数字我都贴出来。

## asyncio 与 reactor 的边界

Scrapy 从 2.13 起把 asyncio 当作一等公民，2.19 的默认 reactor 就是 `AsyncioSelectorReactor`。

这句话容易让人误解。你看，它说的是「Scrapy 内部跑在 asyncio 之上」，不是「你随便怎么写都不会撞车」。

真实情况是这样的，下面垫着 Twisted 的 reactor，reactor 下面垫着 asyncio 的事件循环。你直接用 asyncio 的部分很顺，你想自己掌控那个循环的时候就容易踩到边界。这事儿就像两层的插头，中间那层没对准，电就通不过去。

### 1. async def 回调能 await 什么

先说好消息，回调改成协程完全无障碍。

```python
class AsyncLibrarySpider(scrapy.Spider):
    name = "async-library"
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0,
    }

    async def start(self):
        for n in range(1, self.max_pages + 1):
            yield scrapy.Request(f"{BASE}/books/page/{n}", callback=self.parse)

    async def parse(self, response):
        # 这里可以 await 任何异步库，aiohttp、asyncpg、aioredis 都行
        await self._warm_up()
        for li in response.css("li.book"):
            yield BookItem(
                title=li.css("a::text").get(),
                price=li.css("span.price::text").get(),
            )

    async def _warm_up(self):
        await asyncio.sleep(0.01)
        self.crawler.stats.inc_value("async_warmup/calls")
```

改成协程之后，回调里 await 什么都行。这一步的价值比看上去大，很多清洗逻辑本来就是异步的，以前只能想办法包一层，现在直接写。

![协程回调能 await 什么](https://static.xiongneng.me/scrapy-09-async-callback-20260913062827.png)

`start()` 也一样，它必须是异步生成器。3 个列表页跑出来 12 条 item、3 个响应，统计里 `async_warmup/calls` 也是 3，说明每个回调都真的进了协程。

顺手记一句，`yield` 的语义没变。协程回调照样能 `yield` item 和 `yield` 新请求，只是前面多了 `await` 的能力。

### 2. deferred_to_future 把两条轨接起来

好消息说完了，说边界。

有些接口只给你 Twisted 的 `Deferred`，不给你协程。这时候 await 不上去，中间需要一层适配。

```python
from scrapy.utils.defer import maybe_deferred_to_future

class AsyncDetailSpider(scrapy.Spider):
    name = "async-detail"

    async def start(self):
        yield scrapy.Request(f"{BASE}/books/page/1", callback=self.parse)

    async def parse(self, response):
        hrefs = response.css("li.book a::attr(href)").getall()[:3]
        for href in hrefs:
            # 直接把下载器当异步客户端用
            resp = await maybe_deferred_to_future(
                self.crawler.engine.download(
                    scrapy.Request(response.urljoin(href))
                )
            )
            yield BookItem(
                title=resp.css("h1.title::text").get(),
                sku=resp.css("p.sku::text").get(),
            )
```

上面这段把下载器当成了一个普通的异步 HTTP 客户端，在回调里自己控制请求时机。跑出来 3 条 item、4 个响应，从 `engine.download()` 拿回来的响应解析正常。

两个函数的差别在于严格程度。`deferred_to_future()` 只接受 Deferred，传进去的东西不对会直接报错；`maybe_deferred_to_future()` 宽松一些，已经是 Future 就原样返回，不是就转一下。写通用工具函数的时候用后者更省心。

⚠️ 需要注意一点，**在回调里手动调 `engine.download()` 等于绕过了调度器**。请求不进队列，去重不管用，并发额度也不一定按你的预期算。它适合补几个零星请求，不适合当主力抓取方式。主力还是 `yield Request`。

### 3. 在 asyncio 应用里驱动爬虫的三条硬条件

到这里都是顺的。下面这段是这一篇里最硬的一块。

场景是这样的，你的程序本身就是个 asyncio 应用，有自己的协程要跑，同时想让爬虫在这个循环里一起工作。

官方给的入口是 `AsyncCrawlerRunner`，`crawl()` 返回 asyncio 的 Task，可以直接 await。听起来很简单，但真写起来要同时满足三个条件，少一条就静默卡死。

| 条件 | 少了它的症状 |
|------|--------------|
| 事件循环是 `SelectorEventLoop` | 抛 `TypeError`，ProactorEventLoop 不被支持 |
| `install_reactor()` 在循环跑起来之后调 | reactor 绑到另一个循环上，什么都不会发生 |
| 手动调 `reactor.startRunning()` | 连接永远建不起来，没有任何报错 |

一条条来。

![在 asyncio 应用里驱动爬虫的三条硬条件](https://static.xiongneng.me/scrapy-09-three-conditions-20260913062827.png)

第一条来自 Windows。`asyncio.run()` 在 Windows 上默认给你 `ProactorEventLoop`，而 Twisted 明确不收。

```
TypeError: ProactorEventLoop is not supported,
got: <ProactorEventLoop running=True closed=False debug=False>
```

这个报错还算友好，至少它说清楚了。解法是自己指定循环类型。

```python
import asyncio
import sys

def run():
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as r:
            r.run(main())
    else:
        asyncio.run(main())
```

这里有个附带信息值得记一下。老写法是 `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())`，在 Python 3.14 上会连着打两条弃用警告，说这个策略和 `set_event_loop_policy` 都计划在 3.16 移除。换成 `asyncio.Runner(loop_factory=...)` 就干净了，一个警告都没有。

第二条更隐蔽，是调用位置。

`install_reactor()` 内部会去拿当前的事件循环，拿不到就新建一个。在 Python 3.14 上 `get_event_loop()` 拿不到会抛 `RuntimeError`，于是它建了一个新的循环给你，可你的代码在另一个循环上跑。reactor 挂在那个没人运行的循环上，等于挂在空气里。

判断方法很简单，装完以后比一下两个对象是不是同一个。

```python
loop = asyncio.get_running_loop()
install_reactor(REACTOR)
from twisted.internet import reactor
print(reactor._asyncioEventloop is loop)  # 必须是 True
```

我在模块顶层调用 `install_reactor()`，这一行打出来是 `False`。表现是 `reactor.callLater(0.5, ...)` 注册的定时器永远不会触发，整个爬虫一片安静。

第三条是我花时间最多的一条，也是我在别的地方没见过有人写的。

装对了循环、循环也在跑，连接还是建不起来。我一路往下测，最后用最原始的方式验证，直接 `reactor.connectTCP()` 连本机服务，`connectionMade` 根本没触发。

原因在 Twisted 的启动语义上。`reactor.running` 是个标志位，只有 `run()` 或 `startRunning()` 才会把它置为 `True`。而 `callWhenRunning()` 这个接口的判断是，如果 `running` 已经是真就立即执行，否则把回调挂成一个「启动事件」等以后触发。

Twisted 启动线程池用的就是它。

```python
self._threadpoolStartupID = self.callWhenRunning(self.threadpool.start)
```

于是链条串起来了。`running` 是 `False`，线程池的启动回调一直挂着不执行，线程池没起来。而 `connectTCP()` 走的是解析器那一层，解析要线程池，线程池不动，连接就永远连不上。

这个坑的阴险之处在于，**目标地址写的是 IP 字面量也一样**。你可能觉得不用查 DNS 就没这回事，但 `connectTCP` 这条路它绕不开。当初我就是卡在这个直觉上，白白多试了好几轮。

解法就一行。

```python
reactor.startRunning(installSignalHandlers=False)
```

置上之后，同一个裸连接测试立刻通了，`connectionMade` 触发，收到 351 字节。

三条都满足之后，整件事就顺了。完整脚本长这样。

```python
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
```

跑出来的结果值得看一眼。

| 蜘蛛 | item | 响应 | 备注 |
|------|------|------|------|
| async-library | 12 | 3 | `async_warmup/calls` 为 3 |
| async-detail | 3 | 4 | 回调里手动 await 下载 |

爬虫一共花了 0.98 秒，这期间心跳协程跑了 3 次。也就是说爬虫和自己的业务协程真的在同一个循环里并排跑着。

完整的工程化链条其实是一条闭环。写代码、跑契约测试、抓数据、断点续爬、远程观察、最后部署上线，每一环都有对应的机制。

## 没有 reactor 也能跑

前面几节都建立在「Twisted reactor 存在」这个前提上。2.15 起官方给了一个把这个前提拿掉的选择。

`TWISTED_REACTOR_ENABLED` 设成 `False`，整个 Twisted reactor 就不装了，只保留 asyncio 事件循环。下载器换成 aiohttp 实现。

我把运行时真正装载的下载器打出来看过。

![无 reactor 模式下真正装载的下载器](https://static.xiongneng.me/scrapy-09-reactorless-20260913062827.png)

| 协议 | 换成了什么 |
|------|-----------|
| http | `scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler` |
| https | `scrapy.core.downloader.handlers._aiohttp.AiohttpDownloadHandler` |
| ftp | 被摘掉，映射里直接没有它 |
| data | 不变 |
| file | 不变 |
| s3 | 不变 |

⚠️ 这里有个 2.19 的变更要知道，**默认下载器从 `HttpxDownloadHandler` 换成了 `AiohttpDownloadHandler`**。如果你在 2.18 上写过无 reactor 模式并且依赖 httpx 的行为，升到 2.19 会感到差异，想换回来得在 `DOWNLOAD_HANDLERS` 里手动指定。

模式跑起来毫无问题。3 个列表页 12 条 item、15 个响应，和 reactor 模式的结果一致。有意思的是事件循环这次是 `ProactorEventLoop`，也就是前面刚把 Twisted 拒绝掉的那个。没有 Twisted 了，Windows 的限制也就没了。

它唯一的门槛是一个实验性警告，每条 http 和 https 通道各打一次。

```
WARNING: AiohttpDownloadHandler is experimental
and is not recommended for production use.
```

⚠️ 还有一个容易误读的细节，**这组默认值不是在进程设置上改的**。相关逻辑在 `Crawler._apply_settings()` 里，而它要等到 `crawl_async()` 才执行。我在 `create_crawler()` 之后立刻去读 `DOWNLOAD_HANDLERS_BASE`，拿到的还是旧的 `HTTP11DownloadHandler`，要在蜘蛛打开之后从下载器上读才看得到真值。

结论就一句，这个模式值得试，不值得现在上生产。它最大的价值是把 asyncio 生态里那些不兼容 Twisted 的库解放出来，比如 `playwright` 就明确需要 ProactorEventLoop，在 reactor 模式下和 Scrapy 用不到一起。

## 容易栽的跟头

**坑 1：从老教程抄 `def start_requests`。** 2.19 里这个方法已经彻底不生效了，`Spider` 基类上根本没有这个属性。我测过一个只重写 `start_requests()`、不写 `start_urls` 的蜘蛛，跑起来是零请求、零报错、零警告。起始入口只有 `async def start()` 一个，必须写成异步生成器。老代码迁移的时候，这一行是第一个要改的。

**坑 2：顶层 `from twisted.internet import reactor`。** 这样拿到的是默认的 `SelectReactor`，和 `TWISTED_REACTOR` 配的 asyncio 版本不匹配，装配时抛 `RuntimeError`。更麻烦的是如果你习惯写 `d.addBoth(lambda _: reactor.stop())`，这个异常会被那个回调吞掉，命令行里什么都不显示，程序就那么静静地挂着。正确顺序是先用 `install_reactor()` 装好，再 import reactor。

**坑 3：Windows 上直接用 `asyncio.run()`。** 它给的是 `ProactorEventLoop`，Twisted 的 asyncio reactor 明确拒绝，抛 `TypeError: ProactorEventLoop is not supported`。解法是用 `asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)`。顺带说一句，老写法 `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())` 在 Python 3.14 上已经会打弃用警告了。

**坑 4：`install_reactor()` 在事件循环之外调用。** 它内部要拿当前循环，拿不到就新建一个。在 Python 3.14 上 `get_event_loop()` 拿不到会抛异常，于是它真的建了一个新循环，而你的代码在另一个循环上。reactor 挂在那个没人运行的循环上，连 `callLater` 都不触发。判断方法就一行，比较 `reactor._asyncioEventloop is asyncio.get_running_loop()`。

**坑 5：忘了调 `reactor.startRunning()`。** 这是我花时间最多的一条。`reactor.running` 不置成 `True`，`callWhenRunning()` 注册的回调就不会执行，Twisted 的线程池也因此不启动。而 `connectTCP()` 走的是解析器，解析要线程池，于是连接永远建不起来。整个链条上一句报错都没有。**地址写 IP 字面量也一样中招**，别以为不用查 DNS 就没事。

**坑 6：给 `maybe_deferred_to_future()` 的返回值链 `.addCallback()`。** 它返回的是 asyncio 的 Future，不是 Twisted 的 Deferred，上面没有 Twisted 那套链式接口，`AttributeError: '_asyncio.Future' object has no attribute 'addCallback'`。要么拆成两次 `await`，要么用 `deferred_to_future()` 的语义分清楚自己手上是哪种对象。

## 小结

这一篇的两块内容，说到底都在讲边界在哪。

回调那块，好消息居多。改成协程之后 await 什么都行，aiohttp、asyncpg、aioredis 这些库可以直接用，以前得想办法包一层的东西现在能直接写。yield 的语义没变，item 和 Request 照旧。

驱动那块，记住那句判断就行。能 await 的尽量 await，需要自己掌控循环的时候，先确认三件事。循环类型对不对、reactor 装在哪个循环上、running 是不是真。

我自己的感受是，这一篇里最值得记的不是那三个条件本身，是定位方法。这三件事全是零报错，翻日志一点用都没有，只能一个个去比对状态。我当初就卡在最后一条上，来回试了好几轮，最后是去读 Twisted 的启动代码才想明白的。reactor 是不是同一个对象、running 是不是真，这两个问题问下去，每次都能把范围缩到一行代码。

顺手说一句，无 reactor 模式我建议先别上生产。它是实验性的，每条 http 和 https 通道都会打一次警告。但它值得试，因为把 Twisted 那层拿掉之后，asyncio 生态里那些跟 Twisted 不兼容的库就解放出来了，playwright 就是一个。

这篇里要是有哪里讲得不对，欢迎拍砖。
