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
