"""Bound API request bodies and provide a modest per-instance demo throttle."""

from collections import OrderedDict, deque
from time import monotonic

from starlette.responses import JSONResponse


class RequestLimits:
    def __init__(self, app, max_bytes, per_minute):
        self.app, self.max_bytes, self.per_minute = app, max_bytes, per_minute
        self.clients = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        now = monotonic()
        address = (scope.get("client") or ("unknown",))[0]
        bucket = self.clients.pop(address, deque())
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        self.clients[address] = bucket
        if len(self.clients) > 1024:
            self.clients.popitem(last=False)
        if len(bucket) >= self.per_minute:
            return await JSONResponse({"detail": "Request limit reached; retry shortly"}, 429,
                                      headers={"Retry-After": "60"})(scope, receive, send)
        bucket.append(now)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                return await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(chunks)

        async def replay():
            message = next(iterator, None)
            return message if message is not None else await receive()

        return await self.app(scope, replay, send)
