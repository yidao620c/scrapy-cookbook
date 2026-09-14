print("spider:", crawler.spider.name)
print("responses:", crawler.stats.get_value("response_received_count"))
print("scheduled:", crawler.stats.get_value("scheduler/enqueued"))
stash["note"] = "remote-control-ok"
print("stash:", stash)
