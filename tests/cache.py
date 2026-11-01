from django.core.cache.backends.locmem import LocMemCache
from fakeredis import FakeRedis


class TestRedis(FakeRedis):
    def info(self, *args, **kwargs):
        return {"redis_version": "8.0.0"}


class MemoryCache(LocMemCache):
    """Local Django cache plus an in-memory Redis client for AA task statistics."""

    client = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = self
        self.redis = TestRedis()

    def get_client(self, write=True):
        return self.redis
