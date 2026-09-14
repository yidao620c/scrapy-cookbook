for box in response.css("div.quote"):
    yield {
        "text": box.css("span.text::text").get(default="").strip(),
        "author": box.css("small.author::text").get(default="").strip(),
        "tags": box.css("div.tags a.tag::text").getall(),
    }
