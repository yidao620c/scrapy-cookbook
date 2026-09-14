import sqlite3

c = sqlite3.connect("out/quotes.db")
print("quotes:", c.execute("select count(*) from quotes").fetchone()[0])
print("作者数:", c.execute("select count(distinct author) from quotes").fetchone()[0])
print("最长一条:", c.execute("select text_len, author from quotes order by text_len desc limit 1").fetchone())
