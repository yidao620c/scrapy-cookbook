    def item_completed(self, results, item, info):
        adapter = ItemAdapter(item)
        ok, bad = [], []
        for success, value in results:
            if success:
                ok.append(value)
                continue
            # 失败项是 Twisted 的 Failure，直接 str() 会得到一整段 traceback
            if hasattr(value, "getErrorMessage"):
                bad.append("%s: %s" % (value.type.__name__, value.getErrorMessage()))
            else:
                bad.append(str(value))
        adapter["images"] = ok
        adapter["image_errors"] = bad
        return item
