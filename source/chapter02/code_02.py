>>> response.css("title").get()
'<title>Quotes to Scrape</title>'

>>> response.css("title::text").get()
'Quotes to Scrape'

>>> response.css("div.quote span.text::text").get()[:40]
'“The world as we have created it is a pro'

>>> response.css("div.tags a.tag::text").getall()[:4]
['change', 'deep-thoughts', 'thinking', 'world']

>>> response.css("li.next a").attrib
{'href': '/page/2/'}
