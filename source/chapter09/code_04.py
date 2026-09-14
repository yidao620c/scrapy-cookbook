loop = asyncio.get_running_loop()
install_reactor(REACTOR)
from twisted.internet import reactor
print(reactor._asyncioEventloop is loop)  # 必须是 True
