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
