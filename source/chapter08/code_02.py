while slot.queue and slot.free_transfer_slots() > 0:
    slot.lastseen = now
    request, queue_dfd = slot.queue.popleft()
    _schedule_coro(self._wait_for_download(slot, request, queue_dfd))
