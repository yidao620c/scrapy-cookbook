>>> first = response.css("div.quote")[0]
>>> first.css("span.text::text").get()[:30]
'“The world as we have created '

>>> first.css("small.author::text").get()
'Albert Einstein'
