# 每天15分钟玩转Scrapy10 - 工程化

## 开场

前面几篇的爬虫都是手动跑的。一句 `scrapy crawl`，看着日志滚完，收工。

练手这样挺好，但把它当成一个要交付的东西就不够了。别人得能调你的爬虫，得能一次跑几十个，得能在跑完之后拿到一份可核对的报告。这几种需求，命令行都给不了。

还有一个更现实的问题。一个爬虫上线之后最先失效的往往不是逻辑，是选择器。目标站改一次页面结构，你的 CSS 选择器就开始返回空值，而它不报错，只是数据变少了。等你在两周后发现问题，已经白跑了两周。

这一篇分三块。爬虫怎么从命令行搬进代码、跑一半崩了怎么接上、以及怎么让「页面结构变没变」这件事变成一条能自动跑的断言。

每段输出都是真跑出来的，目录结构、统计数字、契约失败时的输出我都贴出来。

## 从命令行到脚本

`scrapy crawl` 适合手动跑。它每天都能用，但它不适合当一个服务。

生产环境要的东西不太一样。别人得能调你的爬虫，得能一次跑几十个，得能在跑完之后拿到一份结果。这几种需求，命令行都给不了。你想想看，一个要交给同事传参调用的爬虫，总不能靠一句 `scrapy crawl` 加一串参数。

绕开命令行的写法有三种，差别不在写法，在选择依据。

主要看两件事，谁负责启动 reactor，以及一个进程里要不要跑多个蜘蛛。四种启动方式摆在一起，分岔点其实只有这两个。

