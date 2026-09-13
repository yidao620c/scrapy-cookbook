# 每天15分钟玩转Scrapy11 - 部署与运维

## 开场

这一篇讲爬虫跑起来之后的事。

前面十篇都是在本机命令行里跑，你能看到每一个字。上线之后这层透明就没了。服务器上进程在不在、跑到哪一步了、报了什么错，你得有别的手段去知道。这一篇就是补上这些手段。

内容分三块。第一块是怎么看见一个正在跑的爬虫，2.19 在这一块给了个新东西，我实测了一遍。第二块是怎么把爬虫从一台机器搬到一群机器上，我用 scrapyd 走了一遍完整链路，从打包到调度到取回数据。第三块是性能基线，`scrapy bench` 我这次真的跑通了，数字在下面。

顺手说一句环境的事。这几节里的命令我是在 Windows 上跑的，涉及路径和权限的地方跟 Linux 有差别，我遇到差异会单独标出来。说实话这一篇里最容易踩的坑全都跟环境有关，跟 Scrapy 本身反倒关系不大。

## 上线与运维

爬虫上线之后，最想知道的一件事是它现在在干什么。

这一章先解决「看见」，再解决「部署」，最后解决「量基线」。三件事的顺序不能反，因为你得先能看见，改完之后才知道自己改了什么。

### 1. RemoteControl 把进程打开一扇窗

2.19 新增了一个默认启用的扩展，把运行的爬虫进程变成一个可查询、可执行的 HTTP 服务。

它监听在 `localhost` 的随机端口上，要求 Bearer 令牌认证。端口和令牌写在一个 job 文件里，位置是系统状态目录下的 `scrapy/job_files`，Windows 上是 `%LOCALAPPDATA%\scrapy\job_files`。

我把目录改到项目里方便观察。

```bash
scrapy crawl slowcrawl -s REMOTE_CONTROL_JOBS_DIR=remotedir
```

文件内容是 JSON，权限 0600。

```json
{"version": 1, "pid": 21500, "port": 59167, "token": "o5VQe...",
 "spider": "slowcrawl", "project": "bookeng",
 "scrapy_version": "2.19.0", "start_time": 1789233969.96}
```

端口和令牌都拿到了，先查状态。

```bash
curl -H "Authorization: Bearer $TOK" "http://127.0.0.1:$PORT/status"
```

```json
{"pid": 19848, "spider": "slowcrawl", "project": "bookeng",
 "scrapy_version": "2.19.0", "start_time": 1789234165.05}
```

不带令牌会拿到 401，这一条我也验了。

真正有意思的是 `/execute`，它让你在那个进程里跑 Python。作用域里有两个东西，`crawler` 是当前爬虫实例，`stash` 是一个跨调用持久存在的字典。

```bash
curl -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d @exec1.json "http://127.0.0.1:$PORT/execute"
```

`exec1.json` 里是这段代码。

```python
print("spider:", crawler.spider.name)
print("responses:", crawler.stats.get_value("response_received_count"))
print("scheduled:", crawler.stats.get_value("scheduler/enqueued"))
stash["note"] = "remote-control-ok"
print("stash:", stash)
```

返回是这样的。

```json
{"status": "ok",
 "output": "spider: slowcrawl\nresponses: 4\nscheduled: 30\nstash: {'note': 'remote-control-ok'}\n",
 "traceback": null, "elapsed_sec": 0.0}
```

再调一次，换一段代码，验证 `stash` 是不是真的跨调用活着。

```json
{"status": "ok",
 "output": "stash 还在: remote-control-ok\n已抓页面: 4\n引擎在跑: True\n",
 "traceback": null, "elapsed_sec": 0.0}
```

三件事都对上了。实时统计能读到，`stash` 跨调用持久，`crawler.engine.running` 反映出引擎当前状态。

