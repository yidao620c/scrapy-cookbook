>>> response.xpath('//small[@class="author"]/text()').getall()[:3]
['Albert Einstein', 'J.K. Rowling', 'Albert Einstein']

>>> response.xpath('//a[contains(., "Next")]/@href').get()
'/page/2/'

>>> response.xpath('//div[@class="tags"]/a/@href').getall()[:3]
['/tag/change/page/1/', '/tag/deep-thoughts/page/1/', '/tag/thinking/page/1/']
