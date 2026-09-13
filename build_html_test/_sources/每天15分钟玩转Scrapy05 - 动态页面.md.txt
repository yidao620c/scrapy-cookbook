# 每天15分钟玩转Scrapy05 - 动态页面

## 开场

前面那篇讲的是怎么让服务器相信你是本人。这一篇讲另一件事，服务器给回来的东西不全。

你可能已经撞过这个场面。目标页在浏览器里打开挺正常，用 `scrapy shell` 一看，你要的那个节点一个都没有。请求状态码还是 200，页面也不空，就是内容对不上。

这事儿在今天的站点上很常见。前端框架把渲染搬到浏览器里做，服务端只发一个壳子出来，数据靠 JS 再要一次。你拿到的是那个壳子。

这一篇就处理这种情况。先说判断顺序，能不用浏览器就别用，因为这个选择的代价差着好几倍。然后是把浏览器接进来之后，怎么让它干更多的事，滚动、截图、把你想要的返回值带回来。

里面的数字都是我在自己的机器上跑出来的，同一台机器同一段时间，横向比较才有意义。

## 动态内容：先找数据源

页面上有内容，源代码里没有。这件事有三种不同的成因，对应的解法也完全不同。

1. 页面骨架来自服务端，数据由 JS 另外发请求拿回来再塞进去
2. 页面本来就只有骨架，内容全靠前端渲染
3. 页面检测到你在爬它，故意给你一份空壳

前两种是技术问题，第三种是攻防问题。判断顺序应该是这样。

