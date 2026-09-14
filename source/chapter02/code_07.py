# 三种等价写法，任选一种
yield response.follow("/page/2/", callback=self.parse)
yield response.follow(response.css("li.next a"), callback=self.parse)
yield response.follow(response.css("li.next a::attr(href)").get(), callback=self.parse)
