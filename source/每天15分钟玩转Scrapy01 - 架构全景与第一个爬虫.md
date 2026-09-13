# 每天15分钟玩转Scrapy01 - 架构全景与第一个爬虫

## 开场

事情是这样的。

前阵子我把自己九年前写的 Scrapy 教程翻出来重读，那会儿还是 1.0，现在官方已经跑到 2.19 了。本来只想改改 API，改着改着发现，要改的不只是代码，连我讲东西的方式都该换了。

于是索性整套推倒重写。

这是重写后的第 1 篇。整个系列一共 11 篇，从架构全景、Spider 与选择器、数据建模与落库，到登录与 Cookie、动态页面、媒体管道、反爬、性能调优、异步、工程化、部署与运维。今天不急着抠细节，先把地图铺开，顺手跑通你的第一个爬虫。

坦率的讲，我特别理解「用 requests 加 BeautifulSoup 已经够了，何必上框架」这个想法。我自己也是从那儿过来的。

我当年用 requests 抓过一个站，抓完一万条链接，回头去重的时候发现有四千多条是重复的。补上去重，循环写得太猛，对面把我限速了。加上 sleep，跑到第 8000 条程序崩了，重启只能从头再来。最后想把数据顺手存进数据库，发现自己又写了一百多行胶水代码。

这些事单独解决都不难。难的是每写一个新爬虫，就要把它们重写一遍。

Scrapy 干的事就是把这些重复劳动做成标准件。请求怎么排队、怎么去重、怎么限速、怎么重试、怎么并发、数据怎么导出、断了怎么接着爬，全在框架里现成的。你只需要回答两个问题，哪些页面要看，页面上要拿什么。

你可以想想一百年前的汽车工业。零件还是那些零件，可一旦做成标准件，装配就从手工作坊变成了流水线。抓数据这件事走的也是同一条路。

我一直觉得这才是框架该有的姿态。它不替你想清楚抓什么，它只负责把抓的过程管得井井有条。

## Scrapy 是什么

先说结论，Scrapy 是一个用 Python 写的爬取框架，专门干批量抓网页、提结构化数据这件事。

它跑在 Twisted 上面，天生并发、天生异步。一个请求挂了，不会把别的请求一起拖下水。

它内部有几个角色，各管一段。

- ① **引擎 Engine**：总调度，负责控制所有组件之间的数据流，并在特定事件发生时触发信号
- ② **调度器 Scheduler**：接收引擎送来的请求，排队，等引擎下一次来取
- ③ **下载器 Downloader**：真正去发 HTTP 请求、拿回网页
- ④ **蜘蛛 Spiders**：你写的代码，负责解析响应、产出数据和新的请求
- ⑤ **管道 Item Pipeline**：数据被蜘蛛提取之后的加工环节，清洗、校验、去重、落库都在这
- ⑥ **下载器中间件 Downloader Middlewares**：夹在引擎和下载器之间，请求出去和响应回来都要过一遍，改请求头、加代理都在这
- ⑦ **蜘蛛中间件 Spider Middlewares**：夹在引擎和蜘蛛之间，处理蜘蛛的输入（响应）和输出（数据与新请求）

再加一个不参与数据流的角色，**扩展 Extensions**，用来挂载全局功能，比如 Telnet 控制台、内存监控。

那么，这几个角色是怎么串起来的？官方给的顺序是这样的。

1. 引擎从蜘蛛那里拿到初始请求
2. 引擎把请求交给调度器排队，并索要下一个待抓取的请求
3. 调度器把下一个请求还给引擎
4. 引擎把请求发给下载器，途中经过下载器中间件
5. 页面下载完，下载器生成响应送回引擎，途中再经过下载器中间件
6. 引擎把响应交给蜘蛛处理，途中经过蜘蛛中间件
7. 蜘蛛处理完响应，把提取到的数据和新的请求交回引擎，途中还是经过蜘蛛中间件
8. 引擎把数据送进管道，把新请求送回调度器，并继续索要下一个请求
9. 从第 3 步开始循环，直到调度器里再没有请求

你把这圈读两遍就会发现，Scrapy 的爬虫说到底就是一个循环。蜘蛛产出请求，请求变成响应，响应又产出请求和数据，直到请求耗尽。你写的那个 `parse` 方法，就卡在这个循环的中间。

下面这张是官方文档给出的架构图，图上红圈里的数字跟前面那几步一一对应，对照着看一眼就通了。

