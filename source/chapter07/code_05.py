    def on_robots_parsed(self, robotparser, request):
        ua = self.crawler.settings["USER_AGENT"]
        for path in ("/ok", "/private/secret", "/private/public-ok"):
            verdict = robotparser.allowed(HOST + path, ua)
            self.logger.info(
                "robots 判定 %-20s → %s", path, "允许" if verdict else "禁止"
            )
