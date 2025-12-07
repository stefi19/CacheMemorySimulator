import pytest
from src.core.cache import Cache


def test_lru_eviction():
    # 4 blocks, 2-way -> 2 sets
    c = Cache(num_blocks=4, associativity=2, replacement='LRU')
    # fill set 0 with addresses 0 and 2
    assert c.access(0)[0] is False
    assert c.access(2)[0] is False
    # access 0 to mark it MRU
    assert c.access(0)[0] is True
    # accessing 4 (maps to same set) should evict the LRU (which was block for addr 2 -> tag 1)
    res = c.access(4)
    evicted = res[3]
    assert evicted is not None
    assert evicted.tag == 1


def test_fifo_eviction():
    c = Cache(num_blocks=4, associativity=2, replacement='FIFO')
    # fill two ways
    assert c.access(0)[0] is False
    assert c.access(2)[0] is False
    # FIFO should evict the first inserted (addr 0 -> tag 0)
    res = c.access(4)
    evicted = res[3]
    assert evicted is not None
    assert evicted.tag == 0


def test_random_eviction():
    c = Cache(num_blocks=4, associativity=2, replacement='Random')
    assert c.access(0)[0] is False
    assert c.access(2)[0] is False
    # random eviction: evicted tag should be one of the two existing tags (0 or 1)
    res = c.access(4)
    evicted = res[3]
    assert evicted is not None
    assert evicted.tag in (0, 1)
