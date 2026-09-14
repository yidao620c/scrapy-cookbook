async def _download(self, slot, request):
    slot.transferring.add(request)
