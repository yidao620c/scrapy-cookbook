# 每天15分钟玩转Scrapy06 - 媒体管道

## 开场

前面几篇取的都是文字。这一篇换个东西取，文件。

图片和文件跟文字不一样。文字抓下来就是一段字符串，落地的事你自己安排。图片要发网络请求、要写磁盘、可能要顺带跑一遍缩略图，每一步都会慢，每一步都可能失败。

我拿官方那个卖书的演示站从头试了一遍。`books.toscrape.com` 每本书都有封面，60 本书、60 张图，正好够练。

跑通不难，坑全在细节上。比如有张图挂了，却没有一个人告诉你。再比如管道序号写错一格，图片路径永远进不了数据库，而数据看上去完全正常。

说实话，这块的坑比前面几篇都隐蔽。你想想看，爬虫跑完了、item 也导出了、日志里一行红字都没有，可磁盘上就是少了几个文件。

这一篇分两块。媒体管道的两个设计约定，以及三个够用的扩展点。

每段输出还是真跑出来的，目录结构和统计数字我都贴出来。

## 媒体管道的两个约定

普通 item 走到管道里，就是一段内存里的数据，快得没有存在感。

图片和文件不一样。它们要发网络请求、要落磁盘、可能要跑一遍缩略图，每一步都可能慢、都可能失败。把这种活塞进普通的 `process_item` 里，一个 item 卡在一张大图上，后面的 item 全排着。

所以 Scrapy 把它们单独拎出来做成 `MediaPipeline`，两个关键设计。

