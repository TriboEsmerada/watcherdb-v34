"""
Unit tests for RedisLikeCache
"""

import time
import pytest
from watcherdb.core.cache import RedisLikeCache


class TestRedisLikeCache:
    """Test suite for RedisLikeCache"""

    def test_cache_set_get(self, cache):
        """Test basic set and get operations"""
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_set_with_ttl(self, cache):
        """Test set with TTL expiration"""
        cache.set("key2", "value2", ttl=1)
        assert cache.get("key2") == "value2"

        # Wait for expiration
        time.sleep(1.5)
        assert cache.get("key2") is None

    def test_cache_delete(self, cache):
        """Test delete operation"""
        cache.set("key3", "value3")
        assert cache.exists("key3")

        cache.delete("key3")
        assert not cache.exists("key3")

    def test_cache_keys(self, cache):
        """Test keys listing"""
        cache.set("test:1", "value1")
        cache.set("test:2", "value2")
        cache.set("other:1", "value3")

        all_keys = cache.keys("*")
        assert len(all_keys) >= 3

        test_keys = cache.keys("test:*")
        assert len(test_keys) == 2

    def test_cache_flushall(self, cache):
        """Test flush all operation"""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.flushall()
        assert len(cache.keys("*")) == 0

    def test_cache_incr(self, cache):
        """Test increment operation"""
        cache.set("counter", 10)
        result = cache.incr("counter", 5)
        assert result == 15
        assert cache.get("counter") == 15

    def test_cache_expire(self, cache):
        """Test setting TTL on existing key"""
        cache.set("key4", "value4")
        cache.expire("key4", 1)

        assert cache.get("key4") == "value4"
        time.sleep(1.5)
        assert cache.get("key4") is None

    def test_cache_ttl(self, cache):
        """Test TTL query"""
        cache.set("key5", "value5", ttl=10)
        ttl = cache.ttl("key5")
        assert 8 <= ttl <= 10

        # Key without TTL
        cache.set("key6", "value6")
        assert cache.ttl("key6") == -1

        # Non-existent key
        assert cache.ttl("nonexistent") == -2

    def test_cache_stats(self, cache):
        """Test statistics tracking"""
        cache.set("test1", "value1")
        cache.get("test1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["sets"] >= 1

    def test_cache_complex_types(self, cache):
        """Test storing complex data types"""
        # Dict
        cache.set("dict_key", {"a": 1, "b": 2})
        assert cache.get("dict_key") == {"a": 1, "b": 2}

        # List
        cache.set("list_key", [1, 2, 3])
        assert cache.get("list_key") == [1, 2, 3]

        # Set
        cache.set("set_key", {1, 2, 3})
        assert cache.get("set_key") == {1, 2, 3}

        # Tuple
        cache.set("tuple_key", (1, 2, 3))
        assert cache.get("tuple_key") == (1, 2, 3)


class TestCachePubSub:
    """Testes para Pub/Sub do cache"""

    def test_pubsub_subscribe_publish(self, cache):
        """Teste basico de subscribe e publish"""
        messages = []

        def callback(msg):
            messages.append(msg)

        cache.subscribe("test_channel", callback)
        result = cache.publish("test_channel", "Hello World")

        assert result == 1
        assert len(messages) == 1
        assert messages[0] == "Hello World"

    def test_pubsub_multiple_subscribers(self, cache):
        """Teste com multiplos subscribers"""
        messages1 = []
        messages2 = []

        cache.subscribe("multi_channel", lambda m: messages1.append(m))
        cache.subscribe("multi_channel", lambda m: messages2.append(m))

        cache.publish("multi_channel", "Test Message")

        assert len(messages1) == 1
        assert len(messages2) == 1

    def test_pubsub_unsubscribe(self, cache):
        """Teste de unsubscribe"""
        messages = []

        def callback(msg):
            messages.append(msg)

        cache.subscribe("unsub_channel", callback)
        cache.publish("unsub_channel", "First")

        cache.unsubscribe("unsub_channel", callback)
        cache.publish("unsub_channel", "Second")

        assert len(messages) == 1
        assert messages[0] == "First"

    def test_publish_no_subscribers(self, cache):
        """Teste de publish sem subscribers"""
        result = cache.publish("empty_channel", "Message")
        assert result == 0


class TestCacheEdgeCases:
    """Testes de casos de borda"""

    def test_get_nonexistent_key(self, cache):
        """Teste de get em chave inexistente"""
        result = cache.get("nonexistent_key_12345")
        assert result is None

    def test_delete_nonexistent_key(self, cache):
        """Teste de delete em chave inexistente"""
        result = cache.delete("nonexistent_key_12345")
        assert result is False

    def test_incr_on_new_key(self, cache):
        """Teste de incr em chave nova"""
        cache.delete("new_counter")  # Garantir que nao existe
        result = cache.incr("new_counter", 5)
        assert result == 5

    def test_incr_with_string_value(self, cache):
        """Teste de incr em valor string retorna None"""
        cache.set("string_key", "not_a_number")
        result = cache.incr("string_key")
        assert result is None

    def test_expire_nonexistent_key(self, cache):
        """Teste de expire em chave inexistente"""
        result = cache.expire("nonexistent_key_12345", 10)
        assert result is False

    def test_set_overwrite(self, cache):
        """Teste de set sobrescrevendo valor existente"""
        cache.set("overwrite_key", "original")
        cache.set("overwrite_key", "new_value")
        assert cache.get("overwrite_key") == "new_value"

    def test_set_with_then_without_ttl(self, cache):
        """Teste de set com TTL depois sem TTL"""
        cache.set("ttl_test", "value", ttl=60)
        assert cache.ttl("ttl_test") > 0

        cache.set("ttl_test", "value2")  # Sem TTL
        assert cache.ttl("ttl_test") == -1

    def test_keys_empty_cache(self, cache):
        """Teste de keys em cache vazio"""
        cache.flushall()
        result = cache.keys("*")
        assert result == []

    def test_exists_via_get(self, cache):
        """Teste de exists usando get internamente"""
        cache.set("exists_test", "value")
        assert cache.exists("exists_test") is True

        cache.delete("exists_test")
        assert cache.exists("exists_test") is False


class TestCacheStats:
    """Testes para estatisticas do cache"""

    def test_stats_hit_rate(self, cache):
        """Teste de hit rate nas estatisticas"""
        cache.flushall()

        # Criar e acessar chaves
        cache.set("hit1", "v1")
        cache.set("hit2", "v2")
        cache.get("hit1")  # Hit
        cache.get("hit2")  # Hit
        cache.get("miss1")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] >= 2
        assert stats["misses"] >= 1
        assert "hit_rate" in stats
        assert "memory_usage_mb" in stats

    def test_stats_memory_usage(self, cache):
        """Teste de uso de memoria nas estatisticas"""
        cache.set("mem_test", "x" * 1000)
        stats = cache.get_stats()

        assert stats["memory_bytes"] > 0
        assert stats["memory_usage_mb"] >= 0

    def test_stats_num_keys(self, cache):
        """Teste de contagem de chaves"""
        cache.flushall()
        cache.set("k1", "v1")
        cache.set("k2", "v2")

        stats = cache.get_stats()
        assert stats["num_keys"] == 2
