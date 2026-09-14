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
