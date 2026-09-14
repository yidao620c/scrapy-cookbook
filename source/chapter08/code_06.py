    def write_report(self, spider, reason=None):
        st = self.crawler.stats.get_stats()

        def g(key, default=0):
            return st.get(key, default)

        start = st.get("start_time")
        elapsed = (
            (datetime.now(timezone.utc) - start).total_seconds() if start else 0.0
        )
        net_n, net_ms = g("latency/net_count"), g("latency/net_total_ms")
        wall_n, wall_ms = g("latency/wall_count"), g("latency/wall_total_ms")
