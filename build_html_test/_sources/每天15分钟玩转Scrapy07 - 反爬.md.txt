# 每天15分钟玩转Scrapy07 - 反爬

## 开场

这一篇讲对方不想让你爬的时候，会发生什么，以及你能做什么。

先划一条线。前面几篇处理的是技术问题，页面怎么渲染、数据怎么落库，这些都有确定答案。这一篇处理的是对抗问题，对方在做判断，而他的判断标准你看不到。所以这里没有通解，只有一堆可以试的手段，和一条必须守住的底。

我的建议是把预期放低一点。你能做的是让自己的请求看起来正常，不是让它变成伪装。说实话这两件事差别很大，前者是减少误伤，后者是一条走不到头的路。

内容分四块。请求头那一块最容易见效，也最容易做过头。被拦之后的应对那一块，重试和 robots 各有各的规矩。代理那一块我给你看一条完整的链路，从中间件写到服务端收到了什么。最后是这一块我踩过的坑。

所有实验我都自己搭了服务端，因为公网没法做这种对照。搭出来的服务端会按我写的规则拦人，这样「因为什么被拦」这件事才有唯一答案。

## 别用默认 UA 自我介绍

默认的 `USER_AGENT` 长这样。

```
Scrapy/2.19.0 (+https://scrapy.org)
```

这个默认值很坦诚，坦诚到对方一眼就知道来的是爬虫。很多站点就是靠这一行做拦截的，而拦住之后的常见表现是返回一个空页面或者 403，不会给你「因为你自称 Scrapy 所以我拦了」这种提示。其实吧，这一行留着不改，等于每次请求都先自报家门。