![内容不在源码里的三种成因与判断顺序](https://static.xiongneng.me/scrapy-05-why-empty-20260913062827.png)

动手之前，你想想看数据是从哪儿来的。页面既然能显示出来，说明数据一定到过这台机器上。先花两分钟看一眼页面怎么运作的，我拿演示站的 `/js` 页面做实测，同一个页面用三条路线各跑一遍。

### 1. 路线一，普通请求

先用最朴素的方式抓。

```python
import scrapy

class QuotesJsStaticSpider(scrapy.Spider):
    """路线一：普通请求。页面里的名言是 JS 拼出来的，静态 HTML 里空空如也。"""

    name = "quotesjsstatic"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/js/"]

    def parse(self, response):
        self.logger.info("路线一 普通请求，div.quote 数量 = %d", len(response.css("div.quote")))
```

```
2026-09-12 23:44:30 [quotesjsstatic] INFO: 路线一 普通请求，div.quote 数量 = 0
```

零条。请求是成功的，状态码 200，页面也不是空的，只是你要的那个节点根本不存在。

### 2. 路线二，把数据源掏出来

现在换个思路。页面既然要把数据渲染出来，那数据一定在某个地方。去源代码里找找。

```python
import json

import scrapy

class QuotesJsDataSpider(scrapy.Spider):
    """路线二：页面里既然有现成数据，就直接把 JSON 抠出来。"""

    name = "quotesjsdata"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/js/"]

    def parse(self, response):
        script = response.xpath('//script[contains(text(), "var data")]/text()').get()
        if not script:
            self.logger.error("路线二 没找到内嵌数据源")
            return
        start = script.find("var data = [") + len("var data = ")
        data, _ = json.JSONDecoder().raw_decode(script[start:])
        self.logger.info("路线二 内嵌数据源，拿到 %d 条", len(data))
        for row in data:
            yield {
                "text": row["text"],
                "author": row["author"]["name"],
                "tags": row["tags"],
            }
```

```
2026-09-12 23:44:35 [quotesjsdata] INFO: 路线二 内嵌数据源，拿到 10 条
```

十条，跟浏览器里看到的数量一样。整个过程中没有启动浏览器，就是一次普通的 HTTP 请求加一段字符串处理。

这个页面里的写法是 `var data = [...]`，很直白。真实站点的形式会更多样，可能是一个 XHR 接口返回 JSON，也可能是 `window.__INITIAL_STATE__` 这种注入变量。**判断标准是同一个，数据一定存在于某个你能用普通请求拿到的地方。**

从 script 里抠 JSON 有几个小坑，我实测对比了三种写法。

```
1. parsel .re() 跨行        -> None
2. 贪婪 .*  + json.loads    -> JSONDecodeError: Extra data: line 132 column 2 (char 4045)
3. 非贪婪 .*?               -> 成功 10 条
```

第一种失败是因为 parsel 的 `.re()` 不带 DOTALL 标志，`.*` 不跨行。JSON 一换行就匹配不上。

第二种失败是因为贪婪匹配吃掉了 JSON 之后的所有脚本内容。

第三种在这个页面上碰巧成功了，因为 JSON 恰好以 `];` 结尾。但这是巧合，JSON 里面出现 `];` 就会被提前切断。

稳妥的写法是让解析器自己找结尾，而不是用正则猜。

```python
start = script.find("var data = [") + len("var data = ")
data, end = json.JSONDecoder().raw_decode(script[start:])
```

`raw_decode` 从给定的位置开始解析一个 JSON 值，返回数据和解结束的位置。实测里它精确定位到了第 4061 个字符，而整段 script 长 4458 字符。

### 3. 三条路线的账

三条路线都跑完，把结果摆在一起看。

| 路线 | 拿到条数 | 耗时 | 要不要浏览器 |
|------|--------|--------|-------------|
| 一 普通请求 | 0 | 4.04 秒 | 不用 |
| 二 内嵌数据 | 10 | 2.32 秒 | 不用 |
| 三 浏览器渲染 | 10 | 4.92 秒 | 要 |

路线二比路线三快一倍还多，而且少了一个浏览器进程。这就是为什么判断顺序里，找数据源要排在渲染前面。

三条路线里，只有路线一和路线二值得优先考虑。渲染是兜底方案，不是首选。

## 交给浏览器渲染

数据源确实找不到的时候，才轮到浏览器出场。

Scrapy 官方没有把浏览器塞进核心，而是通过 `scrapy-playwright` 这个扩展接的。装它分两步，装包和装浏览器。

```bash
pip install scrapy-playwright
playwright install chromium
```

然后改两处配置。

```python
# 把 http/https 交给 playwright 的下载器去处理
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
PLAYWRIGHT_MAX_CONTEXTS = 1
```

下载器换掉之后，普通请求的写法一个字都不用改，还是 `scrapy.Request`。想让某个请求走浏览器，在 meta 里加一个键就行。

```python
import scrapy
from scrapy_playwright.page import PageMethod

class QuotesJsRenderSpider(scrapy.Spider):
    """路线三：交给浏览器把页面渲染好，再按普通选择器抓。"""

    name = "quotesjsrender"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/js/"]

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        # 等名言节点真的出现，别让框架拿到半成品页面
                        PageMethod("wait_for_selector", "div.quote"),
                    ],
                },
            )

    def parse(self, response):
        quotes = response.css("div.quote")
        self.logger.info("路线三 浏览器渲染后，div.quote 数量 = %d", len(quotes))
        for q in quotes:
            yield {
                "text": q.css("span.text::text").get(),
                "author": q.css("small.author::text").get(),
                "tags": q.css("div.tags a.tag::text").getall(),
            }
```

`playwright_page_methods` 里那一行是必须的。页面加载完成不等于渲染完成，浏览器把 HTML 骨架交出来的时候，JS 可能还没跑完。`wait_for_selector` 让它等到名言节点真的出现再交给 `parse`。少了这一行，你拿到的就是一个空的 `Selector`，而且不报错。

跑起来。

```
2026-09-12 23:44:24 [quotesjsrender] INFO: 路线三 浏览器渲染后，div.quote 数量 = 10
{'downloader/request_count': 2,
 'elapsed_time_seconds': 4.9159651000009035,
 'item_scraped_count': 10,
 'playwright/request_count': 7,
 'playwright/request_count/navigation': 1}
```

十条数据，跟路线二一样。

注意 `playwright/request_count` 是 7，而 Scrapy 层的 `downloader/request_count` 只有 2。一个是浏览器内部真实发出的请求数，一个是 Scrapy 看到的请求数。浏览器要额外去取 JS、CSS、图片这些资源，多出来的开销就在这里。

说到底，这是渲染方案的代价。多花的时间、多发的请求，都是为了让 JS 跑一遍。

拿浏览器当证据看一眼，页面渲染出来是这样的。

![浏览器渲染之后拿到的页面](https://static.xiongneng.me/scrapy-05-js-rendered-20260913062827.png)

### 关于 Splash

早几年做渲染主要靠 Splash，一个独立跑着的渲染服务，Scrapy 这边用 `scrapy-splash` 接。它的思路是把浏览器能力做成一个 HTTP 服务，你发请求给它，它返回渲染后的 HTML。

这套方案现在还能用，但我不建议新项目再上了。理由有三个。它需要一个独立的 Docker 服务跟着跑，部署多一层。它的渲染内核版本偏老，现代前端框架在上面容易出问题。它的维护节奏也慢下来了。

`scrapy-playwright` 现在装起来只要两条命令，浏览器直接跑在本机，配置也少。**新项目直接上 Playwright。** 遇到老项目里已经在用 Splash，知道它是什么东西就行。

## 让浏览器多干一点

浏览器接进来之后，很多人就只用来渲染页面，拿到 HTML 就完事。这样亏了。`PageMethod` 能让它在渲染的同时把一些值顺手带回来，这个能力在处理滚动和交互类页面时特别省事。

### 1. PageMethod 的返回值能读回来

先说机制。`PageMethod` 对象建出来之后，你不要扔进列表就不管了，自己留一个引用。scrapy-playwright 在浏览器里跑完这个方法，会把返回值写回这个对象的 `.result`。

```python
import scrapy
from scrapy_playwright.page import PageMethod

class CatalogSpider(scrapy.Spider):
    """把几个常用的 PageMethod 摆在一起，看它们各自返回什么。"""

    name = "catalog"
    allowed_domains = ["quotes.toscrape.com"]

    async def start(self):
        # 这几个 PageMethod 对象建出来之后自己留着引用，
        # 跑完请求就能从 .result 上把返回值读回来
        title = PageMethod("title")
        count = PageMethod("evaluate", "document.querySelectorAll('div.quote').length")
        shot = PageMethod("screenshot", path="out/js_page.png", full_page=True)

        yield scrapy.Request(
            "https://quotes.toscrape.com/js/",
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    # 页面加载完成 != 渲染完成，等节点真的出现再往下走
                    PageMethod("wait_for_selector", "div.quote"),
                    PageMethod("wait_for_load_state", "networkidle"),
                    title,
                    count,
                    shot,
                ],
            },
            callback=self.parse,
            cb_kwargs={"pms": {"title": title, "count": count, "shot": shot}},
        )

    def parse(self, response, pms):
        self.logger.info("page.title() 返回 -> %s", pms["title"].result)
        self.logger.info("page.evaluate() 返回 -> %s", pms["count"].result)
        self.logger.info(
            "page.screenshot() 返回 -> %s 类型，长度 %s",
            type(pms["shot"].result).__name__,
            len(pms["shot"].result or b""),
        )
        self.logger.info("同一个响应，选择器数到 %d 条", len(response.css("div.quote")))
```

跑出来是这样。

```
2026-09-13 06:06:37 [catalog] INFO: page.title() 返回 -> Quotes to Scrape
2026-09-13 06:06:37 [catalog] INFO: page.evaluate() 返回 -> 10
2026-09-13 06:06:37 [catalog] INFO: page.screenshot() 返回 -> bytes 类型，长度 100833
2026-09-13 06:06:37 [catalog] INFO: 同一个响应，选择器数到 10 条
 'elapsed_time_seconds': 2.781685699999798,
 'item_scraped_count': 10,
 'playwright/request_count': 7,
```

三样东西都拿到了，而且它们是三种不同的类型。

| PageMethod | 参数作用 | 返回值类型 | 实测结果 |
|-----------|---------|-----------|---------|
| `title()` | 不用参数 | 字符串 | `Quotes to Scrape` |
| `evaluate(js)` | 一段 JS 表达式 | JS 值的 Python 映射 | 数字 `10` |
| `screenshot()` | `path` 落盘，`full_page` 整页 | 字节串 | 长度 100833 |

`screenshot` 那一项有个细节值得说。传了 `path` 它会同时落盘也返回字节串，实测那个 PNG 文件是 100833 字节，跟返回值的长度一样。这行代码可以让你在 CI 里给失败页面留一张图，比翻日志直观。

⚠️ 拿 `.result` 有个前提，你得在 `parse` 里能访问到那个 PageMethod 对象。上面用 `cb_kwargs` 传进来是一种办法。直接把对象挂在 `self` 上也能用，但多个请求并行跑的时候会互相覆盖，`cb_kwargs` 这种跟着请求走的写法更稳。

### 2. 无限滚动要数到不再增长

演示站有个 `/scroll` 页面，典型的无限滚动。初始给 20 条名言，往下滚一屏，JS 再去要下一批。

这类页面用 `wait_for_selector` 是没用的。第一批名言一开始就存在，选择器立刻能匹配上，它判断不出后面还有没有。必须自己滚。

`PageMethod` 的第一个参数可以是一个协程函数，scrapy-playwright 会把 `page` 当第一个参数传进去。所以滚动逻辑可以直接写成这样。

```python
async def scroll_to_bottom(page, rounds=6, pause_ms=700):
    """一屏一屏往下滚，直到名言条数不再增加为止，返回最终条数。"""
    total = 0
    for i in range(rounds):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(pause_ms)
        n = await page.evaluate("document.querySelectorAll('div.quote').length")
        print("   第 %d 次滚动后，页面上的名言数 = %d" % (i + 1, n))
        if n == total:
            # 这一轮没有新东西进来，说明到底了
            return n
        total = n
    return total
```

这个函数有两条出口。一条是滚到某一轮数量不再增长，主动收工。另一条是把 `rounds` 循环用完，函数正常返回。

我拿两个不同的轮次上限各跑一遍，差别很大。

| 轮次上限 | 每一轮数到的条数 | 最终 |
|---------|----------------|------|
| 6 | 20 / 30 / 40 / 50 / 60 / 70 | **70** |
| 12 | 20 / 30 / 40 / 50 / 60 / 70 / 80 / 90 / 100 / 100 | **100** |

这个页面真实的条目总量是 100。轮次上限设成 6 的那一次，`item_scraped_count` 是 70，跑完了，退出原因正常，日志里一句提醒都没有。

![滚动轮次上限对结果的影响](https://static.xiongneng.me/scrapy-05-scroll-limit-20260913062827.png)

⚠️ **这两条出口的语义完全不同，但外部看不出来。** 第一条是「我确认到底了」，第二条是「我次数用完了」。`scroll_to_bottom` 的返回值在两种情况下都是一个整数，调用方分不出哪个是哪个。所以轮次上限只能当成一道保险，不能当成结束条件，取值要留足。不然你会安安静静地少拿三成数据。

想区分也行，让函数返回一个元组，把「是否确认到底」这个布尔值一起带出来。

### 3. 把图片和字体拦掉

浏览器渲染的代价之一是它会去取页面引用的所有资源。图片、字体、样式表，一样不落。你要的只是渲染后的 DOM，这些资源大部分是白花的。

scrapy-playwright 留了一个钩子，让你在请求发出之前决定放不放行。

```python
"""按资源类型拦截请求，给渲染提速。"""

BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}

def should_abort(request):
    """返回 True 表示这次请求不发了。request 上带 resource_type。"""
    return request.resource_type in BLOCKED_RESOURCE_TYPES
```

挂上去的方式是在蜘蛛的 `custom_settings` 里写那个函数的位置。

```python
class RenderLeanSpider(scrapy.Spider):
    name = "renderlean"
    custom_settings = {
        "PLAYWRIGHT_ABORT_REQUEST": "jsrender.abort.should_abort",
    }
```

我拿一个书城列表页做对照，20 本书，每本一张封面图。两个蜘蛛跑同一个页面，一个全放行，一个掐掉图片和字体，各跑三轮。

| 轮次 | 全放行 | 掐掉图片字体 |
|------|--------|-------------|
| 1 | 2.663 秒 | 2.475 秒 |
| 2 | 2.850 秒 | 2.448 秒 |
| 3 | 2.723 秒 | 2.397 秒 |
| 平均 | 2.745 秒 | 2.440 秒 |

省下来大约 0.3 秒，一成左右。说实话这个幅度不算大，它取决于页面引用了多少图片，图多的站效果更明显，我这只是一个 20 张图的列表页。你看这个页面的资源构成就明白了，20 张封面图加 2 个字体文件，能省的就是这些。

两侧的数据是完全一样的，`item_scraped_count` 都是 20，`downloader/request_count` 都是 1。缩短的只有浏览器内部的取资源时间，跟解析结果无关。

拦住的数量在统计里叫 `playwright/request_count/aborted`，三轮都是 22。这个数字对应 20 张图加 2 个字体。

⚠️ 这里有个容易看错的地方。同一个统计里的 `playwright/request_count/resource_type/image` 在两侧**都是 20**，看起来像没拦住。原因是资源类型的计数发生在请求发出之前，而 `aborted` 是另一套账。想知道自己到底拦掉了多少，看 `aborted` 那个键，别看 `resource_type` 的分解。

拦截本身要克制一点。有些站的图片地址里藏着业务数据，有些字体文件缺失会让 SPA 的字体加载超时卡住渲染。稳妥的做法是先全放行跑一遍拿到基准，再加拦截，对比两侧的 item 数量有没有变化。

## 容易栽的跟头

**坑 1：以为用了浏览器就没有身份问题了。** 这是个错觉，而且是双重的。我在同一个请求上把两个 UA 都读出来对比。

```
2026-09-13 06:09:10 [uaprobe] INFO: 浏览器里 navigator.userAgent -> Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/151.0.7922.34 Safari/537.36
2026-09-13 06:09:10 [uaprobe] INFO: 浏览器里 navigator.webdriver -> True
2026-09-13 06:09:10 [uaprobe] INFO: Scrapy 这一层的默认 UA -> b'Scrapy/2.19.0 (+https://scrapy.org)'
```

第一行那个 UA 里明晃晃写着 `HeadlessChrome`。第二行 `navigator.webdriver` 是 `True`，这是自动化框架留下的标记，有些站会直接读这一个值。第三行更值得注意，Scrapy 那一层的请求头还是自己的默认 UA，跟浏览器里跑的是两份身份。

想让浏览器看起来正常一点，得在 `PLAYWRIGHT_CONTEXTS` 里设 `user_agent`，把 `HeadlessChrome` 换掉，再把 `PLAYWRIGHT_LAUNCH_OPTIONS` 里的 `headless` 关掉换虚拟显示。不过这一层做起来是没有尽头的，具体怎么权衡在反爬那一篇再展开。

**坑 2：`wait_for_selector` 只等第一个匹配节点。** 它等的是「页面上有这么一个元素」，不是「页面上该有的元素都齐了」。列表类页面尤其容易中招，第一批 20 条渲染出来它就放行，后面 80 条还在路上。你拿到的是个半成品。

几个替代思路。等 `wait_for_load_state("networkidle")`，让网络安静下来；或者自己写个循环，等 `document.querySelectorAll(...).length` 不再变化。前者简单，但页面有轮询接口的时候永远等不到 idle；后者更准，代价是每次要固定多等一会儿。

**坑 3：用 `playwright_include_page` 忘了关页面。** 把 `page` 对象拿到自己手里之后，回收这件事就归你了。`parse` 里必须有一句 `await page.close()`，而且要放在 `finally` 里。

```python
async def parse(self, response):
    page = response.meta["playwright_page"]
    try:
        await page.wait_for_selector("div.quote")
        # ... 解析
    finally:
        # 这一行不能漏，漏了页面不会回收，跑久了浏览器就卡住了
        await page.close()
```

漏了不会立刻报错，是慢慢卡住的。页面的并发上限由 `PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` 控制，我的配置里是 4。前 4 个请求拿走页面不还，第 5 个请求就开始排队，整个爬虫看起来像卡死。还要注意 `errback` 那条路径也得关页面，请求失败的时候 `meta` 里那个 `page` 同样在手上。

**坑 4：把 `PLAYWRIGHT_ABORT_REQUEST` 的返回值理解反了。** 那个函数的返回值是「要不要掐掉」的意思，返回 `True` 表示不发这个请求。很容易照着白名单的思路写，在函数里列出想保留的资源类型然后返回 `True`，那就正好反了，把该留的全拦掉。文档和参数名都指向「abort」，但写的时候手会顺。

它的入参是 `request`，上面带 `resource_type`、`url`、`method` 这些字段。稳妥的写法是维护一个黑名单集合，`in` 判断，这样默认行为是放行。想核对拦截有没有按预期生效，看统计里的 `playwright/request_count/aborted`。

**坑 5：`DOWNLOAD_HANDLERS` 只映射了一个协议。** 这个配置要写两条键，`http` 和 `https` 各一条。其实吧，这个坑有点冤，因为很多示例代码只写了 `https` 那一行，看着挺完整。

```python
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
```

只写 `https` 的话，浏览器渲染对 `https` 的页面正常工作，某个 `http` 的接口请求却走了老的下载器，表现是这个请求拿不到渲染后的结果。更难受的是它不报错，你只会发现某几个页面数据对不上。检查办法是看 `playwright/request_count`，如果它比预想的少，先回来核对这两行。

**坑 6：退出时那一屏 asyncio 报错不是你的错。** 用 Python 3.14 跑 scrapy-playwright，爬虫正常跑完、退出码是 0，最后还是会打出这么一段。

```
[asyncio] ERROR: Task was destroyed but it is pending!
task: <Task pending name='Task-3' coro=<_ThreadedLoopAdapter._process_queue() running at ...scrapy_playwright\_loop.py:58> ...>
Exception ignored while closing generator <coroutine object _ThreadedLoopAdapter._process_queue ...>:
RuntimeError: Event loop is closed
```

这是 scrapy-playwright 的 `_ThreadedLoopAdapter` 在解释器关停阶段被回收导致的，跟你的蜘蛛代码无关，也不影响已经爬到的数据。判断方法很简单，看退出码。0 就说明业务跑完了，这段噪音可以忽略。想让它安静下来，把日志级别调到 `WARNING` 以上也压不住，因为它是 asyncio 直接打到 stderr 的。

## 小结

这一篇其实是在讲一个取舍。

判断顺序那部分，核心就一句话，先找数据源，渲染是兜底。三条路线摆在同一个页面上，普通请求拿 0 条，从 script 里抠出内嵌 JSON 拿 10 条且不用浏览器，渲染也是 10 条但要起一个 Chromium。路线二比路线三快一倍多，选择顺序里它排前面不是没道理的。

渲染那部分，`scrapy-playwright` 接进来的成本很低，两条安装命令加两处配置。真正的门槛在于你要意识到浏览器能做的事比「渲染一下」多。`PageMethod` 的返回值可以带回来，滚动逻辑可以写成协程塞进去，资源可以按类型掐掉。

那几个数字里我觉得最值得记的不是快了多少，是那个 70 和 100。轮次上限写 6 拿到 70 条，页面真实总量是 100，中间丢的三成，日志里一个字都没有。这类静默的截断比报错麻烦得多，报错会拦住你，静默不会。

我自己的感受是，动态页面这块的排查成本主要花在判断上，不是花在写代码上。一条 `scrapy shell` 命令加两分钟看一眼页面源码，能省下后面一堆白折腾。真正需要上浏览器的情况，比看起来要少。

这篇里要是有哪里讲得不对，欢迎拍砖。
