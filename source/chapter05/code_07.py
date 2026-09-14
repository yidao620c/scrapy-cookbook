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
