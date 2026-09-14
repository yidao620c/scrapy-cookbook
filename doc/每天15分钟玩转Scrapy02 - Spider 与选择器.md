# 每天15分钟玩转Scrapy02 - Spider 与选择器

## 开场

上一篇我们把爬虫跑起来了，但 `parse` 里那几行选择器是从官方教程抄的。

抄完心里发虚。为什么写 `span.text::text` 而不是 `.text`？`::attr` 和 `@href` 到底什么时候用哪个？

我当初刚上手那会儿，选择器基本靠试。改一个字符跑一次，看输出对不对，不对再改回来。一个下午就耗在这上面。

我特别理解那种对着输出反复试的烦躁，所以这一篇我打算换个讲法。

坦率的讲，这不算笨，是没人把这两件事讲清楚过。

这一篇就把它们说透。前半程讲 Spider 到底怎么被框架驱动，后半程把选择器从抄变成写，最后拿一个真实的抓取任务，把两段式爬虫组装起来。

## Spider 是怎么跑起来的

Spider 是你跟框架签的一份合同，里面只写三件事，从哪里开始、拿到页面交给谁、产出什么样的数据。

至于调度、下载、并发、去重，全是框架自己的活。

框架驱动一只 Spider 的顺序是固定的。它先调用 `start()` 拿到一批初始请求。每个请求下载完，框架就把响应交给注册在它上面的回调函数。回调跑完，产出的数据进管道，产出的新请求回到调度器排队。请求耗尽，爬虫结束。

有个细节我想单独拎出来说。回调函数可以继续产出请求，而这些请求又能注册新的回调。

就是这条链，让爬虫能一层层往下走，从列表页走到详情页，再从详情页走到作者主页。第一篇里那个 `parse` 递归调用自己，是最简单的用法。

四个要素构成一只 Spider。

1. `name`：蜘蛛名，项目内唯一，`scrapy crawl` 后面跟的就是它
2. `allowed_domains`：白名单，不在这个域内的链接会被 `OffsiteMiddleware` 静默丢掉
3. 起始请求：用 `start_urls` 或 `async def start()` 提供
4. 回调函数：默认是 `parse`，可以在 `Request` 里用 `callback` 指定别的名字

回调函数可以返回四类东西，框架都接得住。字典或者 `Item` 算数据，`Request` 算新任务，`None` 表示什么都不产出，这四者组成的迭代对象同样可以。所以在一个函数里 `yield` 字典和 `yield` 请求混着写，完全正常。

还有两个成员容易被忽略。`errback` 用来接管失败的请求，它拿到的是 `Failure` 对象而不是响应，抓的目标不稳定的时候值得配上。`self.logger` 是框架给每只 Spider 配好的日志器，打出来的日志会带蜘蛛名，同时跑好几个爬虫的时候特别好用。

```python
import scrapy


class QuotesSpider(scrapy.Spider):
    """Spider 的四要素与回调链。"""

    name = "quotes"                              # 要素一：唯一的名字
    allowed_domains = ["quotes.toscrape.com"]    # 要素二：域白名单
    start_urls = ["https://quotes.toscrape.com/"]  # 要素三：起始请求

    def parse(self, response):                   # 要素四：默认回调
        self.logger.info("正在处理 %s", response.url)

        # 产出数据
        for quote in response.css("div.quote"):
            yield {
                "text": quote.css("span.text::text").get(),
                "author": quote.css("small.author::text").get(),
            }

        # 产出新任务：作者主页另找函数处理，别挤在 parse 里
        for link in response.css("div.quote span a::attr(href)").getall():
            yield response.follow(link, callback=self.parse_author)

    def parse_author(self, response):
        yield {
            "name": response.css("h3.author-title::text").get(default="").strip(),
            "birthdate": response.css(".author-born-date::text").get(default="").strip(),
        }
```

这种把列表页和详情页拆成两个回调的做法，是所有爬虫的通用骨架。好处很直接，每个函数只关心一种页面结构，站点改版的时候也只改一处。

