>>> response.css("span.text::text").re(r"([A-Z][a-z]+) is")
['It', 'One', 'Imperfection', 'It']

>>> response.css("span.text::text").re_first(r"world")
'world'