![默认 UA 与真实浏览器 UA 的对照](https://static.xiongneng.me/scrapy-07-default-ua-20260913062827.png)

换 UA 的活属于下载器中间件。写起来就是三个方法加一个 `from_crawler`。

```python
class RandomUserAgentMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.ua_pool = crawler.settings.getlist("UA_POOL") or UA_POOL
        self.enabled = crawler.settings.getbool("RANDOM_UA_ENABLED", True)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        if not self.enabled:
            return None
        request.headers["User-Agent"] = (
            request.meta.get("ua") or random.choice(self.ua_pool)
        )
        self.stats.inc_value("ua_pool/rotated")
        return None
```

⚠️ 2.19 起方法签名里**不要再写 `spider` 参数**。以前写 `def process_request(self, request, spider)` 还能跑，但会打一条 `ScrapyDeprecationWarning`，官方明说以后不再传。要拿爬虫实例就在 `__init__` 里存下 `crawler`，用 `self.crawler.spider`。

写完别信自己的代码，信服务端。我起了个本地端点，把收到的 UA 原样回显。

```
0 | Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0
1 | Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0
2 | Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0
3 | Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0
4 | Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0
5 | Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, l
去重后 UA 种类: 2
```

关掉开关再跑同一组请求，六个全一样。

```
0 | Scrapy/2.19.0 (+https://scrapy.org)
1 | Scrapy/2.19.0 (+https://scrapy.org)
2 | Scrapy/2.19.0 (+https://scrapy.org)
```

有个细节值得单独拎出来。我在中间件里还写了一行 `request.headers.setdefault("Accept-Language", ...)`，**它从来没生效过**。`DefaultHeadersMiddleware` 排在 400 号位，早就把 `Accept-Language` 塞进去了，`setdefault` 遇到已有值不覆盖。回显里 `accept_language` 一直是默认的 `en`。想真正改掉默认头，只能直接赋值。

## 请求头不止 User-Agent

换 UA 是第一步，但它不是全部。有些站的判断标准是一整套请求头，缺一个就拦。

我搭了个服务端，两个端点。`/gate` 只看请求头全不全，不全就 403。`/echo` 把收到的请求头原样回显，包括数量和顺序。然后拿两个蜘蛛对照，一个什么都不设，一个把请求头补成浏览器的样子。

先看什么都不设的那个。

```
2026-09-13 05:39:47 [bare] INFO: [bare] /gate 状态码 = 403，正文 = <html><body>403 blocked: User-Agent 自报家门：Scrapy/2.19.0 (+https://scrapy.org)</body></html>
2026-09-13 05:39:47 [bare] INFO: [bare] /echo 收到的请求头共 3 个：User-Agent, Accept-Encoding, Host
2026-09-13 05:39:47 [bare] INFO: [bare] UA = Scrapy/2.19.0 (+https://scrapy.org)
2026-09-13 05:39:47 [bare] INFO: [bare] Accept-Language = ''
```

再看补过的那个。

```
2026-09-13 05:39:49 [headed] INFO: [headed] /gate 状态码 = 200，正文 = <html><body>200 passed gate</body></html>
2026-09-13 05:39:49 [headed] INFO: [headed] /echo 收到的请求头共 6 个：User-Agent, Accept, Accept-Language, Accept-Encoding, Upgrade-Insecure-Requests, Host
2026-09-13 05:39:49 [headed] INFO: [headed] UA = Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36
2026-09-13 05:39:49 [headed] INFO: [headed] Accept-Language = 'zh-CN,zh;q=0.9,en;q=0.8'
```

差别摆在一起看更清楚。

![三个请求头与六个请求头的两种结局](https://static.xiongneng.me/scrapy-07-header-gate-20260913062827.png)

| 项目 | 什么都不设 | 补过请求头 |
|------|-----------|-----------|
| `/gate` 状态码 | 403 | 200 |
| 请求头数量 | 3 | 6 |
| `Accept-Language` | 空字符串 | `zh-CN,zh;q=0.9,en;q=0.8` |
| 请求字节数 | 260 | 734 |

差的那三个是 `Accept`、`Accept-Language`、`Upgrade-Insecure-Requests`。**真实浏览器发请求时这三个是必带的，一个正常的 HTTP 客户端不会只发三个头。** `Accept-Language` 为空尤其扎眼，它等于告诉对方这个客户端不在乎语言。

补全这件事写成中间件最省事。

```python
class BrowserHeadersMiddleware:
    """把请求头补成浏览器的样子。只补「缺的」，不覆盖调用方显式设过的值。"""

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.headers = crawler.settings.getdict("BROWSER_HEADERS")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        added = 0
        for name, value in self.headers.items():
            # 这里必须判断存在性再赋值。写成 headers.setdefault(name, value) 之后
            # 以为改了值是不对的：更早的中间件（DefaultHeadersMiddleware 在 400 号位）
            # 可能已经填过，setdefault 遇到已有值不会覆盖。
            if name not in request.headers:
                request.headers[name] = value
                added += 1
        if added:
            self.stats.inc_value("headers/filled")
            self.stats.inc_value("headers/filled_total", added)
        return None
```

池子写在 settings 里，好处是改起来不用碰代码。

```python
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
}

DEFAULT_REQUEST_HEADERS = dict(BROWSER_HEADERS)
```

`DEFAULT_REQUEST_HEADERS` 那一行让全局默认头也变成浏览器样式，中间件就成了兜底。两层一起上，可以覆盖到那些绕过默认头的情况。

⚠️ 补请求头有个度。`Accept-Encoding` 里写 `br` 之后，服务端可能真的返回 Brotli 压缩的内容，而你的环境不一定装了对应的解压库。稳妥的写法是只声明 `gzip, deflate`，或者确认自己那套依赖齐全。

还有一个反过来的坑。有些站会检查请求头的一致性，比如 UA 说是 Chrome 126，却没有 `Sec-Fetch-*` 那一组头，或者 `Accept-Language` 只有一个值。这种不一致比少几个头更容易被认出来。**伪装的目标是自洽，不是凑数量。**

## 被拦之后：重试与守规矩

请求头补好了，还是有被拦的时候。这一节讲两种拦法下的应对。

一种是软拦，服务端不拒绝你，但它不高兴。表现是 429 或者 503，意思是「你太频繁了，缓缓再来」。这类情况该重试，但重试有预算，花完了就得认。

另一种是硬的规矩，robots.txt。它不拦你，它是跟你商量。遵不遵守由你决定，但这件事你应该知道自己在做什么选择。

下面三个小节，前两个是框架自带的能力，第三个是 429 这个码的特殊之处。

### 1. 出错要重试

网络请求失败是常态，不是异常。所以重试不该由你在 `errback` 里手写，框架本来就带着。

默认 `RETRY_TIMES = 2`，也就是一次失败再补两次，总共敲三次门。默认重试的响应码是这一串。

```
[500, 502, 503, 504, 522, 524, 408, 429]
```

⚠️ 这个默认值跟老版本不一样。`429`（请求过多）是后加的，而它恰好是最该重试的一个码。你要是照着老教程抄了一份自己的 `RETRY_HTTP_CODES` 列表，就把 429 漏掉了。

我起了个本地服务，让它在同一个 URL 上前两次返回 503、第三次返回 200。默认配置跑下来。

```
最终状态 200，正文 <html><body>ok after 3 attempts</body></html>
'retry/count': 2,
'retry/reason_count/503 Service Unavailable': 2,
```

`retry/count` 是 2，加上最初那一次正好三次，与服务端记的「第三次才成功」对上了。

把 `RETRY_TIMES` 压到 1，放到一个前五次都失败的 URL 上，就能看到放弃长什么样。

```
ERROR: Gave up retrying <GET http://127.0.0.1:8412/flaky?fail=5&tag=B> (failed 2 times): 503 Service Unavailable
最终状态 503，正文 <html><body>503 attempt 2</body></html>
'retry/count': 1,
'retry/max_reached': 1,
```

「放弃」这条日志的级别由 `RETRY_GIVE_UP_LOG_LEVEL` 控制，默认就是 `ERROR`，所以它一定会出现在你眼前。`retry/max_reached` 是统计里专门数放弃次数的键，跑完扫一眼这个值，比翻日志快。

写蜘蛛的时候有件事别忘。`503` 不在「允许的状态码」里，响应会被 `HttpErrorMiddleware` 过滤掉，`parse` 根本收不到。想让回调看到重试耗尽之后那个页面，得显式放开。

```python
"HTTPERROR_ALLOWED_CODES": [500, 502, 503, 504],
```

### 2. 守着 robots 的规矩

`ROBOTSTXT_OBEY` 默认是关的，但 `scrapy startproject` 生成的项目模板里已经帮你打开了。这个改动挺好的，新项目默认守规矩。

它做的事不只是「读一下 robots.txt」。只要这个开关是开的，每个新域名都会先请求一次 `/robots.txt`，解析出规则，之后每条请求都过一遍判定。

判定结果不需要猜。2.18 加了 `robots_parsed` 信号，解析完就通知你，回调里能拿到解析器，直接问它。

```python
    def on_robots_parsed(self, robotparser, request):
        ua = self.crawler.settings["USER_AGENT"]
        for path in ("/ok", "/private/secret", "/private/public-ok"):
            verdict = robotparser.allowed(HOST + path, ua)
            self.logger.info(
                "robots 判定 %-20s → %s", path, "允许" if verdict else "禁止"
            )
```

⚠️ 参数名必须是 `robotparser` 和 `request`，这是信号签名。写错会在回调里抛 `TypeError`，而 signals 的兜底会把它吃掉，只在日志里留一行 ERROR，很容易漏看。

规则、开关两种状态各跑一次，对照很直观。

```
robots 判定 /ok                  → 允许
robots 判定 /private/secret      → 禁止
robots 判定 /private/public-ok   → 允许
robots 声明的 Crawl-delay：0.0
'robotstxt/forbidden': 1,
```

三条路径的结果值得琢磨一下。`Allow` 能把 `Disallow` 覆盖回来，`/private/public-ok` 就是这么被放行的。抓到的 item 只有两条，被拦的那条没有进管道。

把开关关掉，三条全过，包括那条本该被拦的。

```
拿到 http://127.0.0.1:8412/ok → 200
拿到 http://127.0.0.1:8412/private/secret → 200
拿到 http://127.0.0.1:8412/private/public-ok → 200
```

顺带说个反直觉的点。公网那两个演示站都没有 robots.txt，请求返回 404。**404 的语义是「全部放行」，不是「拒绝访问」**，所以拿它们练手看不出这个开关的任何效果。想看真实行为，得找一个真有 robots.txt 的站点，或者像我这样自己搭一个。

### 3. 429 有它自己的节奏

前面那个 503 的例子是「偶发失败」，重试就行。429 不是这个性质，它的含义是「你太快了」，重试得太勤快反而更糟。

我搭的限流端点带一个窗口参数，前 n 次返回 429 并附上 `Retry-After`。先把重试整个关掉，看原始行为。

```
2026-09-13 05:39:57 [ratenoretry] INFO: [no-retry] 状态码 429，Retry-After = b'1'，正文 = <html><body>429 too many requests (第 1 次)</body></html>
2026-09-13 05:39:57 [ratenoretry] INFO: [no-retry] 状态码 429，Retry-After = b'1'，正文 = <html><body>429 too many requests (第 2 次)</body></html>
2026-09-13 05:39:57 [ratenoretry] INFO: [no-retry] 状态码 429，Retry-After = b'1'，正文 = <html><body>429 too many requests (第 3 次)</body></html>
2026-09-13 05:39:57 [ratenoretry] INFO: [no-retry] 状态码 200，Retry-After = None，正文 = <html><body>200 ok (第 4 次)</body></html>
```

四次请求分别拿到 429、429、429、200。`Retry-After` 那个头是服务端给的提示，意思是「等 1 秒再来」。**这个头 Scrapy 不会自动遵守**，它只是把响应交给你。你的蜘蛛连续发了四次，中间没有任何间隔，靠的是窗口刚好走到第四位。

把重试打开，看框架怎么处理这个码。

```
2026-09-13 05:39:59 [scrapy.downloadermiddlewares.retry] ERROR: Gave up retrying <GET http://127.0.0.1:8416/ratelimit?n=3&who=wr> (failed 3 times): 429 Unknown Status
2026-09-13 05:39:59 [ratewithretry] INFO: [with-retry] 最终状态码 429，正文 = <html><body>429 too many requests (第 3 次)</body></html>
2026-09-13 05:39:59 [ratewithretry] INFO: [with-retry] retry/count = 2，retry/max_reached = 1，retry/reason_count/429 = None
 'retry/count': 2,
 'retry/max_reached': 1,
 'retry/reason_count/429 Unknown Status': 2,
```

`RETRY_TIMES` 是 2，加上最初那一次正好三次。窗口是 3，三次全用完了，最后还是 429。**这就是重试预算和限流窗口错位的典型结果**，预算花光，数据没拿到。

把窗口改成 1 再跑同一个蜘蛛，配置一个字没动。

```
2026-09-13 05:40:40 [rateretryok] INFO: [retry-ok] 最终状态码 200，正文 = <html><body>200 ok (第 2 次)</body></html>
2026-09-13 05:40:40 [rateretryok] INFO: [retry-ok] retry/count = 1，retry/max_reached = None
 'retry/count': 1,
 'retry/reason_count/429 Unknown Status': 1,
```

第二次就成功了，`retry/max_reached` 是 `None`，没有放弃。

⚠️ 这两组对照的结论是，**重试能不能救你，取决于你的重试节奏跟对方的窗口对不对得上，跟配置写得多激进没关系。** 默认的重试是立刻重发，没有退避。面对 429 这种做法等于把预算一次性烧掉。这事儿我一开始也没转过弯，总觉得次数开大点总归没坏处。

想让重试真的有用，得给它加退避。最简单的改法是在 `process_response` 里读 `Retry-After`，让这个请求延迟后再回队列。Scrapy 的重试中间件留了 `RETRY_PRIORITY_ADJUST` 这类旋钮，但**按响应头做退避要自己写**，这也是为什么很多团队干脆在下载器中间件里加一层自己的限速器。

还有一个统计上的坑顺便说掉。`retry/reason_count/429` 读出来是 `None`，真实的键名是 `'429 Unknown Status'`。原因是 429 这个码不在 Twisted 的状态短语表里，Scrapy 拼键名的时候把整个字符串用上了。**想统计重试原因就别按精确键名取**，遍历所有 `retry/reason_count` 开头的键更稳。

对比一下 403 就很清楚。403 是「你就是不受欢迎」，重试没有意义，框架默认也不重试它。

```
2026-09-13 05:40:02 [forbidden] INFO: [forbidden] 状态码 403，正文 = <html><body>403 you are not welcome</body></html>
2026-09-13 05:40:02 [forbidden] INFO: [forbidden] retry/count = None，重试原因计数 = {}
```

`retry/count` 是 `None`，重试原因计数是空字典。一次都没试。这是对的行为，把重试预算浪费在一个明确的拒绝上，除了加重对方的判断没有别的作用。

## 走代理换出口

请求头补得再像，有一个东西你改不了，出口 IP。同一个 IP 一天来几十万次请求，这件事光靠 UA 掩饰不掉。代理解决的正是这个。

Scrapy 内置了一个 `HttpProxyMiddleware`，号位是 750。它不看你的配置，只看 `request.meta["proxy"]`。所以做代理轮换不用重写下载逻辑，只要在更早的位置往那个键里写一个地址。

```python
class RotateProxyMiddleware:
    """每个请求从池子里挑一个代理，写进 request.meta["proxy"]。

    真正把代理用起来的是内置的 HttpProxyMiddleware（默认 750 号位），
    它读的正是 request.meta["proxy"]。所以本中间件的号位必须比 750 小。
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.pool = crawler.settings.getlist("PROXY_POOL")
        self.enabled = crawler.settings.getbool("ROTATE_PROXY_ENABLED", False)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request):
        if not self.enabled or not self.pool:
            return None
        # 已经指定过代理的请求不要覆盖（比如某个请求必须走固定出口 IP）
        if request.meta.get("proxy"):
            return None
        request.meta["proxy"] = random.choice(self.pool)
        self.stats.inc_value("proxy/assigned")
        return None

    def process_exception(self, request, exception):
        """代理挂了就把这个请求记一笔，真实项目里应该把它从池子里剔除。"""
        if request.meta.get("proxy"):
            self.stats.inc_value("proxy/failed")
        return None
```

挂上去的时候号位要挑对，比 750 小就行，我选的是 610。

```python
DOWNLOADER_MIDDLEWARES = {
    "antiban.middlewares.BrowserHeadersMiddleware": 543,
    "antiban.middlewares.RotateProxyMiddleware": 610,
}
```

⚠️ 那个号位不是随便挑的。写在 750 之后你的赋值永远不会生效，因为内置中间件已经先跑过了。这类静默失效很难查，表现是「配置看起来完全正确，但请求还是从本机出去的」。

代理池里的地址可以带凭据，写成 `http://user:pass@host:port`。内置中间件会替你拆开拼成 `Proxy-Authorization` 头，不用自己算 base64。

验证这件事不能只看自己的日志。我写了一个最小的正向代理，它在转发的时候往请求里塞一个 `X-Forwarded-For`，在响应里盖一个 `X-Proxied-By` 的章，然后再起一个蜘蛛去请求回显端点。两个蜘蛛跑同一个 URL，一个开着轮换，一个关着。

开着轮换的那次。

```
2026-09-13 05:40:04 [proxy] INFO: [proxy] 服务端看到的 X-Forwarded-For = '203.0.113.8'
2026-09-13 05:40:04 [proxy] INFO: [proxy] 响应头里代理的印章 X-Proxied-By = b'labserver8-proxy'
2026-09-13 05:40:04 [proxy] INFO: [proxy] proxy/assigned = 1，proxy/failed = None
```

关掉的那次。

```
2026-09-13 05:40:06 [direct] INFO: [direct] 服务端看到的 X-Forwarded-For = ''
2026-09-13 05:40:06 [direct] INFO: [direct] 响应头里 X-Proxied-By = None
```

| 项目 | 走代理 | 直连 |
|------|--------|------|
| 服务端看到的 `X-Forwarded-For` | `203.0.113.8` | 空字符串 |
| 响应里的 `X-Proxied-By` | `labserver8-proxy` | 不存在 |
| `proxy/assigned` | 1 | 不存在 |

这两行证据是分开的两条链路。`X-Forwarded-For` 证明服务端看到的是代理的地址；`X-Proxied-By` 证明那次响应确实是从代理那边回来的，不是本机直接拿到的缓存。**两个方向都对上了，链路才算通。** 只看自己这一侧的日志，很可能是「写了 meta 但没走代理」，这种情况日志里什么异常都没有。你想想看，如果只在本地看 `proxy/assigned` 这个计数，它写对了也只能说明那一行代码执行过，说明不了请求真的绕了路。

![代理出口的双向验证](https://static.xiongneng.me/scrapy-07-proxy-check-20260913062827.png)

真实项目里代理有几个层次。数据中心代理便宜、快，但 IP 段是公开的，容易被整段封。住宅代理贵，IP 看起来像普通用户，但速度不稳、有并发限制。我自己的感受是，选择取决于对方查得有多细，以及你的时间预算，没有通用的答案。

⚠️ 代理池不是越大越好。一个池子里混进几个慢的，整体速度会被这几个拖住，而且表现是间歇性的偶发超时，比全挂还难查。**上线之前先给池子里的每个地址做一轮体检**，把响应时间和成功率记下来，把明显不合格的剔掉再进生产。

最后说一句立场问题。代理能让你绕过 IP 层面的限制，但它不改变一件事，对方在 robots.txt 或者服务条款里表达过的意愿。技术上能做和该不该做，是两件事。

## 容易栽的跟头

**坑 1：只改 `USER_AGENT`，剩下的头一个不管。** 这是最常见的一种「我以为我伪装了」。实测里最少的一套请求头只有三个，`User-Agent`、`Accept-Encoding`、`Host`，`Accept-Language` 甚至是空字符串。真实浏览器不会只发三个头。想快速自查，把自己请求的头打成一行，跟浏览器开发者工具里的请求头对一下，差多少一眼就看出来了。

**坑 2：中间件里写 `request.headers.setdefault()` 以为改了默认头。** 这个我之前专门验证过，它从来没生效过。`DefaultHeadersMiddleware` 排在 400 号位，比你的中间件早，等你的代码跑到的时候那些键已经有值了，`setdefault` 遇到已有值不覆盖。要真正改掉默认头只有两条路，要么直接赋值，要么改 `DEFAULT_REQUEST_HEADERS` 把默认值换成你想要的。**这个坑的特征是「代码看着完全合理，日志里也看不出问题，只有对端的回显能证明它没生效」。**

**坑 3：代理中间件的号位写在 750 之后。** 内置的 `HttpProxyMiddleware` 在 750，它读 `request.meta["proxy"]`。你的号位比它大，就等于在它跑完之后才改这个值，这一轮的请求已经发出去了。表现和坑 2 一样，配置全对，行为完全不符合预期。

**坑 4：把 429 当成普通的失败码来重试。** Scrapy 的默认重试是立刻重发，中间没有退避。面对 429 这种做法等于把重试预算一口气烧光。实测里 `RETRY_TIMES=2` 配一个窗口为 3 的限流端点，三次请求全部撞在窗口里，以 `retry/max_reached=1` 收场。同一份配置换到窗口为 1 的端点上就成功了。**重试能不能救你，看的是节奏对不对，不是次数够不够。**

**坑 5：按 `retry/reason_count/429` 去取统计。** 取出来是 `None`，真实的键名是 `'429 Unknown Status'`。429 这个码不在 Twisted 的状态短语表里，Scrapy 拼键名的时候把码和占位短语一起用上了。稳妥的写法是遍历所有以 `retry/reason_count` 开头的键，别按精确名字取。

**坑 6：以为 `ROBOTSTXT_OBEY` 打开就万事大吉。** 它做的不只是读一下那个文件。开关一开，每个新域名都会先请求一次 `/robots.txt`，多一次往返。更值得留意的是 404 的语义，**robots.txt 返回 404 表示「没有规则」，也就是全部放行**，不是拒绝。想验证这个开关到底有没有在工作，得找一个真有 robots.txt 的站点，公网那两个演示站都没有。说到底这个开关管的是「要不要看那份文件」，不是「看完之后怎么抓」，两件事别混在一起。

**坑 7：把 robots.txt 里的 `Crawl-delay` 当成会被自动遵守。** Scrapy 会把它解析出来，但要不要按它降速是你自己的事。实测里那个值为 0.0，日志里能看到解析结果，可蜘蛛该跑多快还是跑多快。想真的按它来，得在 `robotparser` 拿到的值上自己接一段逻辑。

**坑 8：代理池里混进慢节点。** 这件事的麻烦在于它的表现是间歇性的。十个地址里有一个响应要 30 秒，整体平均耗时会被它拖上去，而且是随机出现，看日志像偶发故障。上线前给池子做一轮体检，把响应时间和成功率记下来再筛一遍，比事后查快得多。

## 小结

反爬这一块的难点不在技术，在判断。

请求头那一块是可以确定的。三个头对六个头，403 对 200，这个差距是硬的，补上就有效。但补到什么程度为止，这条线由对方画。补得过头，比如 UA 说是 Chrome 126 而 `Sec-Fetch-*` 那一组一个都没有，反而更像假的。

重试那一块让我改了原来的想法。以前我以为重试次数开大一点总没坏处，实测之后发现不是。面对 429，立刻重发等于把预算一口气烧光，`RETRY_TIMES=2` 配窗口 3 的结果是一次都没成功。**同一份配置换个窗口就够用了，区别只在节奏。** 所以重试这件事要跟限速一起设计，单独调一个没有意义。

代理那一块，我最想让你记住的是那个双向验证。只看自己这边写了 `meta["proxy"]` 是没有意义的，得让服务端告诉你它看到的地址，再让响应头告诉你这一趟确实绕了路。两个方向都对上，才算链路是通的。

最后是立场。robots.txt 是对方写给爬虫看的，它表达的是一个意愿。技术上有能力绕过去，不代表就应该绕。我在这一篇里把 `ROBOTSTXT_OBEY` 的行为讲清楚了，包括 404 的语义和 `Crawl-delay` 其实不会被自动遵守，但那个开关该不该打开，是你自己要回答的问题。

我自己的做法是，公开数据、频率可控、对方没有明确反对的，正常抓；对方写了 Disallow 的目录，不碰。这条线不一定适合所有人，但它至少是条线。

这篇里要是有哪里讲得不对，欢迎拍砖。
