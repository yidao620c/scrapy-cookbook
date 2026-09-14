req = FormRequest(
    url="https://quotes.toscrape.com/login",
    formdata={"csrf_token": token, "username": "feiwuxiong", "password": "x"},
    headers={"Referer": "https://quotes.toscrape.com/login"},
    cookies={"probe": "1"},
)
print(req.to_curl())
