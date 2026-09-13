# 每天15分钟玩转Scrapy04 - 登录与Cookie

## 开场

前面三篇把数据怎么取、怎么存讲完了。但抓的都是那种打开就能看的页面。

真实一点的站点很快会给你上第一道门槛，登录。

想看的内容挂在账号后面，不登录只能看到一个空壳。你直接在地址栏里输那个会员页的地址，服务端给你的是一张登录表单，而不是数据。

这道门槛的解法不止一种。登录页要交表单，浏览器弹框那种要交请求头凭据，还有些站点干脆让你自己带着凭据去敲。

它们的底层是同一件事。你发出去的请求，得跟浏览器发出去的那个长得足够像。

说实话，这一块的坑比前面几篇都多，而且大部分坑不报错。

这一篇拆三块。Cookie 会话到底怎么运作、模拟登录的三步怎么走、HTTP 认证的两个入口怎么选。

演示站还是那个专门给爬虫练手的 quotes.toscrape.com，它自带一个登录页，正好够用。

我当初学这块的时候，最烦的就是文档里写了、照着跑却不对。所以这一篇的每一段输出都是真跑出来的，不是从文档里抄的。

## Cookie 是怎么把会话记住的

HTTP 本身是无状态的。你发两个请求，服务端不知道这俩是同一个人发的。

补丁就是 Cookie。服务端在响应头里塞一个 Set-Cookie，浏览器记下来，下次请求自动带上去。服务端一看这个 Cookie，就知道「哦，还是刚才那位」。

Scrapy 把这件事做成了 `CookiesMiddleware`，默认开着。它做的事跟浏览器一样，收 Set-Cookie、存起来、下一个请求带上。你在绝大多数情况下不需要手动管。

需要手动管的是**分桶**。

默认所有请求共用一个 jar，也就是一个会话。这没问题，直到你要同时用两个身份。比如一边用登录好的账号抓会员页，一边用匿名状态看公开页。共用一个 jar 的话，两个身份会互相污染。

`meta={"cookiejar": "名字"}` 就是干这个的。名字相同的用一个桶，名字不同的各用各的。

我实测了一遍，用一个蜘蛛同时跑两条线。

