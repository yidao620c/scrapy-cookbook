anchors = response.css("div.quote span a")
yield from response.follow_all(anchors, callback=self.parse_author)
