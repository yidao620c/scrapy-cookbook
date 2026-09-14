"""按资源类型拦截请求，给渲染提速。"""

BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}

def should_abort(request):
    """返回 True 表示这次请求不发了。request 上带 resource_type。"""
    return request.resource_type in BLOCKED_RESOURCE_TYPES