![Scrapy 官方架构图](https://static.xiongneng.me/scrapy-01-architecture.png)

## 跑通第一个爬虫

### 1. 先把 Scrapy 装上

```bash
uv add "scrapy[images]"
```

从 2.18 起，Scrapy 开始提供可选依赖的 `extras` 写法，用到什么装什么。`scrapy[images]` 带图片处理（Pillow），`scrapy[s3]` 带 S3 导出，`scrapy[http2]` 带 HTTP/2，`scrapy[uvloop]` 换用更快的 asyncio 事件循环。全部装齐就是 `scrapy[all]`。

装完先自检一下，把关键依赖的版本打出来。

```bash
scrapy version -v
```

跑出来是这样，注意 Twisted 和 Python 的版本，它们直接决定你后面能不能用 asyncio。

```
Scrapy       : 2.19.0
lxml         : 6.1.3
cssselect    : 1.5.0
parsel       : 1.11.0
w3lib        : 2.4.1
Twisted      : 26.4.0
Python       : 3.14.3 (tags/v3.14.3:323c59a, Feb  3 2026, 16:04:56) [MSC v.1944 64 bit (AMD64)]
pyOpenSSL    : 26.4.0 (OpenSSL 4.0.2 25 Aug 2026)
Platform     : Windows-11-10.0.26200-SP0
```

### 2. 建个项目

```bash
scrapy startproject quotesdemo
```

框架会把骨架搭好，还会提示你下一步可以生成蜘蛛。

```
New Scrapy project 'quotesdemo', using template directory '...\scrapy\templates\project', created in:
     D:\...\quotesdemo

 You can start your first spider with:
     cd quotesdemo
     scrapy genspider example example.com
```

懒得手写样板的话，也能用 `scrapy genspider` 直接生成蜘蛛文件。

```bash
cd quotesdemo && scrapy genspider quotes quotes.toscrape.com
```

### 3. 项目里都有啥

生成出来的目录长这样，八个文件各司其职。

```
quotesdemo/
    scrapy.cfg            # 部署与项目配置的入口
    quotesdemo/           # Python 包，你的代码都在这
        __init__.py
        items.py          # 数据结构定义
        middlewares.py    # 中间件（下载器 / 蜘蛛）
        pipelines.py      # 数据管道
        settings.py       # 全局配置
        spiders/          # 所有蜘蛛放这里
            __init__.py
```

`settings.py` 里有几个默认值值得先看一眼，它们决定了你第一次运行的行为。

```python
BOT_NAME = "quotesdemo"
ADDONS = {}                      # 2.17 起的插件机制，第三方扩展挂这里

ROBOTSTXT_OBEY = True            # 默认遵守 robots.txt
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1               # 每个请求间隔 1 秒
FEED_EXPORT_ENCODING = "utf-8"   # 导出默认 UTF-8
```

有个细节我得提醒一句。模板里 `USER_AGENT` 那行是注释掉的，也就是说你的默认身份是 `Scrapy/2.19`。抓之前建议把这行打开，换成项目名加你的站点或邮箱，方便站长联系你调整，而不是直接把你封了。

![项目结构与命令行工具](https://static.xiongneng.me/scrapy-01-project-layout.png)

另外注意模板生成的 `items.py`。从 2.17 起，默认写法已经从 `scrapy.Item` 换成了 dataclass，这个小变化后面讲数据建模那篇还会细说。

```python
from dataclasses import dataclass


@dataclass
class QuotesdemoItem:
    # define the fields for your item here like:
    # name: str | None = None
    pass
```

### 4. 第一个蜘蛛

在 `quotesdemo/spiders/` 下面新建 `quotes_spider.py`。

示例站我用官方教程指定的 `quotes.toscrape.com`，它专门为练习准备，结构稳定，不会哪天突然变质。

```python
import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"                                        # 蜘蛛名，项目内必须唯一
    allowed_domains = ["quotes.toscrape.com"]              # 只允许在这个域内跟进链接
    start_urls = ["https://quotes.toscrape.com/page/1/"]   # 初始请求地址

    def parse(self, response):
        # 一页上有 10 条名言，逐条提取
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
                "tags": quote.css("div.tags a.tag::text").getall(),
            }

        # 找到"下一页"链接就继续跟进，找不到循环自然结束
        next_page = response.css("li.next a::attr(href)").get()
        if next_page is not None:
            yield response.follow(next_page, callback=self.parse)
```

这里有三处关键点。`name` 是这只蜘蛛的唯一标识，`start_urls` 给出起点，`parse` 是默认回调。`response.follow()` 会返回一个 `Request` 对象，它必须被 `yield` 出去才会生效。这个方法还有个好处，它能直接吃相对路径，上面拿到的 `/page/2/` 就是相对路径，不用你自己拼 `urljoin`。

### 5. 换成异步写法

`start_urls` 是快捷写法。官方教程现在主推的是 `async def start()`，需要手工构造初始请求的时候用它。

```python
import scrapy


class QuotesAsyncSpider(scrapy.Spider):
    """等价写法：用 async def start() 手工给出初始请求。"""

    name = "quotes_async"

    async def start(self):
        urls = [
            "https://quotes.toscrape.com/page/1/",
            "https://quotes.toscrape.com/page/2/",
        ]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        page = response.url.split("/")[-2]
        count = len(response.css("div.quote"))
        self.logger.info("第 %s 页解析到 %d 条名言", page, count)
        for quote in response.css("div.quote"):
            yield {
                "page": page,
                "author": quote.css("small.author::text").get(),
            }
```

`start()` 必须写成异步生成器，用 `yield` 吐初始请求。两种写法完全等价，日常用 `start_urls` 更省事，需要在启动时读配置、拼参数、发登录请求，那就用 `async def start()`。

### 6. 跑起来，顺便导出

```bash
scrapy crawl quotes -O quotes.json
```

跑到最后，框架会打印一份完整的运行统计，这份日志是排查问题的第一手材料。

```
2026-09-12 18:02:54 [scrapy.extensions.feedexport] INFO: Stored json feed (100 items) in: quotes.json
2026-09-12 18:02:54 [scrapy.statscollectors] INFO: Dumping Scrapy stats:
{'downloader/request_count': 11,
 'downloader/response_status_count/200': 10,
 'downloader/response_status_count/404': 1,
 'elapsed_time_seconds': 11.304500199999893,
 'finish_reason': 'finished',
 'item_scraped_count': 100,
 'items_per_minute': 545.4545454545455,
 'request_depth_max': 9,
 'robotstxt/request_count': 1,
 'robotstxt/response_status_count/404': 1,
 'scheduler/enqueued/memory': 10,
 'start_time': datetime.datetime(2026, 9, 12, 10, 2, 42, 798685, tzinfo=datetime.timezone.utc)}
```

一眼能读出不少东西。共发出 11 个请求（第 1 页加 9 次翻页，再加 1 次 robots.txt），拿到 100 条数据，用了 11.3 秒，最大跟进深度 9 层。

那个 404 是 robots.txt 本身不存在，Scrapy 把它当成没有限制直接放行。这件事后面避坑那节会细说。

导出的 `quotes.json` 是标准 JSON 数组，长这样。

```json
[
  {
    "text": "“The world as we have created it is a process of our thinking. It cannot be changed without changing our thinking.”",
    "author": "Albert Einstein",
    "tags": ["change", "deep-thoughts", "thinking", "world"]
  },
  {
    "text": "“It is our choices, Harry, that show what we truly are, far more than our abilities.”",
    "author": "J.K. Rowling",
    "tags": ["abilities", "choices"]
  }
]
```

### 7. 用 Shell 现场试选择器

写选择器千万别靠猜。

`scrapy shell` 会把页面下载好，把 `response` 对象直接递到你手上。

```bash
scrapy shell "https://quotes.toscrape.com/page/1/"
```

进去之后逐条试，下面每一条的输出都是我在沙箱里实测的。

```python
>>> response.css("title::text").get()
'Quotes to Scrape'

>>> response.css("div.quote span.text::text").get()[:50]
'“The world as we have created it is a process of o'

>>> response.css("div.tags a.tag::text").getall()[:4]
['change', 'deep-thoughts', 'thinking', 'world']

>>> response.css("li.next a").attrib["href"]
'/page/2/'

>>> response.css("noelement").get()     # 取不到不会报错，返回 None
None
```

这里有三条经验。`::text` 只取标签里的文字，不加它会把整个标签一起带出来。`.get()` 只拿第一个结果，取不到返回 `None`，`.getall()` 返回完整列表。`.attrib` 是拿属性的便捷写法，等价于 `::attr()`。

想直接看渲染效果，在 shell 里敲 `view(response)`，它会在浏览器里打开这个响应。

![view(response) 在浏览器里打开的页面](https://static.xiongneng.me/scrapy-01-view-response-20260912211714.png)

浏览器里呈现的就是这个样子，左上角标题，左侧一条条名言，右边一坨标签云。

写选择器之前先拿眼睛把页面结构过一遍，比对着空白文件瞎猜强得多。

## 名言榜与作者统计

抓完只是半成品，能拿来用才算数。

场景是这样，把演示站的名言全抓下来，顺手做一份谁的话最多、最热门标签是哪些的榜单。前半段交给 Scrapy，后半段用几行标准库代码就够了。

蜘蛛就是上面那个 `quotes`，`scrapy crawl quotes -O quotes.json` 跑完拿到 100 条数据。接下来写 `stats.py` 做统计。

```python
# -*- coding: utf-8 -*-
"""读取 scrapy 导出的 quotes.json，统计作者出镜榜与热门标签。"""
import json
from collections import Counter

with open("quotes.json", encoding="utf-8") as f:
    data = json.load(f)

authors = Counter(item["author"] for item in data)
tags = Counter(tag for item in data for tag in item["tags"])

print(f"名言总数: {len(data)}")
print(f"作者人数: {len(authors)}")
print("\n出镜最多的 5 位作者:")
for name, n in authors.most_common(5):
    print(f"  {name:<20} {n} 句")
print("\n最热门的 5 个标签:")
for name, n in tags.most_common(5):
    print(f"  {name:<16} {n} 次")
```

跑一下。

```bash
python stats.py
```

榜单出来了，数据是真实的。

```
名言总数: 100
作者人数: 50

出镜最多的 5 位作者:
  Albert Einstein      10 句
  J.K. Rowling         9 句
  Marilyn Monroe       7 句
  Dr. Seuss            6 句
  Mark Twain           6 句

最热门的 5 个标签:
  love             14 次
  inspirational    13 次
  life             13 次
  humor            12 次
  books            11 次
```

你看，这个过程正好走了一遍前面那张架构图上的路径。蜘蛛产出初始请求，调度器排队，下载器取回页面，蜘蛛解析出数据和下一页请求，数据经管道写进 feed 文件。

你只写了 `parse` 一个方法，中间那些环节全是框架替你跑完的。这就是用框架的收益所在，你花在抓什么上的精力，不会被怎么调度的琐事稀释掉。

![完整案例的抓取链路](https://static.xiongneng.me/scrapy-01-quotes-flow.png)

## 容易栽的跟头

**坑 1：请求发了，数据没出来。** 忘了写 `parse`，或者把回调名拼错，日志里就会显示下载成功、偏偏没有数据。我第一次遇到还以为是页面结构改了，查了半天才发现是名字的问题。没指定 `callback` 的请求默认调用 `parse`，名字必须就叫 `parse`，写成 `parsel`、`parse_page` 都不行。改了名字，就得在 `scrapy.Request(url, callback=self.新名字)` 里显式指定。

**坑 2：`-o` 和 `-O` 用混，JSON 文件被写坏。** `-O` 是覆盖写，跑第二次干净重来。`-o` 是追加写，往 JSON 数组后面再塞一个数组，文件当场就不再是合法 JSON，下次 `json.load` 直接报错。要反复跑就用 `-O`，要累积记录就换成 `-o quotes.jsonl`，一行一条，追加多少次都合法。

**坑 3：默认身份是 `Scrapy/2.19`。** 模板里 `USER_AGENT` 那行是注释状态，不改就是框架默认值，很容易被识别、被限速。打开它，写成项目名加你的域名或邮箱，这是对站点的基本礼貌，也是给自己省麻烦。

**坑 4：robots.txt 的三种结果，处理方式完全不同。** 返回 200 就按规则办。返回 404 会被当成没有限制直接放行，本次实测日志里的 `robotstxt/response_status_count/404` 就是这种情况。返回 5xx 服务器错误时，礼貌起见框架默认会拒绝抓取。所以看到爬虫一条数据都拿不到，先去日志里搜 `robotstxt`，比盲猜快得多。

**坑 5：`scrapy shell` 的 URL 不加引号。** 带查询参数的地址里有 `&`，不加引号会被命令行当成命令分隔符截断，shell 拿着半个 URL 去请求，自然 404。macOS 和 Linux 用单引号，Windows 那句示例要用双引号，写成 `scrapy shell "https://example.com/list?page=1&sort=new"` 这样。

**坑 6：`allowed_domains` 写错不报错，请求被静默丢掉。** 这个词只写主域（`example.com`）能覆盖子域，写成 `example.com:8080` 这种带端口的形态，框架不会报错，只是把请求悄悄过滤掉。我当初就是这么写的，日志里请求数少得可怜，找了半天没找着原因。。。更隐蔽的是，从 2.17 起这类书写问题连运行时警告都取消了，官方建议改用 `scrapy-lint` 做静态检查。写完花两分钟对一遍域名，能省一小时排查。

## 小结

回到开头那个词，标准件。

这一篇只做了两件事，把 Scrapy 的内部结构铺开，再跑通一个能拿到数据的爬虫。

结构那半边，值得记住的是那条循环。蜘蛛产出请求，请求变成响应，响应又产出数据和新的请求，直到调度器空掉。七个角色各管一段，而你写的代码只占蜘蛛那一个格子。

实操那半边，一个爬虫的最小闭环也就是四步。建项目、写 Spider、`scrapy crawl` 跑起来、导出文件。中途选择器拿不准，`scrapy shell` 随开随试，不用反复重启爬虫。

说真的，这两件事都不用背。你只要记得那个循环长什么样，剩下的细节用着用着就熟了。

我自己也还在用这套东西，也还在踩新的坑。这篇里要是有哪里讲得不对，欢迎拍砖。
