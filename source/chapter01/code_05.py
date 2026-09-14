>>> response.css("title::text").get()
'Quotes to Scrape'

>>> response.css("div.quote span.text::text").get()[:50]
'“The world as we have created it is a process of o'

>>> response.css("div.tags a.tag::text").getall()[:4]
['change', 'deep-thoughts', 'thinking', 'world']

>>> response.css("li.next a").attrib["href"]
'/page/2/'

>>> response.css("noelement").get()     # 取不到不会报错，返回 None
None
