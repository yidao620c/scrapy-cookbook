start = script.find("var data = [") + len("var data = ")
data, end = json.JSONDecoder().raw_decode(script[start:])
