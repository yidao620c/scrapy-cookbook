import asyncio
import sys

def run():
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as r:
            r.run(main())
    else:
        asyncio.run(main())
