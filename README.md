# Scrapy 教程

**更新时间：2026-09-13**

Scrapy 是 Python 开发的著名爬虫框架，目前使用非常广泛。本教程基于最新的 Scrapy 2.19 版本编写，通过实际的例子带领你一步步掌握 Scrapy 核心。

**在线阅读:**  [http://scrapy-cookbook.readthedocs.io/zh_CN/latest/](http://scrapy-cookbook.readthedocs.io/zh_CN/latest/)

## 目录结构

```text
.
├── doc/                   # Sphinx 文档源文件
│   ├── conf.py            # Sphinx 配置
│   ├── index.rst          # 文档目录入口
│   └── *.md               # 第 1-11 章的章节文档
├── source/                # 各章节对应的 Python 源代码
│   └── chapter01/         # 对应第 1 章
│       ├── code_01.py
│       └── ...
├── Makefile               # Linux/macOS 本地构建入口
├── make.bat               # Windows 本地构建入口
└── requirements.txt       # 文档构建依赖
```

## 源代码说明

`source/chapterNN` 目录对应 `doc` 目录中的第 `NN` 章。例如：

- `doc/每天15分钟玩转Scrapy01 - 架构全景与第一个爬虫.md`
- `source/chapter01/code_01.py`


## 本地构建文档

```bash
pip install -r requirements.txt
make html
```

Windows 使用：

```bat
pip install -r requirements.txt
make.bat html
```

构建结果输出到 `build/html`。

## License

MIT