![四条启动路线的分岔点](https://static.xiongneng.me/scrapy-10-run-paths-20260913062827.png)

### 1. CrawlerProcess 里排队跑多个蜘蛛

最省事的一种。它自己装 reactor、自己起循环，你只管往里塞蜘蛛。

```python
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
```

两个方法的分工要拎清楚。`crawl()` 往队列里放，`start()` 才点火。

我跑了一遍，两个蜘蛛在同一个进程里依次跑完，各自出各自的统计。

| 蜘蛛 | item | 响应 | 说明 |
|------|------|------|------|
| listing | 4 | 1 | 只抓列表页，不跟详情 |
| library | 8 | 10 | 2 个列表页加 8 个详情页 |

`process.start()` 是阻塞的，它会一直卡在那里直到最后一个蜘蛛收工。这一点在写服务的时候要记住，别指望它后面那行代码会立刻执行。

它内部做的事不复杂。先给 `join()` 建一个任务挂到当前循环上，然后调 `reactor.run()` 进主循环，等 join 任务完成再回头停掉 reactor。

⚠️ 也正因为如此，**同一个 `CrawlerProcess` 的 `start()` 只能调一次**。我试着调了第二次，直接抛 `twisted.internet.error.ReactorNotRestartable`。原因是 reactor 一旦停了就没法重启。要跑第二批，就新建一个进程。

### 2. CrawlerRunner 自己管 reactor

第二种写法把 reactor 的生死交回给你。什么时候起、什么时候停，都写在你的代码里。

代价是多一个必须记住的顺序，`install_reactor()` 要排在 import reactor 之前。

```python
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
```

顺序为什么重要，我把写反的结果也测了。

顶层直接 `from twisted.internet import reactor`，拿到的是默认的 `SelectReactor`。而 settings 里 `TWISTED_REACTOR` 写的是 asyncio 版本，两边对不上，装配的时候会抛。

```
RuntimeError: The installed reactor
(twisted.internet.selectreactor.SelectReactor) does not match the requested one
(twisted.internet.asyncioreactor.AsyncioSelectorReactor)
```

单独看这个报错，信息很清楚，照着改就行。麻烦的地方在于它出现的位置。

我当时写的是 `d.addBoth(lambda _: reactor.stop())`，这个回调把异常顺手吞了。于是命令行里一行报错都没有，程序就那么停在那儿，日志停在 `Enabled addons` 那一行不动。我盯着屏幕看了半天才想起来去查 reactor 类型。

所以 `addBoth` 这种写法要留个心眼，它会把异常吃掉。想稳妥一点，用 `addErrback` 单独把失败打出来。

顺序写对之后一切正常。reactor 类型是 `AsyncioSelectorReactor`，两个蜘蛛的数据和上一种写法完全一致。

`CrawlerRunner` 真正的用途不是省事，是嵌进已有的 Twisted 应用。你的程序本来就跑在 Twisted 上，那就别再让 Scrapy 抢着建 reactor。

### 3. 规则表驱动，加一行多一个爬虫

前两种写法解决的是启动方式，这一节解决的是数量。

手上只有三五条规则的时候，一个蜘蛛一个文件挺好。规则变成几十条、还天天变的时候，为每条规则新建一个 spider 文件就不划算了。

做法是把所有会变的东西抽成参数，写一个什么都不写死的蜘蛛。

```python
import scrapy

class TableSpider(scrapy.Spider):
    """只认配置，不写死任何站点细节。"""

    name = "table"
    allowed_domains = ["127.0.0.1"]

    def __init__(self, url=None, channel=None, item_sel=None, title_sel=None,
                 price_sel=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = url
        self.channel = channel or "default"
        self.item_sel = item_sel or "li.book"
        self.title_sel = title_sel or "a::text"
        self.price_sel = price_sel or "span.price::text"

    async def start(self):
        yield scrapy.Request(self.start_url, callback=self.parse)

    def parse(self, response):
        for row in response.css(self.item_sel):
            yield {
                "channel": self.channel,
                "title": row.css(self.title_sel).get(),
                "price": row.css(self.price_sel).get(),
            }
```

配置以表的形式放在外面，`crawl()` 的关键字参数会原样传给蜘蛛的构造函数。

```python
TABLE = [
    {"channel": "首页", "url": f"{BASE}/books/page/1"},
    {"channel": "第二页", "url": f"{BASE}/books/page/2"},
    {"channel": "第三页", "url": f"{BASE}/books/page/3"},
]

def main():
    settings = get_project_settings()
    settings.set("LOG_LEVEL", "WARNING")
    settings.set("FEEDS", {"out/table.jsonl": {"format": "jsonlines"}})

    process = CrawlerProcess(settings)
    for row in TABLE:
        process.crawl(TableSpider, **row)
    process.start()
```

三行配置跑出来 12 条数据，按 channel 分正好各 4 条。

这套写法的好处是代码和规则彻底分开。规则存在数据库里、配置中心里、Excel 里都行，读出来变成一串字典就能跑。加一条渠道只是表里多一行，不用碰代码，也不用重新发版。

有个细节要注意，`channel` 这种来源标记一定要自己带上。同一个输出文件里混着多个蜘蛛的数据，没有来源列，后面根本分不清哪条是哪个渠道抓的。

## 断点续爬与磁盘队列

到这里爬虫都能跑起来了。接下来处理「跑不完」这件事。

几十万条 URL 的爬虫没有一次跑完的运气。中途断电、机器重启、你手滑按了两次 Ctrl-C，都是常态。跑不完之后的正确姿势不是从头再来，是从断的地方接上。

### 1. JOBDIR 三件套

给爬虫一个目录就行。

```bash
scrapy crawl library -s JOBDIR=jobdir/run
```

跑起来之后目录里会多出三样东西。

![JOBDIR 三件套与续爬统计](https://static.xiongneng.me/scrapy-10-jobdir-20260913062827.png)

| 文件 | 作用 |
|------|------|
| `requests.queue/` | 还没抓的请求，按域分目录 |
| `requests.seen` | 已经见过的请求指纹，就是去重表 |
| `spider.state` | `SpiderState` 扩展存的自定义变量 |

我在同一个目录上跑了三次，数据很能说明问题。

| 轮次 | 参数 | item | 响应 | 完成原因 |
|------|------|------|------|----------|
| 冷启动 | 无 | 20 | 25 | finished |
| 第一次 | 加 JOBDIR，页面数限 6 | 14 | 19 | closespider_pagecount |
| 第二次 | 同一个 JOBDIR | 6 | 6 | finished |

第二次只抓了 6 个页面就收工，比冷启动需要的 25 个少了一大截，因为队列里剩下的活儿本来就少了。两轮加起来 14 加 6 正好 20，一条没漏也一条没重。

第二次的统计里还有一行 `dupefilter/filtered` 为 5，那是去重表挡掉的重复请求。这就是 `requests.seen` 在干活。

⚠️ 用 JOBDIR 有一条纪律要守，**改了蜘蛛代码就不要接着旧目录爬**。队列里存的是序列化之后的请求对象，带着当时的 URL、回调名、`meta`。你改掉回调函数名或者 `meta` 的键，那些老请求读回来之后会指向一个不存在的方法。表现出来是蜘蛛启动正常、然后一条数据都不出。

配合它用的还有两个参数。`CLOSESPIDER_PAGECOUNT` 和 `CLOSESPIDER_ITEMCOUNT` 可以让你主动提前收工，我上面就是用前者造出了「跑一半」的场景。这两个参数在调试断点续爬的时候特别好用，不用真的去等着它崩。

### 2. 2.19 新增的 SQLite 队列

默认的磁盘队列有个隐患。写到一半进程被强杀，队列文件可能就损坏了，一整个目录的进度全废。

2.19 新加了四个基于 SQLite 的队列，直接解决这个问题。

```bash
scrapy crawl library -s JOBDIR=jobdir/run \
  -s SCHEDULER_DISK_QUEUE=scrapy.squeues.PickleLifoSQLiteQueue
```

四个新类的名字挺规律，`Pickle` 和 `Marshal` 是序列化方式，`Fifo` 和 `Lifo` 是出队顺序。

换上去之后目录结构一模一样，文件名也一样，但内容是另一回事。我把两个队列的第一个文件头拉出来对比。

| 队列 | 文件头 | 大小 |
|------|--------|------|
| `PickleLifoDiskQueue` | `00 00 00 04 80 04 95 22` | 1224 字节 |
| `PickleLifoSQLiteQueue` | `SQLite format 3.` | 12288 字节 |

右边那个一眼就能认出来是 SQLite。128 条请求下体积差了十倍，这是 SQLite 的页分配开销。

代价是写入变慢。官方说的是「每条请求单独一个事务，换来非正常退出也不会损坏磁盘队列」，速度上要付代价。我拿 300 条请求在两个队列上各压了一遍。

| 队列 | 写入 300 条 | 读出 300 条 | 磁盘占用 |
|------|-------------|-------------|----------|
| `LifoDiskQueue` | 0.1 毫秒 | 11.7 毫秒 | 0 KB |
| `LifoSQLiteQueue` | 386.3 毫秒 | 377.5 毫秒 | 84 KB |

⚠️ 这组数字要读得准确一点。**磁盘队列那个 0.1 毫秒不是因为它快，是因为它在内存里缓冲**，磁盘占用 0 KB 也说明了这一点，真正的落盘发生在页写满或者关闭的时候。SQLite 那个 386 毫秒是每条都提交一次的真实成本。

所以取舍很清楚。抓取量大、机器可能随时被回收的场景，用 SQLite 换可靠性；追求调度吞吐、能接受偶尔重来的场景，用默认队列。

## 契约测试

一个爬虫上线之后最先失效的不是逻辑，是选择器。目标站改一次页面结构，你的 CSS 选择器就开始返回空值。千万别以为这样没事，它不报错，只是数据变少了。

契约测试就是为了让这件事变成一条断言。

### 1. 契约写在 docstring 里

这是最容易看错的一点。契约不是 Python 装饰器，它写在回调的文档字符串里，`@` 开头，一行一条。

```python
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
```

跑起来就一个命令。

```bash
scrapy check
```

我写了三个回调、每条挂两到三个契约，一共 6 条，全通过。

```
......
----------------------------------------------------------------------
Ran 6 contracts in 0.871s

OK
```

三个契约的含义值得逐个说清楚。`@url` 告诉它拿哪个地址做样本请求，这是唯一的必需项。`@returns` 断言输出条数，`item 1` 表示恰好一条 item。`@scrapes` 断言 item 里必须有哪些字段。

⚠️ 这三件事加起来，正好覆盖了选择器失效最常见的表现。**`@scrapes` 是最值钱的那条**，页面结构变了、某个字段取成 `None`，`scrapy check` 会立刻告诉你少字段，而不是等线上数据攒了两周才发现。

### 2. 2.19 新增的请求侧契约

以前契约只能断言响应侧的东西。要测一个 POST 接口就很别扭，没法在契约里声明请求方法。

2.19 补上了这一块，一次加了四个。

| 契约 | 作用 | 写法 |
|------|------|------|
| `@method` | 声明请求方法 | `@method POST` |
| `@body` | 带上请求体 | `@body q=scrapy&page=1` |
| `@header` | 加一个请求头 | `@header Content-Type application/x-www-form-urlencoded` |
| `@cookie` | 加一个 Cookie | `@cookie session demo` |

⚠️ 这四个的语法都是**名字和值用空格分开**，不是冒号。我第一版顺手写成了 `@header Content-Type: application/x-www-form-urlencoded`，结果抛出来一个挺难懂的错。

```
twisted.web.http_headers.InvalidHeaderName: b'Content-Type:'
```

它把 `Content-Type:` 整个当成了请求头的名字。因为 `HeaderContract` 的实现是取第一个参数当名字、剩下的用空格拼起来当值，那个冒号就留在名字里了。

除了这四个，2.19 还有两处契约相关的改进。契约现在支持 `async def` 回调，包括异步生成器，写协程回调的蜘蛛也能用契约了。另外官方把自定义契约的扩展点改了，以前要重写 `add_pre_hook()` 和 `add_post_hook()`，现在改成定义 `pre_process()` 和 `post_process()`，老写法会打弃用警告。

### 3. 让它会失败

通过的输出没什么信息量，失败的样子才值得看。

我故意把 `@scrapes` 里加了一个不存在的字段，输出长这样。

```
FAIL: [broken-contract] parse_detail (@scrapes post-hook)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
scrapy.exceptions.ContractFail: Missing fields: discount

----------------------------------------------------------------------
Ran 2 contracts in 0.712s

FAILED (failures=1)
```

报错里三样东西都有。哪个蜘蛛、哪个回调、哪条契约、以及缺了哪个字段。这个格式直接扔进 CI 就行，退出码非零，流水线会红。

![契约失败时的定位信息](https://static.xiongneng.me/scrapy-10-contract-fail-20260913062827.png)

还有两个参数平时很有用。`scrapy check -l` 只列出有哪些契约不执行，改完一堆 docstring 之后想确认自己没写漏很方便。`scrapy check -a name=value` 可以把蜘蛛参数传进去，跟 `crawl` 的 `-a` 一样，用来测那些依赖参数的蜘蛛。

我的建议是给每个线上的蜘蛛至少配一条契约，就用真实页面地址。它运行成本极低，一个站点一秒钟就跑完了，但能提前告诉你页面改了。

## 容易栽的跟头

**坑 1：管道和中间件方法里留着 `spider` 参数。** 这是 2.19 里刚收紧的。`open_spider(self, spider)`、`process_item(self, item, spider)`、`close_spider(self, spider)` 这三个签名带上 `spider` 就会打弃用警告，原文如下。

```
ScrapyDeprecationWarning: SlowPipeline.open_spider() requires a spider argument,
this is deprecated and the argument will not be passed in future Scrapy versions.
If you need to access the spider instance you can save the crawler instance passed
to from_crawler() and use its spider attribute.
```

官方在警告里直接把替代写法说了，`from_crawler` 里存下 `crawler`，后面用 `self.crawler.spider`。我觉得这个改动值得顺手改掉，理由是它在 2.19 里已经同时覆盖下载器中间件、蜘蛛中间件和管道三处，下一轮就会真的不传参了。

这事儿还有个背景。以前 `spider` 参数是官方推荐的拿蜘蛛实例的方式，老教程全这么写。所以你要是从老项目搬代码过来，这三个签名基本都是带参数的版本，一跑就是一屏警告。

**坑 2：在同一个进程里第二次调 `CrawlerProcess.start()`。** 想「先跑完 A 再跑 B」，直觉写法是两次 start。我实测的结果是这样。

```
[probe] 第一轮 start() 正常返回
[probe] 第二轮抛异常
[probe] twisted.internet.error.ReactorNotRestartable:
```

注意最后那行冒号后面是空的。这个异常的消息体是空字符串，日志里就只有一行光秃秃的类名，很容易被当成别的问题。原因在 Twisted，reactor 是进程级单例，跑过一次就不能再跑。正确写法是把两个 crawler 都 `crawl()` 进同一个 `CrawlerProcess`，只 start 一次，Scrapy 会按顺序排队。

**坑 3：以为 `CrawlerProcess` 上有 `.signals`。** 我当初写多蜘蛛调度脚本的时候第一版就是这么写的，直接抛 `AttributeError: 'CrawlerProcess' object has no attribute 'signals'`。说到底这是个概念没摆正的问题，信号挂在 crawler 上，不在 process 上。要接信号得先拿到 crawler。

```python
process = CrawlerProcess(get_project_settings())
crawler = process.create_crawler("pages")      # 这一步返回 crawler
crawler.signals.connect(on_spider_opened, signal=signals.spider_opened)
process.crawl(crawler, n=50)
process.start()
```

`create_crawler()` 收的是蜘蛛名或者 Spider 类，不收 `模块路径:类名` 那种字符串。传错了报 `KeyError: 'Spider not found: ...'`。

**坑 4：在 `spider_closed` 回调里读 `elapsed_time_seconds`。** 这个统计项是 `CoreStats` 扩展在它的 `spider_closed` 里写进去的，而你的回调跟它谁先执行没有保证。我前几次跑出来一直是 `None`，换成在 `spider_opened` 里用 `time.perf_counter()` 自己掐表就稳了。

顺带一句，同类的还有 `retry/reason_count` 这几个统计。我在反爬那篇里读 429 的重试次数，键名是 `'429 Unknown Status'` 而不是 `429`，因为 Twisted 的状态短语表里没有这个码。想稳妥一点就按前缀遍历，别按精确键名取。

**坑 5：改了蜘蛛代码，接着旧 JOBDIR 爬。** 这条正文提到过，我在这里把它说透，因为它是最贵的一个坑。队列文件里存的是序列化之后的请求对象，带着当时的 URL、回调方法名和 `meta`。你把回调函数改个名字、或者调整了 `meta` 的键，那些老请求读回来之后指向的是一个不存在的方法。

它的表现形式特别难查。蜘蛛启动正常、日志正常、退出原因正常，就是一条数据都不出，连异常都没有。所以要么换一个新目录，要么先清掉 `requests.queue/` 和 `requests.seen` 再重跑。老实说这条纪律写进注释里容易，真到赶进度的时候最容易忘，我的习惯是把目录名带上当天日期，跨天就一定是新目录。

**坑 6：契约写在注释里，不写在 docstring 里。** 契约只从回调函数的文档字符串里读，`@` 开头，一行一条。函数体里的 `#` 注释它一眼都不看。我拿一个把契约写进注释的蜘蛛试了一下，输出是这样。

```
----------------------------------------------------------------------
Ran 0 contracts in 0.002s

OK
```

契约数是零，退出码也是零。这个静默比报错难对付，因为它在 CI 里是绿的，看起来一切正常，实际上你一条断言都没有。所以新写契约之后，我建议先跑一次 `scrapy check -l` 把契约列出来，确认数量对得上再往下走。那三个 `@url`、`@returns`、`@scrapes` 写在 docstring 的哪一行无所谓，写在注释里就等于没写。

## 小结

这一篇三块内容，各管一件事。

从命令行到脚本那块，管的是别人能不能用你的爬虫。`CrawlerProcess` 适合一把跑完的场景，多蜘蛛排队、参数从代码传进去，都在它这儿。要长驻、要反复跑、要在自己的 asyncio 程序里嵌，就换 `CrawlerRunner`，reactor 交给自己管。

断点续爬那块，管的是跑不完的时候怎么办。JOBDIR 三件套给的是最小可用的方案，默认磁盘队列在进程被强杀时确实有损坏风险，SQLite 队列用写入速度换这份可靠性。我实测那组数字挺说明问题，300 条请求的写入从 0.1 毫秒变成 386 毫秒，差了三千多倍，但那个 0.1 毫秒是内存缓冲的假象，别拿它当真性能。

契约测试那块，管的是失效的时候你能不能第一时间知道。三块里我觉得它的性价比最高，一个站点一秒钟跑完，`@scrapes` 少一个字段就红给你看。上线之后真正会坏的东西不是你的逻辑，是别人家的页面结构，而这个东西只能靠定期去戳一下才知道。

要说我在这篇上花时间最多的地方，其实是调度脚本。`CrawlerProcess` 那个 `ReactorNotRestartable` 我试了两次才反应过来是设计如此，`.signals` 挂在哪也是翻了半天。这些都不是难懂的概念，纯粹是没有文档会主动告诉你的东西，所以我在这篇里把它们都写出来了。

这篇里要是有哪里讲得不对，欢迎拍砖。