![RemoteControl 的四个端点](https://static.xiongneng.me/scrapy-11-remote-control-20260913062827.png)

⚠️ 有两件事必须提醒。第一，**它能执行任意代码，等价于把解释器开在别人面前**，虽然默认只监听 `127.0.0.1` 而且有令牌，但也别往公网地址上绑。第二，**job 文件里就放着令牌**，权限虽然设成了 0600，也绝对不要随手贴到聊天窗口或者 issue 里。

这个扩展官方说是给 Scrapy MCP server 用的，也就是说你以后可以让 AI 直接通过这扇窗看你的爬虫。

### 2. 部署的三种落点

爬虫跑在本机和生产环境是两件事。第三种部署方式这里只讲选择依据，不展开操作。

Scrapyd 是官方出的爬虫服务。它把项目打包上传、按需调度、在网页上看日志。适合一个团队共用几台机器跑很多爬虫的场景。配套的工具是 `scrapyd-client`，用它把项目打成 egg 再传上去。

⚠️ 用 Scrapyd 之前先改一件事，**它的监听地址默认是 `0.0.0.0`**，也就是全网可达。生产环境务必改成内网地址，前面再套一层带认证的反向代理。

容器是另一种落点。爬虫的依赖经常很啰嗦，浏览器、字体、系统库都算，打进镜像之后「在我机器上能跑」这句话才算作数。`JOBDIR` 记得挂到卷上，不然容器一重启进度就没了。

再就是托管平台。官方的 Scrapy Cloud 属于这一类，把代码推上去就能跑。省事的地方在于不用管机器，代价是调试不如自己机器上方便，尤其是要抓需要浏览器的站点。

### 3. 用 bench 给机器量个底

调优之前得先有一个基线，不然你不知道自己改的到底是快了还是慢了。

官方准备了一个命令。

```bash
scrapy bench
```

它的做法是起一个本机服务端，在一个固定地址上拉固定量的数据，默认跑 10 秒看能处理多少页面。

我这次把它跑通了，逐秒的输出是这样。

```
2026-09-13 06:05:44 [scrapy.extensions.logstats] INFO: Crawled 210 pages (at 12600 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:45 [scrapy.extensions.logstats] INFO: Crawled 394 pages (at 11040 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:46 [scrapy.extensions.logstats] INFO: Crawled 562 pages (at 10080 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:47 [scrapy.extensions.logstats] INFO: Crawled 722 pages (at 9600 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:48 [scrapy.extensions.logstats] INFO: Crawled 874 pages (at 9120 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:49 [scrapy.extensions.logstats] INFO: Crawled 1010 pages (at 8160 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:52 [scrapy.extensions.logstats] INFO: Crawled 1402 pages (at 7680 pages/min), scraped 0 items (at 0 items/min)
2026-09-13 06:05:53 [scrapy.extensions.logstats] INFO: Crawled 1522 pages (at 7200 pages/min), scraped 0 items (at 0 items/min)
```

跑完的统计。

```
 'elapsed_time_seconds': 10.159261299995705,
 'finish_reason': 'closespider_timeout',
 'downloader/response_count': 1538,
 'downloader/response_bytes': 10173928,
 'scheduler/enqueued': 30758,
```

十秒跑了一千五百多个响应，十兆字节。**注意那个速率曲线是往下走的**，第一秒一万两千多，到了第十秒掉到七千二。这是正常的，累积的排队和本机资源占用会一点点吃掉速度，所以拿这个数做横向比较的时候，要保证跑的是同样的时长，不然比出来的不是同一件事。

![bench 的逐秒速率曲线](https://static.xiongneng.me/scrapy-11-bench-20260913062827.png)

⚠️ 第一次跑它的时候我拿到的是这个。

```
2026-09-13 06:03:35 [scrapy.downloadermiddlewares.retry] ERROR: Gave up retrying <GET http://localhost:8998?total=100000&show=20> (failed 3 times): 502 Bad Gateway
 'downloader/response_status_count/502': 1,
```

重试三次全是 502，`bench` 直接失败退出。报错里没有任何一个字提到代理，那三个 502 看起来像是本机那个 8998 服务端出了问题。

真实原因是我这台机器配了系统级 HTTP 代理，`bench` 内部发的请求走了代理，而代理当然不知道 `localhost:8998` 是什么，于是回了一个 502。把代理相关的环境变量清掉，或者把 `localhost` 加进 `NO_PROXY`，它就正常了。

**这个坑值得单独记住，因为它会伪装成别的错误。** 任何连本机端口的实验，跑之前都先确认代理有没有被绕开。我在前面几篇里搭的那些本地服务端，也是这样才跑通的。这事儿我当初没往代理上想，一直在查那个服务端，绕了一圈才回头发现。

回到 `bench` 的定位。说到底它测的是框架在你机器上的吞吐上限，不是你那个具体蜘蛛的吞吐。蜘蛛的形状、目标站的响应速度、反爬策略都会大幅改变结果。**有真实数据的时候以真实数据为准，`bench` 的用途是换机器、换配置之后的横向比较。** 我自己的感受是，性能这件事上直觉的准确率低得让人意外，有个数字在手边会踏实很多。

## 用 scrapyd 把爬虫变成服务

上一节把三种落点的特点过了一遍，这一节挑 scrapyd 走一条完整的链路，从打包到调度到取回数据。它是官方出的爬虫服务，适合一个团队共用几台机器跑很多爬虫的场景。

装两个包，`scrapyd` 是服务端，`scrapyd-client` 是打包上传用的客户端。

```bash
pip install scrapyd scrapyd-client
```

服务端要一份配置文件。默认端口是 6800，我换成 6801 避免跟别的东西撞上，监听地址明确写成 `127.0.0.1`。

```ini
[scrapyd]
eggs_dir     = eggs
logs_dir     = logs
items_dir    = items
jobs_to_keep = 5
max_proc     = 4
http_port    = 6801
bind_address = 127.0.0.1
```

起起来之后，日志里能看到它在做什么。

```
2026-09-13T05:57:08+0800 [scrapyd.app#info] Scrapyd web console available at http://127.0.0.1:6801/
2026-09-13T05:57:08+0800 [-] Site starting on 6801
2026-09-13T05:57:08+0800 [Launcher] Scrapyd 1.6.0 started: max_proc=4, runner='scrapyd.runner'
2026-09-13T05:57:08+0800 [scrapyd.launcher#debug] Process slot 0 ready
2026-09-13T05:57:08+0800 [scrapyd.launcher#debug] Process slot 1 ready
2026-09-13T05:57:08+0800 [scrapyd.launcher#debug] Process slot 2 ready
2026-09-13T05:57:08+0800 [scrapyd.launcher#debug] Process slot 3 ready
```

`max_proc` 是 4，下面四行是四个进程槽就位。**这个数字决定了这台机器上同时能跑几个爬虫进程**，它跟你蜘蛛内部的并发是两回事，一层是进程级的，一层是请求级的。

⚠️ `bind_address` 这一行别省。scrapyd 的默认值是 `0.0.0.0`，也就是全网可达，而它的 API 里有一个 `schedule` 接口可以让你启动任意已上传的爬虫。生产环境务必写成内网地址，前面再套一层带认证的反向代理。

客户端那一侧改 `scrapy.cfg`。

```ini
[settings]
default = dep.settings

[deploy]
url = http://127.0.0.1:6801/
project = dep
```

然后一条命令上传。

```bash
scrapyd-deploy
```

输出是这样的。

```
Packing version 1789250286
Deploying to project "dep" in http://127.0.0.1:6801/addversion.json
Server response (200):
{"project": "dep", "version": "1789250286", "spiders": 1, "status": "ok", "node_name": "WIN-20260318JJX"}
```

版本号是打包那一刻的 Unix 时间戳，所以每次上传都是一个新版本，服务端会同时留着旧版本。回执里的 `spiders` 是它从这个包里认出来的蜘蛛数量。

上传之后服务端的工作目录长这样。

```
.
├── dbs/
│   └── dep.db
├── eggs/
│   └── dep/1789250286.egg
├── items/
│   └── dep/quotes/
├── logs/
└── scrapyd.conf
```

`eggs` 里是你上传的包，`dbs` 里是作业记录，`items` 和 `logs` 按项目和蜘蛛分层。

接下来全走 HTTP 接口。四个查询接口先看一眼。

![scrapyd 的打包与调度链路](https://static.xiongneng.me/scrapy-11-scrapyd-flow-20260913062827.png)

```bash
curl -s http://127.0.0.1:6801/listprojects.json
curl -s "http://127.0.0.1:6801/listspiders.json?project=dep"
curl -s "http://127.0.0.1:6801/listversions.json?project=dep"
```

```json
{"projects": ["dep"], "status": "ok", "node_name": "WIN-20260318JJX"}
{"spiders": ["quotes"], "status": "ok", "node_name": "WIN-20260318JJX"}
{"versions": ["1789250286"], "status": "ok", "node_name": "WIN-20260318JJX"}
```

让它跑一次。

```bash
curl -s -X POST http://127.0.0.1:6801/schedule.json -d project=dep -d spider=quotes
```

```json
{"jobid": "285c5365aef511f18ad4c858b329b27d", "status": "ok", "node_name": "WIN-20260318JJX"}
```

拿到 jobid 之后查状态。

```json
{"pending": [], "running": [],
 "finished": [{"id": "285c5365aef511f18ad4c858b329b27d", "project": "dep", "spider": "quotes",
   "start_time": "2026-09-13 05:59:02.444967", "end_time": "2026-09-13 05:59:05.898301",
   "log_url": "/logs/dep/quotes/285c5365aef511f18ad4c858b329b27d.log",
   "items_url": "/items/dep/quotes/285c5365aef511f18ad4c858b329b27d.jl"}],
 "status": "ok", "node_name": "WIN-20260318JJX"}
```

任务跑完了，起止时间、日志地址、数据地址都在里面。这两个 URL 可以直接拼上服务端地址去下载，抓到的数据就在那个 `.jl` 文件里，一行一条 JSON。

⚠️ 这里有个数字值得注意。任务的墙钟耗时是三秒半，而任务日志里那一行是 `'elapsed_time_seconds': 1.3554213000024902`。**差了大约两秒，那是进程启动和 egg 解包的开销。** 也就是说 `elapsed_time_seconds` 量的是蜘蛛自己的运行时间，不含调度开销。你要是拿它估算「跑一千个任务要多久」，会明显低估。

三个东西一起构成了这套方案的可用性。`eggs` 目录让回滚变成「切一个版本号」，`logs` 目录让每个任务的输出都能事后翻，`items` 目录让数据不用你自己写管道去落盘。代价是它只负责调度，任务的依赖、环境、出口 IP 这些还是得你自己在机器上准备好。

关于容器和托管平台，我在这个环境里没有 Docker 可用，所以那两条路径只写选择依据，不给操作步骤。这里要如实说清楚，避免你把没验证过的东西当成验证过的。

## 容易栽的跟头

**坑 1：以为 job 文件会自己清理干净。** 它会清理，但只在正常退出的时候。我做完这一篇的实验之后去数了一下那个目录，里面有 80 个文件，日期从早上零点一路排到实验结束。

```
$ ls -1 "$LOCALAPPDATA/scrapy/job_files" | wc -l
80
```

这些文件是爬虫进程正常结束时自己删掉的漏网之鱼，进程被强杀、机器重启、调试时按了 Ctrl-C，都留下一个。它们本身很小，两百字节一个，麻烦在于**里面存着对应进程的端口和令牌**。放在那儿不占地方，但它是一份凭证。

定期清一下。目录位置是系统状态目录下的 `scrapy/job_files`，Windows 上是 `%LOCALAPPDATA%\scrapy\job_files`，Linux 上在 XDG 的状态目录里。要换位置就用 `REMOTE_CONTROL_JOBS_DIR` 指过去，我在实验里就是这么做的。

**坑 2：把 `REMOTE_CONTROL_ENABLED` 设成真，以为它就在跑。** 这个扩展依赖 asyncio 支持，不满足条件的时候会自动禁用，日志里只会留一行。它不会让爬虫启动失败，所以很容易被忽略。**判断方法不是看配置，是看启动日志里有没有那一行监听端口的提示**，或者直接去 job 文件目录看有没有新文件生成。

```
2026-09-13 06:03:35 [scrapy.extensions.remote_control] INFO: Remote control HTTP server listening on port 55861 (job 23336-fd8b8f49a4c748a0943644cb03425f50)
```

有这一行才算真的起来了。

**坑 3：连本机端口的实验被系统代理拦下去。** 这个坑害我多花了一轮。我用 `scrapy bench` 的时候第一次拿到的是三次 502 重试然后放弃，报错里一个字都没提代理，看起来像是那个本机服务端坏了。

```
2026-09-13 06:03:35 [scrapy.downloadermiddlewares.retry] ERROR: Gave up retrying <GET http://localhost:8998?total=100000&show=20> (failed 3 times): 502 Bad Gateway
```

原因是这台机器配了系统级 HTTP 代理，请求走了代理，代理不知道 `localhost:8998` 是什么就回了个 502。清掉代理环境变量，或者把 `localhost` 和 `127.0.0.1` 加进 `NO_PROXY`，立刻就正常了。**任何连本机地址的实验，跑之前先确认这一条。** 它后面还会以各种面貌出现，比如 curl 能通而程序不通，或者「本地接口莫名其妙返回 502」。

**坑 4：拿 `elapsed_time_seconds` 估算批量任务的耗时。** 这个值量的是蜘蛛自己的运行时间，进程启动和 egg 解包不算在里面。实测一个任务墙钟跑了三秒半，日志里的 `elapsed_time_seconds` 是 1.36 秒，差了大约两秒。任务规模小的时候这个比例很大，你要是按它去规划「一千个任务要多久」，算出来的数字会明显偏乐观。

**坑 5：scrapyd 的 `bind_address` 用默认值。** 它默认监听 `0.0.0.0`，全网可达。而它的 `schedule` 接口允许启动服务器上任意一个已上传的爬虫。这两件事凑在一起，等于给任何能访问到 6800 端口的人递了一把钥匙，他可以让你的爬虫跑起来。生产环境改成内网地址，外面套一层带认证的反向代理。

**坑 6：job 文件里那个 0600 权限在 Windows 上不等于安全。** Scrapy 写这个文件的时候确实按 `0o600` 创建，那是 POSIX 的权限位。Windows 上走的是另一套访问控制模型，这些位是模拟出来的，实际的文件访问控制由 NTFS 的 ACL 决定。

```
-rw-r--r-- 1 Administrator 197121 204 Sep 13 01:02 10724-58d7fa7328cf4a8b8af06a18b42d51d5.json
```

我在 Windows 上看到的就是上面这个样子，不是 0600。**别把权限位当成唯一一道防线**，真正的约束是那个文件里存着能在爬虫进程里执行任意代码的令牌，所以它不该出现在聊天窗口、工单、截图或者代码仓库里。

## 小结

这一篇的三块内容，其实在回答同一个问题，你怎么知道线上那个东西还好。

RemoteControl 给的是最细的一层。它让你在一个跑着的进程里执行代码，实时统计、当前状态、甚至临时改一点东西都能做到。2.19 把它做成默认开启，说明官方认为「能看见运行中的进程」是个基础需求。但它也是一扇需要认真对待的门，能执行代码这个能力本身就是风险。

scrapyd 给的是中间一层。打包、上传、调度、取数据，全走 HTTP 接口，一套流程下来每个任务的边界都清清楚楚。我实测那一条链路的时候，最有用的是它把「墙钟耗时」和「蜘蛛耗时」分开了，这两个数摆在一起你才知道调度开销占了多少。

`bench` 给的是最底下那一层，机器的能力上限。这个数字跟你的蜘蛛没有直接关系，但它是你换机器、换配置时唯一可比的基准。

这一篇里我最想让你注意的还是那个 502。它跟爬虫、跟 Scrapy、跟这台机器的性能都没有关系，纯粹是环境里有个代理在中间。**排错的时候，先确认自己的实验环境是干净的，比钻研报错信息更省时间。** 我在这个系列里搭了不少本地服务端做对照实验，每一次都要先过这一关。

到这里十一篇就写完了。从第一个爬虫到能上线的服务，中间那些我自己踩过的坑基本都放进来了。写的时候我尽量把「我测出来的」和「文档上说的」分开，凡是标了数字的地方都有对应的运行记录，你可以照着复现。

这篇里要是有哪里讲得不对，欢迎拍砖。