![Cookie 分桶：一个蜘蛛两个身份](https://static.xiongneng.me/scrapy-04-cookiejar-20260913062827.png)

```python
import scrapy
from scrapy import FormRequest

class QuotesJarSpider(scrapy.Spider):
    """两个身份同时在线：桶 A 登录，桶 B 匿名，互不串味儿。"""

    name = "quotesjar"
    allowed_domains = ["quotes.toscrape.com"]

    async def start(self):
        # 桶 A 的一条线：先 GET 登录页，再把令牌提交回去
        yield scrapy.Request(
            "https://quotes.toscrape.com/login",
            meta={"cookiejar": "jar_a"},
            callback=self.submit_login,
        )
        # 桶 B 的一条线：同一个站点，但换一个桶，不带登录态
        yield scrapy.Request(
            "https://quotes.toscrape.com/page/2/",
            meta={"cookiejar": "jar_b"},
            callback=self.check_jar_b,
        )

    def submit_login(self, response):
        token = response.css('input[name="csrf_token"]::attr(value)').get()
        yield FormRequest(
            url="https://quotes.toscrape.com/login",
            formdata={"csrf_token": token, "username": "feiwuxiong", "password": "x"},
            meta={"cookiejar": "jar_a"},
            callback=self.check_jar_a,
        )

    def check_jar_a(self, response):
        self.logger.info("桶 A 登录态 = %s", "Logout" in response.text)

    def check_jar_b(self, response):
        self.logger.info("桶 B 登录态 = %s", "Logout" in response.text)
```

跑出来的结果很干净。

```
2026-09-12 23:41:11 [quotesjar] INFO: 桶 B 登录态 = False
2026-09-12 23:41:13 [quotesjar] INFO: 桶 A 登录态 = True
```

你看，同一个站点，同一个时刻。一个桶登录成功了，另一个桶还是游客身份。这就是分桶的意义。

有个顺序问题必须记住。**桶要从这条线的第一个请求就挂上。**

我第一版写的时候偷了个懒，GET 登录页那个请求没写 `meta`，想着反正令牌是页面里的字符串，跟会话没关系。结果提交的时候带着令牌、却挂在新的桶里，服务端一看这个令牌不是你这个会话发的，登录直接失败。查了半天才反应过来。

有个细节值得单独说一句。Cookie 的值类型在 2.18 起放宽了，`Request.cookies` 不再要求值必须是字符串。

```python
req = scrapy.Request("https://example.com/", cookies={
    "text": "abc", "flag": True, "score": 1.5, "count": 3,
})
```

实测这三种非字符串值都能正常发出去。

```
Request 上存的 cookies -> {'text': 'abc', 'flag': True, 'score': 1.5, 'count': 3}
值类型 -> {'text': 'str', 'flag': 'bool', 'score': 'float', 'count': 'int'}
实际发出的 Cookie 头 -> text=abc; flag=True; score=1.5; count=3
```

最后说这事儿最反直觉的一点。**想读响应里的 Cookie，`response.cookies` 这个属性在 2.19 上是没有的。**

```
AttributeError: 'HtmlResponse' object has no attribute 'cookies'
```

老教程里常见这个写法，照抄过来就是一行报错。要拿服务端发下来的 Cookie，走 `response.headers.getlist("Set-Cookie")` 自己解析。

## 模拟登录：三步走

登录的本质是把服务端给你的一次性凭据，换成一个能重复用的会话。整个过程拆开就三步。

1. 打开登录页，把隐藏的令牌抠出来
2. 带着令牌和账号密码，提交表单
3. 拿到会话，后面的请求自动带着它

### 1. 先看登录页长什么样

动手之前先摸清表单结构。这一步千万别省，抄错一个字段名能查一下午。演示站的登录页在 `https://quotes.toscrape.com/login`，表单部分是这样的。

![登录表单的三个字段与隐藏令牌](https://static.xiongneng.me/scrapy-04-login-form-20260913062827.png)

```python
<form action="/login" method="post" accept-charset="utf-8" >
    <input type="hidden" name="csrf_token" value="bkfswnpSqLiNVDgZhlaWmtCuIxQOAFReHKvGcjXdTrMYyJUzEoBP"/>
    <label for="username">Username</label>
    <input type="text" class="form-control" id="username" name="username" />
```

三个字段。`csrf_token` 是隐藏的，值是服务端每次生成的随机串。另外两个是账号密码。

这个隐藏令牌是登录爬虫最关键的一环。它存在的意义是防止别人拿一个脚本对着登录接口猛刷。你把用户名密码直接 POST 过去，服务端只会当你没交令牌，直接拒绝。

### 2. 用 FormRequest 提交

取出令牌，跟账号密码一起交回去。

```python
import scrapy
from scrapy import FormRequest

class QuotesLoginSpider(scrapy.Spider):
    """登录后带会话翻页，每页都确认登录态还在。"""

    name = "quoteslogin"
    allowed_domains = ["quotes.toscrape.com"]
    start_urls = ["https://quotes.toscrape.com/login"]

    def parse(self, response):
        # 第一步：从登录页里把隐藏令牌抠出来
        token = response.css('input[name="csrf_token"]::attr(value)').get()
        self.logger.info("第一步 拿到 csrf_token=%s", token)

        # 第二步：连着令牌一起提交，回调就是登录后的落点
        yield FormRequest(
            url="https://quotes.toscrape.com/login",
            formdata={
                "csrf_token": token,
                "username": "feiwuxiong",
                "password": "whatever",
            },
            callback=self.after_login,
        )

    def after_login(self, response):
        # 第三步：用文本特征判断，不要看状态码
        if "Logout" not in response.text:
            self.logger.error("登录失败，还停在登录页：%s", response.url)
            return
        self.logger.info("第三步 登录成功，落点 %s", response.url)
        yield from response.follow_all(css="li.next a", callback=self.parse_page)

    def parse_page(self, response):
        """翻页页面上再确认一次登录态，证明 Cookie 一直跟着。"""
        self.logger.info("翻到 %s，仍然登录中=%s", response.url, "Logout" in response.text)
        for q in response.css("div.quote"):
            yield {
                "text": q.css("span.text::text").get(),
                "author": q.css("small.author::text").get(),
            }
```

`FormRequest` 的 `formdata` 会给每个值做 URL 编码，然后自动带上 `Content-Type: application/x-www-form-urlencoded`。你不用自己拼字符串。

顺手说一个版本变化。`FormRequest.from_response()` 这个方法在 2.17 起已经弃用了。它会去猜表单的 action、method 和所有隐藏字段，页面稍微复杂一点就猜错，而且错得很难查。**用显式的 `FormRequest` 加 `response.css` 自己取字段**，多写两行，换来的是可控。

### 3. 登录成功的判断标准

跑起来看结果。

```
2026-09-12 23:35:59 [quoteslogin] INFO: 第一步 拿到 csrf_token=mibxVYyCslWUJSGQBEdjZLMwATkXIHeagnptqhozfrcPNROuDvFK
2026-09-12 23:36:01 [quoteslogin] INFO: 第三步 登录成功，落点 https://quotes.toscrape.com/
2026-09-12 23:36:01 [quoteslogin] INFO: 首页拿到 10 条名言
2026-09-12 23:36:12 [quoteslogin] INFO: 翻到 https://quotes.toscrape.com/page/2/，仍然登录中=True
```

最后那行是本篇的重点。翻到第二页，会话还在。说明 Cookie 已经被自动带上了，后面的请求不用你操心。

![登录成功后会话被自动带上](https://static.xiongneng.me/scrapy-04-session-reuse-20260913062827.png)

统计里有几个数字值得看。

```
{'downloader/request_count': 5,
 'downloader/request_method_count/POST': 1,
 'downloader/response_status_count/200': 3,
 'downloader/response_status_count/302': 1,
 'elapsed_time_seconds': 34.78,
 'item_scraped_count': 12,
 'request_depth_max': 2}
```

5 个请求。登录页一个 GET，登录一个 POST，第三页的名言数据分布在这之后的请求里。那个 302 是登录成功后服务端给的跳转，我这次实测里它返回的是重定向而不是直接给首页。

这就是为什么**判断登录成功不能看状态码**。你可能收到 200 也可能收到 302，甚至可能收到 302 之后再跳回登录页。真正可靠的判断是找登录后才出现的文本特征，我用的就是右上角那个 Logout 链接。换一个站点，特征换成用户名、头像、或者「退出」两个字都行，只要它登录前不存在。

### 4. 顺手把请求导出成 curl

调试登录这类问题时，最想干的事是把请求原样搬到命令行里试。2.18 起 `Request` 自带这个能力。

```python
req = FormRequest(
    url="https://quotes.toscrape.com/login",
    formdata={"csrf_token": token, "username": "feiwuxiong", "password": "x"},
    headers={"Referer": "https://quotes.toscrape.com/login"},
    cookies={"probe": "1"},
)
print(req.to_curl())
```

实测输出是一条可以直接粘进终端的命令。

```bash
curl -X POST https://quotes.toscrape.com/login --data-raw 'csrf_token=uJpsNjYSVORkDhMzdcCPZIqALmioaKxEgebUWFQrnlywXvBfTGtH&username=feiwuxiong&password=x' -H 'Referer: https://quotes.toscrape.com/login' -H 'Content-Type: application/x-www-form-urlencoded' --cookie 'probe=1'
```

方法、URL、表单数据、请求头、Cookie 全都还原了。抓虫的时候把它打出来跑一遍，能省掉很多猜。

## HTTP 认证：两个入口

有一类站点不用登录页，而是浏览器弹一个框让你输账号密码。那是 HTTP Basic 认证，凭据直接放在请求头里。

2.17 起 Scrapy 给了两个入口。一个是 settings，全局生效。

```python
HTTPAUTH_USER = "user"
HTTPAUTH_PASS = "passwd"
HTTPAUTH_DOMAIN = "example.com"
```

另一个是每个请求自己带，写在 meta 里。

```python
yield scrapy.Request(url, meta={"http_user": "user", "http_pass": "passwd"})
```

我用 httpbingo.org 的 basic-auth 端点实测了 meta 这个入口，三个请求打同一个地址。

```
meta 正确凭据 -> 状态码 200 | { "authenticated": true,  "user": "user", "authorized": true }
meta 错误凭据 -> 状态码 401 | { "authenticated": false, "user": "user", "authorized": false }
不带任何凭据 -> 状态码 401 | { "authenticated": false, "user": "",     "authorized": false }
```

正确凭据 200，错误凭据和不带凭据都是 401。

有两个细节我实测撞到了，都值得说。

**第一，`HTTPAUTH_DOMAIN` 是必填的。** 只配 USER 和 PASS，爬虫直接起不来。

```
ValueError: HTTPAUTH_DOMAIN must be set when HTTPAUTH_USER or HTTPAUTH_PASS is configured. 
Set it to a domain (e.g. 'example.com') to restrict credentials to that domain, 
or set it to None to send credentials with all requests.
```

报错写得很明白，它是逼你想清楚凭据要发给谁。写域名就只发给那个域名，写 `None` 就是发给所有请求。这个设计是对的，毕竟把账号密码发给一个不认识的站点很危险。

**第二，settings 配的凭据是全局兜底，会「救活」你没打算认证的请求。** 我拿同一个蜘蛛换用 settings 入口跑了一遍。

```
meta 正确凭据 -> 状态码 200
meta 错误凭据 -> 状态码 401
不带任何凭据 -> 状态码 200
```

第三个变 200 了。因为全局凭据对每个请求都生效，包括那个我故意不带凭据的。meta 的优先级更高，能覆盖 settings，但反向不成立。

所以选哪个入口的标准很清楚。整站都要认证，用 settings 省事。只有一部分接口要认证，一律用 meta。

## 容易栽的跟头

**坑 1：取令牌和提交令牌不在同一个桶里。** 我第一版就是这么写的，`meta={"cookiejar": "jar_a"}` 只加在提交那一步。结果是服务端认为令牌不是这个会话发的，登录失败，而失败的表现为「还停在登录页」，看起来像账号密码错了。规则很简单，**一条会话线的第一个请求就要挂上桶**。

**坑 2：用 `response.cookies` 读响应 Cookie。** 2.19 上这个属性不存在，直接 `AttributeError`。要读服务端下发的 Cookie，用 `response.headers.getlist("Set-Cookie")` 自己解析，或者干脆交给 `CookiesMiddleware` 自动管，别去碰。

**坑 3：只配 `HTTPAUTH_USER` 和 `HTTPAUTH_PASS`。** 缺 `HTTPAUTH_DOMAIN` 的话爬虫起不来，抛 `ValueError`。这个报错信息足够清楚，照着它补上就行。写域名表示只发给该域，写 `None` 表示发给所有请求。

**坑 4：用 settings 配全局凭据，然后奇怪为什么没认证的接口也通了。** 实测里那个不带任何凭据的请求返回了 200，就是被全局凭据救的。settings 是全局兜底，meta 是逐请求覆盖，优先级 meta 更高。只有一部分接口要认证的场景，一律用 meta。

**坑 5：靠状态码判断登录是否成功。** 登录接口返回什么状态码取决于站点的实现。我这次实测拿到的是 302，换个站点可能是 200，也可能是 302 之后再跳回登录页。判断依据要看**登录后才出现的页面特征**，比如 Logout 链接、用户名、退出按钮。

**坑 6：用 `FormRequest.from_response()` 自动认表单。** 这个方法 2.17 起弃用了。它会去猜表单的 action、method 和所有隐藏字段，页面稍微复杂一点就猜错，而且错得很难查。用显式的 `FormRequest` 加 `response.css` 自己取字段，多写两行，换来的是可控。

**坑 7：把账号密码直接写进代码。** 这个坑不在框架里，在你自己的仓库里。演示站上写 `password: "whatever"` 无所谓，真实站点上这一行进版本库就等于泄露。凭据从环境变量或者配置中心读，日志里也别打出来。

## 小结

这一篇把登录这道门槛拆开了。

Cookie 那块，核心概念只有一个，请求要跟浏览器长得像。`CookiesMiddleware` 自动处理收发的细节，你需要手动管的只有分桶，而分桶的规矩是第一条请求就得挂上。

登录那块，三步的骨架是取令牌、提交、复用会话。`FormRequest` 负责第二步，`to_curl()` 负责在你搞不定的时候把请求搬到命令行里。

认证那块，记住一句就够，全局的管整站，逐请求的管局部，两个都配了的时候 meta 赢。

说真的，登录这块我踩过的坑比这一篇写出来的多。最难受的就是那种不报错的失败，写了一堆代码，跑起来安安静静，什么也没抓到。

你想想看，日志里一行错都没有，你怎么知道是哪个环节出的问题。只能靠一个个状态去比对。

遇到这种，先怀疑三件事。桶挂上了没有、令牌取对了没有、判断登录成功的特征选对了没有。这三个都确认过，基本上就通了。

这篇里要是有哪里讲得不对，欢迎拍砖。