![Spider 的生命周期与回调链](https://static.xiongneng.me/scrapy-02-lifecycle.png)

## CSS 选择器

`response.css()` 返回的不是字符串，是一个 `SelectorList`，里面装着若干个 `Selector`。

这个设计决定了它的两层用法，先选中节点，再从节点里取数据。

取数据有四个方法，分工明确。

1. `.get()`：取第一个匹配项，没有就返回 `None`
2. `.getall()`：取全部匹配项，返回列表，没有就是空列表
3. `.get(default="")`：取不到时返回你指定的默认值，比 `None` 好处理
4. `.attrib`：直接把选中节点的属性字典取出来

至于选中什么，由选择器写法决定，三种写法对应三种结果。

1. `title` 选中整个标签，`.get()` 拿到 `<title>Quotes to Scrape</title>`
2. `title::text` 只取标签里的文本，`.get()` 拿到 `Quotes to Scrape`
3. `a::attr(href)` 只取指定属性，`.get()` 拿到 `/page/2/`

在 shell 里跑一遍这几条，下面每一条输出都是实测结果。

```python
>>> response.css("title").get()
'<title>Quotes to Scrape</title>'

>>> response.css("title::text").get()
'Quotes to Scrape'

>>> response.css("div.quote span.text::text").get()[:40]
'“The world as we have created it is a pro'

>>> response.css("div.tags a.tag::text").getall()[:4]
['change', 'deep-thoughts', 'thinking', 'world']

>>> response.css("li.next a").attrib
{'href': '/page/2/'}
```

`SelectorList` 还能继续往下选，这就是嵌套选择器。它的意义在于先把搜索范围收窄到一条记录里，再在记录内部找字段。页面上就算有几十个同类元素，也互不干扰。

```python
>>> first = response.css("div.quote")[0]
>>> first.css("span.text::text").get()[:30]
'“The world as we have created '

>>> first.css("small.author::text").get()
'Albert Einstein'
```

嵌套时有个相对性的问题。`first.css(...)` 表示在这个节点内部找，写法上没问题。换成 XPath 就要小心了，这一点下一节细说。想先看一眼实际效果，就在 shell 里直接试，比对着文档猜快得多。

选择器还有个福利，CSS3 的属性匹配语法可以直接用，比如 `a[href*="image"]` 表示 href 里包含 image。不过真到抓取的时候，更常见的做法是先复制浏览器开发者工具给出的选择器，再在 shell 里逐步简化。一次写出完美表达式这件事，我也没做到过。

## XPath 与正则

CSS 能覆盖八成场景，剩下两成要靠 XPath。

XPath 的独门本事是按内容和按位置来选，这是 CSS 做不到的。

有三个需求 CSS 无解，选中所有包含某段文字的链接、按文本内容定位元素、从当前节点往上找父节点。对应到 XPath 就是下面这些写法。

| 需求 | XPath 写法 |
|--------|------------------|
| 按文本内容找链接 | `//a[contains(., "Next")]/@href` |
| 按属性值找元素 | `//small[@class="author"]/text()` |
| 只取第一个匹配 | `(//div[@class="quote"])[1]` |
| 取所有匹配 | `//div[@class="quote"]` |
| 往上找父节点 | `//span[@class="text"]/../..` |

实测跑一遍，输出如下。

```python
>>> response.xpath('//small[@class="author"]/text()').getall()[:3]
['Albert Einstein', 'J.K. Rowling', 'Albert Einstein']

>>> response.xpath('//a[contains(., "Next")]/@href').get()
'/page/2/'

>>> response.xpath('//div[@class="tags"]/a/@href').getall()[:3]
['/tag/change/page/1/', '/tag/deep-thoughts/page/1/', '/tag/thinking/page/1/']
```

嵌套 XPath 有个差别必须记住。CSS 嵌套是天然的相对查找，XPath 不是。以 `//` 开头会跳回文档根节点重新搜，只有在前面加一个点变成 `.//` 才表示在当前节点内部找。

```
>>> quotes = response.xpath('//div[@class="quote"]')   # 10 条名言
>>> len(quotes.xpath('.//small[@class="author"]'))     # 在每条名言内部找作者
10
```

还有个近义写法的坑，`//node[1]` 和 `(//node)[1]` 结果完全不同。前者是每个父节点下的第一个 node，后者才是全文第一个 node。刚上手时写错这个，会拿到一堆莫名其妙的结果。

需要按位置取的时候，实测对比是这样。

```python
>>> len(response.xpath('//div[@class="quote"]'))
10
>>> len(response.xpath('(//div[@class="quote"])[1]'))
1
```

最后是正则。选中的文本往往还带着引号、多余空格、编号，这时候用 `.re()` 和 `.re_first()` 在结果上做二次清洗，比再写一层选择器省事得多。

```python
>>> response.css("span.text::text").re(r"([A-Z][a-z]+) is")
['It', 'One', 'Imperfection', 'It']

>>> response.css("span.text::text").re_first(r"world")
'world'
```

给你一个实用的判断标准。清洗逻辑能用一句正则说清，就放在 `.re()` 里。要是需要多步处理，比如去标签、去空格、类型转换，那属于 Item Loader 的活，后面的文章会讲。

![CSS 与 XPath 的分工](https://static.xiongneng.me/scrapy-02-selector-map.png)

## 把链接串成一张网

单个页面好办，难的是怎么把成百上千个页面串起来。

Scrapy 从简单到复杂给了三档工具。

### 1. follow 和 follow_all

最基础的是 `response.follow()`。它跟 `scrapy.Request` 有两处不一样。它直接吃相对路径，不用你先 `urljoin`。它也吃 `Selector` 对象，能直接接选择器的结果。

```python
# 三种等价写法，任选一种
yield response.follow("/page/2/", callback=self.parse)
yield response.follow(response.css("li.next a"), callback=self.parse)
yield response.follow(response.css("li.next a::attr(href)").get(), callback=self.parse)
```

要一次性跟进一批链接，就用 `response.follow_all()`。它返回生成器，配合 `yield from` 一次吐完。

```python
anchors = response.css("div.quote span a")
yield from response.follow_all(anchors, callback=self.parse_author)
```

### 2. CrawlSpider 和 Rule

页面结构复杂起来，手写 follow 就变得啰嗦。`CrawlSpider` 把这部分抽成了规则表，你声明什么样的链接该怎么处理，它自己去提取和跟进。

```python
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule


class AuthorCrawlSpider(CrawlSpider):
    """规则化爬取：翻页和作者页都交给 Rule。"""

    name = "author_crawl"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/"]

    rules = (
        # 作者主页：交给 parse_author，不再往下跟
        Rule(LinkExtractor(allow=r"/author/"), callback="parse_author"),
        # 分页：没有 callback，follow 默认为 True，会一直翻到没有下一页
        Rule(LinkExtractor(allow=r"/page/")),
    )

    def parse_author(self, response):
        yield {
            "name": response.css("h3.author-title::text").get(default="").strip(),
            "birthdate": response.css(".author-born-date::text").get(default="").strip(),
        }
```

`Rule` 有个特别容易记混的默认值，`follow` 的默认值取决于有没有 `callback`。写了 `callback` 就默认不跟进，没写才默认跟进。这个设计其实挺合理，但它仍然是最容易配错的地方。我当初第一次配的时候就栽在这儿。

`LinkExtractor` 有几个常用参数值得过一遍。`allow` 和 `deny` 用正则筛链接地址，`restrict_xpaths` 把提取范围限定在页面某个区域内，`process_value` 能对链接做二次加工。2.17 还新增了 `deny_tags` 和 `deny_attrs`，可以直接排除某类标签，或者排掉不带指定属性的链接，比写正则直观。

这次我把上面这个爬虫实测跑了一遍。结果是 50 条作者数据，发出 254 个请求，而去重过滤器拦下了 **1062 个重复请求**。

这个数字挺说明问题的。规则化爬取会提取出大量重复链接，同一个作者在多个页面被反复引用。如果没有内置去重，请求量要翻好几倍。

### 3. 三种订阅类 Spider

除了逐页爬取，Scrapy 还内置了三种针对订阅源的 Spider，省掉手工解析的功夫。

1. `XMLFeedSpider`：按节点遍历 XML 订阅源，用 `itertag` 指定节点名，`parse_node()` 处理每个节点
2. `CSVFeedSpider`：一行一行地读，用 `headers` 声明列名，`parse_row()` 处理每一行
3. `SitemapSpider`：直接读站点地图发现 URL，支持嵌套地图，也能从 robots.txt 里找地图地址

这三者的共同点是响应类型已经由框架处理好了，你只需要写拿到一条记录后提取什么。需要注意的是 2.18 起行为有变化，以前没实现 `parse_node()` 或 `parse_row()` 会报一个配置类错误，现在直接抛 `AttributeError`。报错直白多了，但也更容易让人措手不及。

## 实战：把演示站抓个遍

前面都是零件，现在把它们组装成一个能出结果的爬虫。

任务是这个，把演示站 100 条名言对应的 50 位作者全部整理成档案，包括出生日期和出生地，最后统计出这批作家生活在什么年代、都来自哪里。

难点在于数据分布在两类页面上。作者名字和链接在名言列表页，出生日期和出生地在作者详情页。列表页只负责发现链接，真正的数据要从详情页取。

这正是两段式回调的用武之地。

```python
import scrapy


class AuthorsSpider(scrapy.Spider):
    """两段式抓取：列表页取作者链接，作者页补生平档案。"""

    name = "authors"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/"]

    def parse(self, response):
        # 第一段：名言条目里的作者主页链接。
        # dict.fromkeys 保序去重，同一页重复出现的作者只发一次请求
        links = response.css("div.quote span a::attr(href)").getall()
        for link in dict.fromkeys(links):
            yield response.follow(link, callback=self.parse_author)

        # 第二段：翻页，把 10 页都走一遍
        yield from response.follow_all(css="li.next a", callback=self.parse)

    def parse_author(self, response):
        """作者详情页：字段与页面结构一一对应，缺字段用 default 兜底。"""
        yield {
            "name": response.css("h3.author-title::text").get(default="").strip(),
            "birthdate": response.css(".author-born-date::text").get(default="").strip(),
            "birthplace": response.css(".author-born-location::text").get(default="").strip(),
            "bio": response.css(".author-description::text").get(default="").strip(),
        }
```

跑起来。

```bash
scrapy crawl authors -O authors.json
```

运行统计里有几个数字值得看。

```
'item_scraped_count': 50,
'downloader/request_count': 111,
'dupefilter/filtered': 37,
'elapsed_time_seconds': 132.32,
'finish_reason': 'finished',
```

50 条作者档案，111 个请求，10 个列表页加 50 个作者页，再加首次的 robots.txt。37 个重复请求被自动拦下，这是 `dict.fromkeys` 之外的第二层保险，来自框架的指纹去重。耗时 132 秒是因为默认配置把延迟设成了 1 秒，属于对站点的礼貌。嫌慢可以调 `DOWNLOAD_DELAY`，但别调成 0。

有了档案就能做统计。

```python
"""读 authors.json，统计出生年代分布与出生地 Top 榜。"""
import json
from collections import Counter

with open("authors.json", encoding="utf-8") as f:
    data = json.load(f)

years = [int(item["birthdate"][-4:]) for item in data if item["birthdate"]]
decade = Counter(f"{y // 10 * 10}s" for y in years)
places = Counter(item["birthplace"].removeprefix("in ").rsplit(",", 1)[-1].strip()
                 for item in data if item["birthplace"])

print(f"作者档案: {len(data)} 位")
print(f"出生年份跨度: {min(years)} - {max(years)}")
print("\n出生年代分布:")
for d, n in sorted(decade.items()):
    print(f"  {d:<8} {'█' * n} {n}")
print("\n出生地 Top 5:")
for p, n in places.most_common(5):
    print(f"  {p:<16} {n} 位")
```

结果出来了，全是真实数据。

```
作者档案: 50 位
出生年份跨度: 1775 - 1973

出生年代分布:
  1770s    █ 1
  1800s    ██ 2
  1810s    █ 1
  ...
  1920s    ███████ 7
  1940s    █████████ 9
  1960s    ███ 3
  1970s    █ 1

出生地 Top 5:
  The United States 25 位
  The United Kingdom 9 位
  Germany          3 位
  France           2 位
  Ireland          2 位
```

榜单读起来挺有意思。演示站的作家一半来自美国，英国排第二，两个英语国家的作家加起来占了近七成。年龄上则集中在 20 世纪。

回头看这个爬虫，它做的事其实很简单。从列表页发现 50 个链接，每个链接发一个请求，把 50 个响应拼起来。复杂的感觉都来自页面结构，而不是框架。

你花在抓什么上的精力，不会被怎么调度稀释掉。说到底，这就是用框架的收益。

![两段式抓取与统计结果](https://static.xiongneng.me/scrapy-02-two-stage.png)

## 容易栽的跟头

**坑 1：拿 `[0]` 取结果，没匹配到就崩了。** `SelectorList` 是列表，`response.css("h1")[0]` 在页面改版后没有 h1 时会直接抛 `IndexError`，整个爬虫中断。`.get()` 取不到返回 `None`，`.get(default="")` 还能给个兜底值，抓取代码应该尽量用后者。判断逻辑也别写 `if x == None`，直接 `if x` 或者 `if x is None` 更清楚。

**坑 2：嵌套 XPath 用 `//` 开头。** `quotes.xpath('//small[@class="author"]')` 看起来像在每条名言里找作者，实际上 `//` 跳回了文档根，返回的是全页所有作者。正确写法是 `.//small[@class="author"]`。这个错误很隐蔽，因为页面结构简单时两种写法的结果碰巧一样。

**坑 3：`Rule` 里的正则限制得太宽。** 我这次写的 `LinkExtractor(allow=r"/page/")` 看着是想翻页，实际它同时匹配了 `/tag/love/page/1/`，把标签页也一起拖进了爬取范围，请求数从预期的 60 涨到 254。正则匹配的是整段 URL 的子串，写规则时最好加上更具体的锚点，比如 `allow=r"/page/\d+/?$"`。想确认自己写的规则提取了什么，在 `scrapy shell` 里手动构造一个 `LinkExtractor` 跑一遍最直接。

**坑 4：`callback` 名字写错，静默丢数据。** `callback=self.parse_authorr` 拼错一个字母，Scrapy 不会报错，请求照样发、页面照样下载，只是谁也处理不了它。日志里会看到请求数正常，可 `item_scraped_count` 是 0。遇到这种组合，先回去检查回调名。

**坑 5：`response.follow` 忘了 yield。** `response.follow()` 只是构造并返回一个 `Request` 对象，不 `yield` 出去，框架根本不知道有这个任务。写成 `response.follow(link, callback=self.parse)` 而不带 `yield`，爬虫会在第一页就安静结束。

**坑 6：从 `response.meta` 复制内部键。** 想把附加数据带到下一个请求，正确做法是自己起一个键名，比如 `meta={'item': item}`。如果直接把 `response.meta` 整个拷进新请求，就带上了框架自己用的内部键，深度、下载槽位这些。2.18 起新增的 `MetaCopyDetectionMiddleware` 会检测到并发出警告。这个警告不是空穴来风，带上错误的深度会让深度的限制和统计全部失真。

**坑 7：`XMLFeedSpider` 和 `CSVFeedSpider` 的报错换了样子。** 2.18 起，忘了实现 `parse_node()` 或 `parse_row()` 不再报原来的配置类异常，而是直接抛 `AttributeError`。看到这个报错别先去怀疑 XML 格式，回头看一眼方法名是不是写全了。

## 小结

这一篇把爬虫的两个核心环节拆开了。

Spider 那半边，你要记住的是那条回调链。`start()` 给初始请求，回调产出数据和新请求，循环到请求耗尽。

选择器那半边，记住的是先选节点再取数据的两层结构，还有 CSS 打头阵、XPath 补盲区、正则做清洗的分工。

真正把这一篇钉牢的是那个实战。50 位作家的档案不是从单个页面里抠出来的，是 111 个请求连起来的结果。

下次再遇到数据分散在不同层级页面这种需求，两段式回调就是你的默认解法。

说真的，这些东西不用背。写的时候卡在哪儿，回来翻一眼就行。

你看，选择器这东西没什么玄学，试多了手感自然就来了。我自己也还在用这套东西，也还在踩新的坑。这篇里要是有哪里讲得不对，欢迎拍砖。