![媒体管道的落盘链路](https://static.xiongneng.me/scrapy-06-media-flow-20260913062827.png)

一个设计是**绕开调度器**。媒体文件的请求不进请求队列，而是直接交给下载器中间件链，由 `engine.download_async()` 发出去。好处是它不占调度器的位置，也不经过 spider 中间件。

⚠️ 但有个前提要钉死，**它绕开的只是调度器，没绕开域的并发额度**。图片下载和页面抓取抢的是同一批下行槽，`CONCURRENT_REQUESTS_PER_DOMAIN` 和 `DOWNLOAD_DELAY` 一样管着它。这一点很容易想反，以为媒体走的是另一条快车道。

我拿同一批 60 张图做过对照。并发压到 1、延迟设成 0.5 秒，63 个请求跑了 57.39 秒。并发放到 6、延迟清零，4.90 秒跑完。差了 11 倍多，慢的那次就是被延迟卡住的，一张图也没少。

另一个设计是**按 URL 去重，再加按 item 加锁**。同一个图片地址在多个 item 里出现只下载一次，结果共享给所有等它的 item；一个 item 的媒体文件全部结束，这个 item 才继续往下走。后一条保证了你在 `item_completed` 里读到的结果一定是完整的，不会出现「一半图还在路上」这种中间状态。

顺带说一句，这个去重是管道自己按请求指纹做的，跟调度器那个去重队列没有关系。所以在 `get_media_requests()` 里加不加 `dont_filter` 都一样。

用法上只有一个硬约定，字段名必须叫这两个。

| 用途 | 输入字段 | 输出字段 |
|------|----------|----------|
| 图片管道 | `image_urls` | `images` |
| 文件管道 | `file_urls` | `files` |

名字改了管道就找不到活干，而且它不报错，只是安静地什么都不做。你看，这是本篇第一个「静默失效」型的坑。

字段之外还有一件事得说清楚。`image_urls` 里必须放**绝对地址**。列表页上的 `img src` 常常是相对路径，`media/cache/2c/da/xxx.jpg` 这种，直接丢给管道会下载失败。`response.urljoin()` 转一下再放进去。

媒体管道和普通管道在一个 `ITEM_PIPELINES` 字典里，靠数字排序。

| 数字 | 含义 |
| 1 到 100 | 通常放下载前的准备类管道 |
| 200 到 500 | 媒体管道放这一段 |
| 500 以上 | 清洗、校验、写库 |

顺序错了后果很具体。媒体管道排在写库管道后面，写库那一刻 `images` 字段还是空的，图片路径永远进不了数据库。数据看起来是对的，只是少了一列。

## 现成管道与自定义扩展点

### 1. 先把管道装上

最小的可用配置就三行。

```python
ITEM_PIPELINES = {
    "scrapy.pipelines.images.ImagesPipeline": 200,
}

IMAGES_STORE = "media_store"
```

在书城列表页上抓前 3 页，只塞 `image_urls`，剩下的交给管道。

```python
import scrapy

from bookmedia.items import BookItem

class BookCoverSpider(scrapy.Spider):
    name = "bookcovers"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    max_pages = 3

    def parse(self, response):
        page_no = int(response.meta.get("page_no", 1))
        for card in response.css("article.product_pod"):
            link = card.css("h3 a")
            yield BookItem(
                title=(link.attrib.get("title") or "").strip(),
                price=card.css("p.price_color::text").get(default="").strip(),
                detail_url=response.urljoin(link.attrib.get("href") or ""),
                # 字段名必须是 image_urls，而且是绝对地址
                image_urls=[response.urljoin(card.css("img::attr(src)").get())],
            )

        nxt = response.css("li.next a::attr(href)").get()
        if nxt and page_no < self.max_pages:
            yield response.follow(
                nxt, callback=self.parse, meta={"page_no": page_no + 1}
            )
```

跑完看统计。

![默认的哈希命名与目录结构](https://static.xiongneng.me/scrapy-06-default-tree-20260913062827.png)

```
'downloader/request_count': 64,
'elapsed_time_seconds': 4.898,
'file_count': 60,
'file_status_count/downloaded': 60,
'item_scraped_count': 60,
'request_depth_max': 2,
```

64 个请求拆开看是 60 张图加 3 个列表页，多出来的那一个是 robots.txt。60 个 item、60 个文件，一个不差。

### 2. 看它把文件落在哪

默认的命名是 URL 的 sha1，归档之后没人认得出哪张是哪本。目录结构倒是挺清楚。

```
media_store/
├── full/            <- 原图，文件名是 40 位哈希
└── thumbs/
    ├── small/       <- 80x80 框
    └── big/         <- 160x160 框
```

目录名不是配置项，是 `file_path()` 的返回值里带出来的。默认实现返回的是 `full/<sha1>.jpg`，`full/` 是这个函数写进去的。同理 `thumb_path()` 返回 `thumbs/<档位>/<sha1>.jpg`。

缩略图的档位来自 `IMAGES_THUMBS`，键名就是目录名。

```python
IMAGES_THUMBS = {
    "small": (80, 80),
    "big": (160, 160),
}
```

这里有个容易误会的细节。`(80, 80)` 不是「裁成 80 见方」，是**等比缩放的上限框**。原图 125x155 出来的是 64x80，不会变形也不会留白。

顺手说两个开关。`IMAGES_EXPIRES` 是过期天数，默认 90 天，重复跑同一批图不会重复下载。`IMAGES_MIN_WIDTH` 和 `IMAGES_MIN_HEIGHT` 能挡掉尺寸太小的图，占位图和像素点就是这么过滤掉的。

### 3. 接管落盘路径

默认命名看不下去的时候，就继承管道改三个方法。这三个方法就是媒体管道的全部扩展点。

```python
import hashlib
import os

from itemadapter import ItemAdapter
from scrapy import Request
from scrapy.pipelines.images import ImagesPipeline

def _slug(text, maxlen=48):
    """把书名压成安全的文件名。中文直接保留，只清掉路径敏感字符。"""
    keep = []
    for ch in text:
        if ch.isalnum() or ch in "-_":
            keep.append(ch)
        elif ch in " \t":
            keep.append("-")
    name = "".join(keep).strip("-") or "untitled"
    return name[:maxlen]

class NamedImagesPipeline(ImagesPipeline):
    def get_media_requests(self, item, info):
        adapter = ItemAdapter(item)
        page = adapter.get("detail_url") or ""
        for url in adapter.get("image_urls") or []:
            # 管道自己按请求指纹去重，不走调度器队列，所以 dont_filter 加不加都一样。
            # 这里写出来只是表明「重复的图片 URL 不会被静默丢掉」这层意思。
            yield Request(
                url,
                headers={"Referer": page} if page else {},
                dont_filter=True,
            )

    def file_path(self, request, response=None, info=None, *, item=None):
        title = _slug(ItemAdapter(item).get("title") or "") if item is not None else ""
        digest = hashlib.sha1(request.url.encode("utf-8")).hexdigest()[:8]
        # 目录自己定。默认实现返回 full/<sha1>.jpg，不写目录名文件就散在根下
        return "covers/%s-%s.%s" % (title, digest, self._ext(request.url))

    @staticmethod
    def _ext(url):
        tail = os.path.splitext(url.split("?")[0])[1].lstrip(".").lower()
        return tail or "jpg"
```

改完再跑一遍，60 张图全部进了 `covers/`，文件名从哈希变成了「书名加短哈希」。中文书名完好，`isalnum()` 对汉字返回真。

![接管 file_path 之后的文件名](https://static.xiongneng.me/scrapy-06-custom-path-20260913062827.png)

```
out/basic_store/
├── covers/            60 张，A-Light-in-the-Attic-281d7495.jpg 这种
└── thumbs/
    ├── small/         60 张
    └── big/           60 张
```

有个细节值得留意。缩略图仍然落在 `thumbs/<档位>/` 下面，文件名还是哈希。因为缩略图走的是 `thumb_path()`，我没改它。想让缩略图也换名字，就一样重写 `thumb_path()`。

⚠️ 这里有个 2.19 的新规矩。**不要重写 `__init__` 去接 `store_uri`**。父类的 `from_crawler()` 是这么调你的，`cls(settings["IMAGES_STORE"], crawler=crawler)`。你照抄老教程写一个 `def __init__(self, store_uri, download_func, settings)`，`crawler` 这个关键字参数没地方接，管道直接起不来。需要初始状态就放在 `open_spider()` 里。

### 4. 把失败也记下来

`item_completed()` 收到的是「成功和失败混在一起」的结果列表。默认实现只挑出成功的写进 `images`，失败的往日志里打一行就完了。

问题在于媒体文件的失败率并不低。防盗链、限流、超时，随便一个都能让图挂掉。而「这张图没下来」这件事如果没人记账，你只能靠数文件才发现少了。

```python
    def item_completed(self, results, item, info):
        adapter = ItemAdapter(item)
        ok, bad = [], []
        for success, value in results:
            if success:
                ok.append(value)
                continue
            # 失败项是 Twisted 的 Failure，直接 str() 会得到一整段 traceback
            if hasattr(value, "getErrorMessage"):
                bad.append("%s: %s" % (value.type.__name__, value.getErrorMessage()))
            else:
                bad.append(str(value))
        adapter["images"] = ok
        adapter["image_errors"] = bad
        return item
```

故意塞一个不存在的地址试一下，三个 URL 里坏一个。

```
'file_count': 2,
'file_status_count/downloaded': 2,
```

导出的 item 里看到记账生效了。

```json
"images": [
  {"url": "http://127.0.0.1:8412/image/1.png",
   "path": "covers/混合好坏的图片集-82a839d6.png",
   "checksum": "08bc85fb581f1551a146aaa240b6c610",
   "status": "downloaded"}
],
"image_errors": ["FileException: "]
```

啰嗦一句 `image_errors` 这个字段。dataclass item 上写一个**没声明过的**字段不会报错，但它也不会被导出。字段得先在 item 里声明好，不然「记了账」和「没记账」看起来一模一样。

## 容易栽的跟头

**坑 1：字段名写错，管道安静地什么都不干。** 输入字段必须叫 `image_urls`，输出字段必须叫 `images`，文件管道对应 `file_urls` 和 `files`。名字改了管道就找不到活干，而且它不报错。我试过把 `image_urls` 写成 `img_urls`，爬虫正常跑完、item 正常导出，只是 `images` 那一列永远是空的。这类静默失效靠日志发现不了，只能靠统计里的 `file_count`。

**坑 2：`image_urls` 里放相对地址。** 列表页上的 `img src` 常常写成 `media/cache/2c/da/xxx.jpg`，直接丢给管道会下载失败。管道不会替你补全，得先用 `response.urljoin()` 转成绝对地址。

**坑 3：图片管道没装 Pillow。** `ImagesPipeline` 在构造时会去 import `PIL`，失败就抛 `NotConfigured("ImagesPipeline requires installing Pillow 8.3.2 or later")`。而 `NotConfigured` 在管道这一层的表现是**这个管道被跳过**，爬虫照跑、item 照样导出，只是 `images` 字段永远是空的。我当初就是这么踩进去的，装了 scrapy 却没装 extras，跑了两轮才发现盘上一张图都没有。2.18 起官方给了 extras，装的时候写 `pip install "scrapy[images]"` 就不会漏。

**坑 4：媒体管道排在写库管道后面。** `ITEM_PIPELINES` 里的数字越小越先执行。媒体管道放到 600、写库放到 300，写库那一刻 `images` 还没填上，路径永远进不了库。数据能入库、页面上看不出错，只是少了一列。**媒体管道一律排在 200 段。**

**坑 5：失败项直接 `str()` 打进日志。** `item_completed` 收到的失败项是 Twisted 的 `Failure`，`str()` 出来是一整段 traceback。要拿一行可读的错误，用 `value.getErrorMessage()`，`value.type.__name__` 能给出异常类型。

**坑 6：给 item 加了个没声明的字段。** dataclass item 上写一个没声明过的字段不会报错，但它也不会被导出。我记图片失败用的那个 `image_errors`，是先在 item 类里声明了才出现在导出结果里的。你要是临时往实例上挂一个键，导出的文件里不会有这一列，于是「记了账」和「没记账」看起来一模一样。

**坑 7：重写 `__init__` 去接 `store_uri`。** 2.19 起父类的 `from_crawler()` 是这么调你的，`cls(settings["IMAGES_STORE"], crawler=crawler)`。照抄老教程写一个 `def __init__(self, store_uri, download_func, settings)`，`crawler` 这个关键字参数没地方接，管道直接起不来。需要初始状态就放在 `open_spider()` 里。

## 小结

这一篇就一件事，让文件稳稳当当地落在地上。

两个约定记住了就够用。媒体请求绕开调度器，但没绕开域的并发额度。字段名必须叫 `image_urls` 和 `images`，改名等于关掉管道，而且没有任何提示。

扩展点就三个。`get_media_requests` 管请求怎么发，`file_path` 管文件叫什么、放哪儿，`item_completed` 管收尾和记账。

我自己的感受是，媒体管道这一块最值得花时间的地方不在下载，在记账。图的失败率天生比文字高，防盗链、限流、超时随便一个都能让图挂掉。把失败记进 item，后面排查才有线索。

说到底，这事儿的难点不在把图抓下来，在抓不下来的时候你能知道。其实吧，字段名写错和管道顺序写错这两个最容易出问题的点，都是零报错的。日志里干干净净，统计里那几个数字才是唯一线索。

这篇里要是有哪里讲得不对，欢迎拍砖。
