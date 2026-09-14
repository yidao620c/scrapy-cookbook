# 每天15分钟玩转Scrapy03 - 数据建模与落库

## 开场

上一篇我们抓到了 50 位作家的档案，parse 里写的是 `yield {"name": ..., "birthdate": ...}`。

跑通了，但抓完我盯着那段代码看了很久，我一直觉得这事儿得改。

4 个字段的字典已经有点长了。要是换成商品详情页那种二十多个字段的站点，这个函数会长成什么样。名字、价格、库存、规格，每个字段的清洗逻辑都挤在一起。改一个字段，要在一堆 `.strip()` 里翻半天。

还有个更隐蔽的麻烦。字典是没有形状的。`item["auther"]` 拼错一个字母，Python 不会拦你。它会安静地产出一个多了一个键的字典，一路顺到导出文件里，等你哪天发现作者名全是空的才回头查。

导出成 JSON 文件也只是临时方案。真要落地的时候，数据得进数据库。

这一篇解决三件事。给数据定一个型，把清洗逻辑从 parse 里搬出去，让抓到的数据自己流进文件和数据库。

先看清全局。一条数据从响应里被抠出来，到最后躺进 SQLite，中间要经过这么几道手。

![数据从响应到落库的完整链路](https://static.xiongneng.me/scrapy-03-item-lifecycle-20260912231500.png)

## Item：给数据定个型

Item 是 Scrapy 里给数据定型的东西。你可以把它理解成一张表的结构声明，先写清楚有哪些字段，再往里塞值。

Scrapy 2.17 起，`startproject` 生成的 `items.py` 默认模板换成了 `@dataclass` 写法。以前那套 `scrapy.Item` 加 `Field()` 仍然能用，官方没有废弃它的意思。

两种写法长得不一样，出来的效果一样。这是本篇的项目里定义的 Item。

```python
"""Item 定义：给抓到的数据定一个型。

2.17 起 startproject 生成的默认模板就是 @dataclass 写法（scrapy.Item 仍然可用）。
字段的定义顺序就是导出顺序，2.17 起按定义顺序返回。
"""

from dataclasses import dataclass


@dataclass
class QuoteItem:
    """一条名言。"""

    text: str | None = None         # 名言正文，已压平空白
    author: str | None = None       # 作者
    author_slug: str | None = None  # 作者页标识，管道里从链接推出来
    tags: list[str] | None = None   # 标签列表
    text_len: int | None = None     # 正文长度，管道里算
    fingerprint: str | None = None  # 去重指纹，管道里算
```

六个字段，其中两个是管道里补算出来的。这一点后面会展开。

`@dataclass` 的写法有个直接好处，你的编辑器知道 `QuoteItem` 有哪些字段。敲 `item.` 的时候会自动补全，赋值类型不对的时候静态检查工具会给你标出来。字典给不了这个。

字段的定义顺序就是导出顺序，这是 2.17 起的行为。我实测对比过两种写法。

```
== 1. 字段顺序从哪来 ==
OldItem.fields        -> ['text', 'author']
NewItem has .fields?  -> False
ItemAdapter(NewItem).asdict() -> {'text': 'hi', 'author': 'me'}
ItemAdapter(OldItem).asdict() -> {'text': 'hi', 'author': 'me'}
```

这里藏着本篇第一个坑。`scrapy.Item` 风格有 `.fields`，`@dataclass` 风格没有。很多老教程、老代码里都在用 `QuoteItem.fields`，你照抄到新项目里会直接 `AttributeError`。想拿字段清单，2.19 里的正确入口是 `ItemAdapter`。

那 Item 到底该管什么。

我的理解是这样。Item 只负责两件事，声明有哪些字段，装字段的值。至于这个值是原始的还是清洗过的，是页面里直接取的还是算出来的，Item 不关心。

把清洗逻辑写进 Item 的 `__post_init__`，或者写成 property，技术上做得到，但会让数据的形状和数据的加工搅在一起。你想想看，形状是形状，加工是加工，两样缠在一起，以后想单独换掉哪一边都难。

Scrapy 把加工这部分活单独挪到了另一个地方。

## ItemLoader 与处理器：把清洗搬出 parse

先看 parse 里的现状。

```python
for box in response.css("div.quote"):
    yield {
        "text": box.css("span.text::text").get(default="").strip(),
        "author": box.css("small.author::text").get(default="").strip(),
        "tags": box.css("div.tags a.tag::text").getall(),
    }
```

这段代码把两件事混在了一起。一件事是在页面里哪个位置取值，另一件是取出来的值怎么收拾。字段一多，这两件事就缠成一团。

ItemLoader 的思路是把它们分开。parse 只负责声明「在哪里取」，怎么收拾交给处理器。

```python
from itemloaders import ItemLoader
from itemloaders.processors import Identity, MapCompose, TakeFirst

from quotesitem.items import QuoteItem


def flatten_ws(value):
    """压平空白，顺便把弯引号换成直引号。"""
    if value is None:
        return None
    return " ".join(str(value).split()).replace("“", '"').replace("”", '"')


def pick_slug(value):
    """从 /author/Albert-Einstein 里取出 Albert-Einstein。"""
    if not value:
        return None
    return str(value).rstrip("/").rsplit("/", 1)[-1]


class QuoteLoader(ItemLoader):
    """字段级处理器 > Field 元数据 > Loader 默认，三级优先级从高到低。"""

    default_item_class = QuoteItem
    default_input_processor = MapCompose(flatten_ws)
    default_output_processor = TakeFirst()   # 默认只留第一个结果

    tags_out = Identity()                    # 标签要保留成列表，不能走 TakeFirst
    author_slug_in = MapCompose(pick_slug)
```

处理器分两段，输入处理器管「值进来时怎么处理」，输出处理器管「值攒齐了怎么交出去」。

三级优先级的判断顺序是固定的，从高到低这么排。

1. 字段级处理器，像上面的 `tags_out` 和 `author_slug_in`，只作用于那一个字段
2. Field 元数据里的处理器，`scrapy.Item` 风格下可以写 `Field(input_processor=...)`
3. Loader 的默认处理器，`default_input_processor` 和 `default_output_processor`

查找时从高往低走，命中一个就不再往下找。

![处理器三级优先级的查找顺序](https://static.xiongneng.me/scrapy-03-processor-priority-20260912231500.png)

常用的处理器就那几个。

1. `MapCompose`，把一批函数串起来逐个作用到每个值上，输入处理器里用得最多
2. `TakeFirst`，只留第一个结果，输出处理器的默认值就是它
3. `Identity`，原样返回，用在你想取消默认行为的地方
4. `Join`，把多个值拼成一个字符串，比如把多个标签拼成逗号分隔
5. `Compose`，跟 MapCompose 像，但它把整批值当一个整体处理，不是逐个

上面那个 `tags_out = Identity()` 值得单独说一句。默认输出处理器是 `TakeFirst`，而标签是个列表，一页上有 change、deep-thoughts、thinking、world 四个。要是不给 `tags` 单独指定 `Identity`，这四个标签会被 `TakeFirst` 砍掉三个，只剩第一个。这种错误很安静，数据能出来、能入库，只是少了一截。

`author_slug_in = MapCompose(pick_slug)` 是输入处理器的用法。页面上给的是 `/author/Albert-Einstein`，我们不想要前面的路径，也不要末尾的斜杠，`pick_slug` 就负责把这串收拾成 `Albert-Einstein`。

现在看 parse 长什么样。

```python
import scrapy

from quotesitem.items import QuoteItem
from quotesitem.loaders import QuoteLoader


class QuotesItemSpider(scrapy.Spider):
    """抓名言 → ItemLoader 清洗 → 管道去重落库。"""

    name = "quotesitem"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/"]

    def parse(self, response):
        for box in response.css("div.quote"):
            loader = QuoteLoader(item=QuoteItem(), selector=box)
            loader.add_css("text", "span.text::text")
            loader.add_css("author", "small.author::text")
            loader.add_css("author_slug", "span a::attr(href)")
            loader.add_css("tags", "div.tags a.tag::text")
            yield loader.load_item()

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
```

parse 里剩下的全是「取什么」，一行清洗代码都没有。

`add_css` 之外还有 `add_xpath` 和 `add_value`。最后一个用来塞页面里没有的值，比如你把上一页的某个字段用 `meta` 带过来，再用 `add_value` 补进 Item。

还有几个方法知道一下就行。`get_value`、`get_output_value` 可以中途看一眼处理器算出来的结果，调试的时候有用。`replace_css` 是先把已有值清空再添加，适合覆盖场景。

有个细节我当初绕了一圈。`loader.add_css` 可以调多次，同一个字段调两次就是两个值。输入处理器是逐个作用在值上的，这一点跟输出处理器的差别要分清楚。

## 管道：数据的最后一道工序

Item 从 Spider 出来之后，还不会直接落地。中间会经过管道。

管道就是一个普通的 Python 类，实现 `process_item` 就够了。每个 Item 路过，它处理一次，然后交给下一个。数字小的先跑。

本篇写了四条，分工各自明确。

1. `EnrichPipeline` 补算派生字段，正文长度和去重指纹
2. `DedupPipeline` 内存去重，重复的直接丢
3. `JsonlPipeline` 写 JSONL 文件
4. `SQLitePipeline` 写 SQLite

队列顺序是有讲究的。补算必须在去重之前，因为去重的指纹是补算出来的。去重又必须在写盘之前，不然重复数据已经进文件了，丢也没意义。

四条管道排队走过，一条数据的一生就这么结束了。

![四条管道的数据流](https://static.xiongneng.me/scrapy-03-pipeline-flow-20260912231500.png)

```python
import hashlib
import json
import sqlite3
from pathlib import Path

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class EnrichPipeline:
    """补算派生字段：正文长度与去重指纹。"""

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        text = adapter.get("text") or ""
        author = adapter.get("author") or ""
        adapter["text_len"] = len(text)
        adapter["fingerprint"] = hashlib.sha1(
            f"{text}|{author}".encode("utf-8")
        ).hexdigest()[:16]
        return item


class DedupPipeline:
    """内存去重。重复的直接 DropItem，后面的管道就不会再看到它。"""

    def __init__(self):
        self.seen = set()
        self.dropped = 0

    def process_item(self, item, spider):
        fp = ItemAdapter(item)["fingerprint"]
        if fp in self.seen:
            self.dropped += 1
            raise DropItem(f"重复名言已丢弃: {fp}")
        self.seen.add(fp)
        return item

    def close_spider(self, spider):
        spider.crawler.stats.set_value("dedup/dropped", self.dropped)
        spider.logger.info("去重管道丢掉了 %d 条重复", self.dropped)
```

三个知识点藏在上面这段里。

第一个是 `DropItem`。抛这个异常等于告诉框架，这一条不要了。后面的管道收不到它，feed 导出也不会写它，`item_scraped_count` 也不计它。实测里能同时看到 `item_dropped_count` 和 `dedup/dropped` 两个统计。

第二个是 `close_spider`。管道持有的资源在这里收尾，比如内存里的去重集合在这个时点把统计结果写进 stats。写文件、关数据库连接也在这个钩子里做。

第三个是 `ItemAdapter`。管道里取字段用 `adapter["xxx"]` 而不是 `item["xxx"]` 或者 `item.xxx`，这是为了兼容两种 Item 风格。`@dataclass` 风格用属性访问，`scrapy.Item` 用下标访问，`ItemAdapter` 把这两套统一了。你写的管道想给两种 Item 复用，就得走这个入口。

接着看写盘的两条。

```python
class JsonlPipeline:
    """写 JSONL。文件在 open_spider 打开、close_spider 关闭。"""

    def open_spider(self, spider):
        path = Path(spider.settings.get("JSONL_PATH", "quotes_pipeline.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = path.open("w", encoding="utf-8")
        self.count = 0

    def process_item(self, item, spider):
        self.fh.write(json.dumps(ItemAdapter(item).asdict(), ensure_ascii=False) + "\n")
        self.count += 1
        return item

    def close_spider(self, spider):
        self.fh.close()
        spider.logger.info("JSONL 写出 %d 条", self.count)


class SQLitePipeline:
    """写 SQLite。fingerprint 做主键，天然防重复入库。"""

    def __init__(self):
        self.conn = None
        self.rows = 0

    @classmethod
    def from_crawler(cls, crawler):
        """要用到 settings 的管道就实现这个类方法。"""
        pipeline = cls()
        pipeline.db_path = crawler.settings.get("SQLITE_PATH", "quotes.db")
        return pipeline

    def open_spider(self, spider):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                fingerprint TEXT PRIMARY KEY,
                text        TEXT NOT NULL,
                author      TEXT,
                author_slug TEXT,
                tags        TEXT,
                text_len    INTEGER
            )
            """
        )

    def process_item(self, item, spider):
        a = ItemAdapter(item)
        self.conn.execute(
            "INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?,?)",
            (a["fingerprint"], a["text"], a["author"], a["author_slug"],
             ",".join(a.get("tags") or []), a["text_len"]),
        )
        self.rows += 1
        return item

    def close_spider(self, spider):
        self.conn.commit()
        self.conn.close()
        spider.logger.info("SQLite 写入 %d 条 → %s", self.rows, self.db_path)
```

`from_crawler` 是管道的另一个入口。需要读 settings 的时候实现它，框架会传一个 crawler 对象进来，你从 `crawler.settings` 里取值。不实现这个方法也完全可以，框架会退回去用无参构造。

还有个点是 `INSERT OR IGNORE` 配合主键。内存去重管的是这一次运行，数据库主键管的是跨次运行。第二次跑同一个站点，内存里的 `seen` 是空的，但主键会拦下已经入库的记录。这是两层保险。

至于 `FEEDS`，它是跟管道平行的另一条出口，不需要写代码。在 settings 里声明就行。

```python
FEEDS = {
    "out/quotes_feed.jsonl": {
        "format": "jsonlines",
        "encoding": "utf-8",
        "fields": ["text", "author", "author_slug", "tags", "text_len"],
    },
}
```

`fields` 是个好用的过滤参数。数据库里存 6 个字段，导出给外部用的文件只给 5 个，把内部算出来的 `fingerprint` 挡掉。2.19 起 `format` 还能按文件扩展名自动推断，写清楚更稳，我习惯显式写着。

现在把四条管道挂上去。

```python
ITEM_PIPELINES = {
    "quotesitem.pipelines.EnrichPipeline": 200,
    "quotesitem.pipelines.DedupPipeline": 300,
    "quotesitem.pipelines.JsonlPipeline": 400,
    "quotesitem.pipelines.SQLitePipeline": 500,
}

JSONL_PATH = "out/quotes_pipeline.jsonl"
SQLITE_PATH = "out/quotes.db"
```

## 实战：抓名言、去重、落库

零件都齐了，跑起来看结果。

### 1. 跑主蜘蛛

一条命令，把 100 条名言抓下来，去重、写 JSONL、写 SQLite 一次做完。

```bash
scrapy crawl quotesitem
```

统计输出是真实的。

```
2026-09-12 23:04:41 [quotesitem] INFO: SQLite 写入 100 条 → out/quotes.db
2026-09-12 23:04:41 [quotesitem] INFO: JSONL 写出 100 条
2026-09-12 23:04:41 [quotesitem] INFO: 去重管道丢掉了 0 条重复
2026-09-12 23:04:41 [scrapy.extensions.feedexport] INFO: Stored jsonlines feed (100 items) in: out/quotes_feed.jsonl
{'dedup/dropped': 0,
 'downloader/request_count': 11,
 'elapsed_time_seconds': 14.10387329999503,
 'feedexport/success_count/FileFeedStorage': 1,
 'finish_reason': 'finished',
 'item_scraped_count': 100,
 'request_depth_max': 9,
 'robotstxt/request_count': 1,
 'scheduler/enqueued': 10}
```

几个数字对着看一遍。100 条名言，11 个请求，10 个列表页加一次 robots.txt 探测。`request_depth_max` 是 9，翻页翻到第 10 页的意思。去重丢 0 条，因为这个站点本身没有重复内容。耗时 14 秒，11 个请求就把整个站点翻了一遍。

三条出口都写成了同一份数据，说明管道链路是通的。

### 2. 校验落库结果

光看日志不算数，打开数据库核一遍。

```python
import sqlite3

c = sqlite3.connect("out/quotes.db")
print("quotes:", c.execute("select count(*) from quotes").fetchone()[0])
print("作者数:", c.execute("select count(distinct author) from quotes").fetchone()[0])
print("最长一条:", c.execute("select text_len, author from quotes order by text_len desc limit 1").fetchone())
```

```
quotes: 100
作者数: 50
最长一条: (1084, 'Marilyn Monroe')
```

100 条名言，50 位作者，跟上一篇抓到的作者数对上了。最长的一条 1084 个字符，来自 Marilyn Monroe。

建表语句也落对了，六个字段一个不少，`fingerprint` 是主键。

```
CREATE TABLE quotes (
    fingerprint TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    author      TEXT,
    author_slug TEXT,
    tags        TEXT,
    text_len    INTEGER
)
```

再看一行真实数据，注意 `tags` 字段和 `text_len` 字段，前者来自 `Identity` 处理器保住的列表，后者是管道算出来的。

```
{"text": "\"The world as we have created it is a process of our thinking. It cannot be changed without changing our thinking.\"", "author": "Albert Einstein", "author_slug": "Albert-Einstein", "tags": ["change", "deep-thoughts", "thinking", "world"], "text_len": 115, "fingerprint": "10216be1eb2f786e"}
```

正文里的弯引号被 `flatten_ws` 换成了直引号。这是有意做的，弯引号进数据库以后在别的系统里容易变成乱码。

### 3. 用别名蜘蛛验证去重

去重管道跑了 0 条，等于没验证。我另写了一个蜘蛛，故意给两个 URL 喂同样内容。

```python
from quotesitem.spiders.quotes_item import QuotesItemSpider


class QuotesAliasSpider(QuotesItemSpider):
    """同一份内容挂在两个 URL 上（常见的别名情况），用来验证去重管道。"""

    name = "quotesalias"
    start_urls = [
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/page/1/",
    ]
```

首页和第一页内容完全一样，只是地址不同。跑起来。

```bash
scrapy crawl quotesalias -s SQLITE_PATH=out/alias.db -s JSONL_PATH=out/alias_pipeline.jsonl
```

```
2026-09-12 23:05:04 [quotesalias] INFO: SQLite 写入 100 条 → out/alias.db
2026-09-12 23:05:04 [quotesalias] INFO: JSONL 写出 100 条
2026-09-12 23:05:04 [quotesalias] INFO: 去重管道丢掉了 10 条重复
{'dedup/dropped': 10,
 'dupefilter/filtered': 1,
 'downloader/request_count': 12,
 'item_dropped_count': 10,
 'item_dropped_reasons_count/DropItem': 10,
 'item_scraped_count': 100,
 'finish_reason': 'finished'}
```

这里有两层去重同时在干活，值得看清楚。

框架的调度器先拦了一层。`/page/2/` 这个地址从首页能提取到，从第一页也能提取到，但它是同一个 URL，第二次就被指纹过滤器挡下，`dupefilter/filtered` 记了 1 次。

我们自己的管道拦了第二层。第一页那 10 条名言地址不同、内容相同，框架的 URL 去重管不了这种，得靠内容指纹。`item_dropped_count` 是 10，`dedup/dropped` 也是 10，两个统计说的是同一件事。

最终落库 100 条。要是没有这条管道，同样 100 条数据会被写两遍。

### 4. 对照三个出口

最后确认三份产物条数一致，一份没多一份没少。

```python
import json

for name in ("out/quotes_pipeline.jsonl", "out/quotes_feed.jsonl"):
    n = sum(1 for line in open(name, encoding="utf-8") if line.strip())
    print(name, "->", n, "条")
```

```
out/quotes_pipeline.jsonl -> 100 条
out/quotes_feed.jsonl -> 100 条
```

JSONL 100 条，feed 100 条，SQLite 100 行。三条出口合上了。

feed 文件里比 JSONL 少一个 `fingerprint`，那是 `fields` 过滤起的作用。

回头看这一篇搭起来的东西，Item 定了数据的形状，Loader 把清洗从 parse 里摘出来，管道负责加工和落地。parse 现在只剩四行取值代码。

以后站点改版，选择器变了只改 parse，清洗规则变了只改处理器，落库方式变了只改管道。三件事各归各处，互不打扰。

## 容易栽的跟头

**坑 1：在 `@dataclass` 风格的 Item 上找 `.fields`。** 老教程里遍地都是 `QuoteItem.fields`，但那是 `scrapy.Item` 的属性。2.17 换了默认模板之后，`@dataclass` 写的 Item 上没有这个属性，照抄会直接 `AttributeError`。我实测过，`hasattr(QuoteItem, "fields")` 是 `False`。你看，两种写法连查字段的入口都不一样，从老代码往新项目迁移的时候特别容易漏这一步。要拿字段清单，用 `ItemAdapter(item)` 来操作。

**坑 2：给 Item 赋一个没声明的字段，它不报错。** 这是 `@dataclass` 风格最容易欺骗人的地方。实测里 `item.nope = 1` 一路通过，因为 dataclass 实例本来就允许挂普通属性。你以为字段加上了，其实没有。好消息是它不会被导出，`ItemAdapter(item).asdict()` 只会返回声明过的字段，所以错误表现为「数据静默消失」而不是「多出一个字段」。写管道的时候发现某个字段总是空的，先回去看 Item 里声明了没有。

```
NewItem: n.nope = 1 通过了，值 = 1
asdict() -> {'text': 'hi', 'author': 'me'}
```

对照一下 `scrapy.Item` 风格，它拦得住。`item["nope"] = 1` 抛 `KeyError`，`item.nope = 1` 抛 `AttributeError` 并提示改用下标写法。同一个错误，两种风格一个静默一个报错。

**坑 3：列表字段被默认的 `TakeFirst` 砍成一个值。** `default_output_processor` 默认是 `TakeFirst`，它只留第一个结果。标签、图片链接、规格参数这类本来就是多个值的字段，必须单独指定 `tags_out = Identity()` 之类的处理器，否则你会拿到一个看起来很正常、其实少了一半数据的 Item。这个坑不报错，最容易被忽略。

**坑 4：管道顺序写反。** `ITEM_PIPELINES` 是数字小的先跑，跟直觉里的「列表从上到下」不一样。把去重放在写盘后面，重复数据早就写进文件了。把补算指纹放在去重后面，去重管道拿到的是 `None`，所有数据会被当成同一条。我这次的顺序是 200 补算、300 去重、400 写 JSONL、500 写数据库，每一步都依赖前一步的结果。

**坑 5：管道持有的文件或连接不在 `close_spider` 里关。** `open_spider` 里开了文件、连了数据库，就必须在 `close_spider` 里配对关掉。少了这一步，SQLite 的事务不提交，进程退出后数据一条都看不到。我这次的 `SQLitePipeline` 就是在这个钩子里 `commit` 加 `close`，写 JSONL 的那条也是在这里关文件。

**坑 6：在管道里用 `item["field"]` 或者 `item.field` 硬取字段。** 这两种写法各自绑死一种 Item 风格。管道用 `ItemAdapter(item)` 包一层，两种风格都能跑。字段不存在时用 `.get()` 而不是下标，`.get()` 返回 `None`，下标会抛 `KeyError`。

**坑 7：`FEEDS` 的 `fields` 里写了不存在的字段名。** `fields` 这个过滤参数不会校验字段名，写错了就是那一列在你导出的文件里凭空消失，没有报错也没有警告。导出文件比预期的短，先回来检查这里。

**坑 8：以为 `DropItem` 之后还会走完剩余的管道。** 抛出 `DropItem` 的瞬间这条数据的旅程就结束了，后面所有管道都收不到它。想让数据「打个标继续往下走」，用的是给字段赋值，不是抛异常。想区分统计，可以自定义异常类继承 `DropItem`，`item_dropped_reasons_count` 会按异常类名分开计数。

## 小结

这一篇把数据从 Spider 到存储的整条路铺完了。

Item 管形状。用它声明字段，等于给数据立了一份契约，也顺手拿到了编辑器的自动补全。

ItemLoader 和处理器管清洗。parse 退回到只做一件事，声明在哪里取值。怎么收拾交给处理器，三级优先级从字段级一路查到 Loader 默认。

管道管加工和落地。补算、去重、写文件、写数据库，四条各干一样，顺序由数字决定。

实测那一段是本篇的骨架。100 条名言，11 个请求，两条去重防线，三份产物条数一致。说到底，数据不是从页面上抓下来就算完了，得能安静地躺进数据库里才算数。

有个判断标准可以带走。你的 parse 里散着三处以上的 `.strip()`，或者出现 `if value else None` 这种兜底，就该把清洗搬进处理器了。

说真的，这几条管道的写法我一开始也总是记混顺序。跑一次，看一眼 stats 里的 `item_dropped_count`，就全明白了。这篇里要是有哪里讲得不对，欢迎拍砖。
