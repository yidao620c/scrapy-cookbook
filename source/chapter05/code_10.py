async def parse(self, response):
    page = response.meta["playwright_page"]
    try:
        await page.wait_for_selector("div.quote")
        # ... 解析
    finally:
        # 这一行不能漏，漏了页面不会回收，跑久了浏览器就卡住了
        await page.close()
