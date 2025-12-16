"""Consolidated unit tests for core cache behaviors.

These tests focus exclusively on the cache core and simulator logic
(no UI). They cover:

- replacement policies (LRU/FIFO/Random)
- write policies (write-back vs write-through)
- write-miss policies (write-allocate vs write-no-allocate)
- eviction behavior and write-back to RAM
- a small matrix of smoke tests across cache sizes / associativities / line sizes

The tests are intentionally small and deterministic so they run fast in a
developer environment and are suitable for CI.
"""

import pytest
from src.core.cache import Cache
from src.core.ram import RAM
from src.core.simulator import CacheSimulator


def test_lru_fifo_random_basic():
    # Input: For each replacement policy in ("LRU","FIFO","Random") create
    # a Cache(num_blocks=4, associativity=2, line_size=1). Perform accesses in
    # order: access(0), access(2), then protocol-specific touches and access(4)
    # Expected: For LRU evicted.tag == 1; for FIFO evicted.tag == 0; for
    # Random evicted.tag in {0,1}.
    """
    This test uses a 4-block cache with associativity=2 (two sets). We
    populate one set then trigger an eviction and assert the evicted tag
    matches the expected outcome for LRU/FIFO; Random must evict one of the
    present tags.
    """
    for policy in ("LRU", "FIFO", "Random"):
        c = Cache(num_blocks=4, associativity=2, replacement=policy, line_size=1)
        # fill set 0 with addresses 0 and 2 (both map to set 0)
        assert c.access(0)[0] is False
        assert c.access(2)[0] is False
        if policy == 'LRU':
            # touch address 0 to make it MRU, then access addr 4 (same set)
            assert c.access(0)[0] is True
            res = c.access(4)
            evicted = res[3]
            assert evicted is not None
            # tag 1 (addr 2 block_addr 1) should be LRU and evicted
            assert evicted.tag == 1
        elif policy == 'FIFO':
            # FIFO evicts the first inserted (tag 0)
            res = c.access(4)
            evicted = res[3]
            assert evicted is not None
            assert evicted.tag == 0
        else:
            # Random eviction: evicted tag must be one of the existing tags
            res = c.access(4)
            evicted = res[3]
            assert evicted is not None
            assert evicted.tag in (0, 1)


def _fill_and_evict(cache: Cache, line_size: int, target_set: int = 0):
    """Helper: fill a given set completely and then access a new tag that
    maps to the same set, causing an eviction. Returns (evicted, existing_tags).
    """
    assoc = cache.associativity
    num_sets = cache.num_sets
    # addresses that map to target_set: block_addr = target_set + k*num_sets
    addrs = [((target_set + k * num_sets) * line_size) for k in range(assoc)]
    for a in addrs:
        res = cache.access(a, is_write=False)
        assert res is not None
    existing_tags = list(range(0, assoc))
    # touch the first entry to change recency (for LRU)
    _ = cache.access(addrs[0], is_write=False)
    new_block_addr = (target_set + assoc * num_sets)
    new_addr = new_block_addr * line_size
    res = cache.access(new_addr, is_write=False)
    evicted = res[3]
    return evicted, existing_tags


def test_policies_various_configs():
    # Input: Iterate configurations over num_blocks in [4,8,16], associativities
    # in [1,2,4,8] (valid combos only), line_sizes in [1,2,4], and policies in
    # (LRU,FIFO,Random). For each configuration create Cache(nb, assoc, policy,
    # line_size) and fill set 0 then access a new block causing eviction.
    # Expected: An eviction occurs. For LRU expected evicted.tag == (0 if
    # assoc==1 else 1). For FIFO expected evicted.tag == 0. For Random
    # expected evicted.tag in existing tags.
    policies = ['LRU', 'FIFO', 'Random']
    num_blocks_list = [4, 8, 16]
    assoc_choices = [1, 2, 4, 8]
    line_sizes = [1, 2, 4]

    for nb in num_blocks_list:
        for assoc in assoc_choices:
            if assoc > nb or nb % assoc != 0:
                continue
            for ls in line_sizes:
                for policy in policies:
                    # create cache for this configuration; the Cache ctor may
                    # adjust associativity internally if inputs were invalid,
                    # but the test only iterates valid combos above.
                    c = Cache(num_blocks=nb, associativity=assoc, replacement=policy, line_size=ls)
                    assert c.num_blocks == nb
                    assert c.associativity == assoc
                    evicted, tags = _fill_and_evict(c, line_size=ls, target_set=0)
                    assert evicted is not None, f"Policy {policy} should evict when full (nb={nb}, assoc={assoc}, ls={ls})"
                    if policy == 'LRU':
                        if assoc == 1:
                            expected = 0
                        else:
                            expected = 1
                        assert evicted.tag == expected, f"LRU evicted {evicted.tag}, expected {expected} (nb={nb}, a={assoc}, ls={ls})"
                    elif policy == 'FIFO':
                        assert evicted.tag == 0, f"FIFO evicted {evicted.tag}, expected 0 (nb={nb}, a={assoc}, ls={ls})"
                    elif policy == 'Random':
                        assert evicted.tag in tags, f"Random evicted {evicted.tag} not in {tags}"


def test_write_hit_behavior():
    # Input: For each write policy in ('write-back','write-through') create a
    # Cache(num_blocks=4, associativity=2, line_size=1, write_policy=wp). Do
    # access(0,is_write=False) then access(0,is_write=True).
    # Expected: For 'write-back' block.dirty is True and mem_write (mw) is
    # False. For 'write-through' block.dirty is False and mw is True.
    """Verify write-hit semantics:

    - write-back: the cache line's dirty bit is set, and no immediate
      backing-store write is reported (mem_write=False on the access)
    - write-through: dirty bit remains False and mem_write should be True
      because the write goes directly to memory.
    """
    for wp in ("write-back", "write-through"):
        c = Cache(num_blocks=4, associativity=2, line_size=1, write_policy=wp)
        res = c.access(0, is_write=False)
        assert res[0] is False
        res2 = c.access(0, is_write=True)
        hit2, sidx, widx, ev, mr, mw = res2
        assert hit2 is True
        block = c.sets[sidx][widx]
        if wp == 'write-back':
            assert block.dirty is True
            assert mw is False
        else:
            assert block.dirty is False
            assert mw is True


@pytest.mark.parametrize("write_miss_policy", ["write-allocate", "write-no-allocate"])
def test_write_miss_policies(write_miss_policy):
    # Input: Cache(num_blocks=4, associativity=2, line_size=1, write_policy='write-through')
    # then perform access(8,is_write=True, write_miss_policy=write_miss_policy).
    # Expected: If 'write-no-allocate': hit False, widx is None, mw True.
    # If 'write-allocate': hit False, widx is not None, mr True, mw True.
    """Verify write-miss policies:

    - write-no-allocate: the write does not allocate a cache line and
      should generate an immediate memory write (widx is None, mw True)
    - write-allocate: the cache allocates a line on write-miss and the
      simulator/cache signals memory activity accordingly.
    """
    c = Cache(num_blocks=4, associativity=2, line_size=1, write_policy='write-through')
    res = c.access(8, is_write=True, write_miss_policy=write_miss_policy)
    hit, sidx, widx, ev, mr, mw = res
    if write_miss_policy == "write-no-allocate":
        assert hit is False
        assert widx is None
        assert mw is True
    else:
        assert hit is False
        assert widx is not None
        assert mr is True
        assert mw is True


def test_evict_dirty_triggers_mem_write_in_cache():
    # Input: Cache(num_blocks=2, associativity=1, line_size=1, write_policy='write-back').
    # Sequence: access(0,is_write=True) then access(2,is_write=False) causing eviction.
    # Expected: The evicted block has dirty==True and the access reports mem_write True.
    """When evicting a dirty block under write-back, the access should
    indicate a memory write and the evicted block should have been dirty.
    """
    c = Cache(num_blocks=2, associativity=1, line_size=1, write_policy='write-back')
    # first write: allocate and mark dirty
    r1 = c.access(0, is_write=True)
    assert r1[0] is False
    # next access causes eviction
    r2 = c.access(2, is_write=False)
    ev = r2[3]
    mem_write_flag = r2[5]
    assert ev is not None
    assert getattr(ev, 'dirty', False) is True
    assert mem_write_flag is True


def test_simulator_writeback_updates_ram():
    # Input: Cache(num_blocks=2, associativity=1, line_size=1, write_policy='write-back'),
    # RAM(size_bytes=16, line_size=1). Sequence loaded: addresses [0,2] with writes [True, False].
    # Expected: After stepping the simulator, RAM.read(0) == 1 (a write-back occurred at base 0).
    """Integration test: CacheSimulator should write back dirty blocks to RAM
    on eviction (write-back policy).
    """
    cache = Cache(num_blocks=2, associativity=1, line_size=1, write_policy='write-back')
    ram = RAM(size_bytes=16, line_size=1)
    sim = CacheSimulator(cache, ram=ram)
    # sequence: write to 0 (dirty), then access 2 causing eviction and write-back
    sim.load_sequence([0, 2], writes=[True, False])
    info1 = sim.step()
    assert info1 is not None
    info2 = sim.step()
    assert info2 is not None
    # RAM should show a write at the base address of the evicted line
    assert ram.read(0) == 1


@pytest.mark.parametrize('nb,assoc,ls', [
    (4, 1, 1),
    (4, 2, 1),
    (8, 2, 2),
    (8, 4, 2),
])
def test_various_configurations_smoke(nb, assoc, ls):
    # Input: Parameterized (nb, assoc, ls). Create Cache(num_blocks=nb, associativity=assoc, line_size=ls, write_policy='write-back')
    # Then perform access(addr=0,is_write=False), access(0,is_write=True), access(0,is_write=False).
    # Expected: First access is a miss (False), second access becomes a hit (True), third access is hit (True).
    """Smoke tests across several cache configurations. Ensures basic
    allocate/read/write semantics behave as expected for each setting.
    """
    c = Cache(num_blocks=nb, associativity=assoc, line_size=ls, write_policy='write-back')
    addr = 0
    # initial read -> miss
    res = c.access(addr, is_write=False)
    assert res[0] is False
    # write -> hit after allocation
    res2 = c.access(addr, is_write=True)
    assert res2[0] is True
    # subsequent read -> hit
    res3 = c.access(addr, is_write=False)
    assert res3[0] is True


def test_line_size_eviction_and_ram_base_write():
    # Input: Cache(num_blocks=2, associativity=1, line_size=4, write_policy='write-back'),
    # RAM(size_bytes=32, line_size=4). Sequence: [0,8] with writes [True, False].
    # Expected: A single write-back to base address 0 is recorded: ram.read(0) == 1.
    """When line_size > 1, current simulator/cache semantics write back to
    the base-aligned address of the evicted block. This test verifies the
    base-aligned write happens (one write to base address).
    """
    cache = Cache(num_blocks=2, associativity=1, line_size=4, write_policy='write-back')
    ram = RAM(size_bytes=32, line_size=4)
    sim = CacheSimulator(cache, ram=ram)

    # write to address 0 (block base 0, line_size 4) -> becomes dirty
    sim.load_sequence([0, 8], writes=[True, False])
    info1 = sim.step()
    info2 = sim.step()
    assert info1 is not None and info2 is not None
    # current behavior: single write to base 0 recorded
    assert ram.read(0) == 1


def test_write_no_allocate_with_write_back_behavior():
    # Input: Cache(num_blocks=4, associativity=2, line_size=1, write_policy='write-back').
    # Perform access(7,is_write=True, write_miss_policy='write-no-allocate').
    # Expected: hit False, widx is None, mw True (immediate memory write, no allocation).
    """Ensure that write-no-allocate behavior follows current core logic.

    For write-no-allocate the cache should not allocate and the access
    should report an immediate memory write. This should hold regardless of
    the write_policy (we assert behavior for write-back config too).
    """
    c = Cache(num_blocks=4, associativity=2, line_size=1, write_policy='write-back')
    hit, sidx, widx, ev, mr, mw = c.access(7, is_write=True, write_miss_policy='write-no-allocate')
    assert hit is False
    assert widx is None
    assert mw is True


def test_cache_reset_clears_dirty_bits():
    # Input: Cache(num_blocks=4, associativity=2, line_size=1, write_policy='write-back').
    # Allocate and dirty entries via access(0,is_write=True) and access(2,is_write=True). Then call c.reset().
    # Expected: After reset all blocks have dirty False and valid False.
    """cache.reset() should clear dirty bits and valid flags."""
    c = Cache(num_blocks=4, associativity=2, line_size=1, write_policy='write-back')
    # allocate and dirty some entries
    _ = c.access(0, is_write=True)
    _ = c.access(2, is_write=True)
    # ensure some dirty bits are set
    any_dirty = any(getattr(b, 'dirty', False) for s in c.sets for b in s)
    assert any_dirty is True
    c.reset()
    # after reset, no dirty and all invalid
    for s in c.sets:
        for b in s:
            assert b.dirty is False
            assert b.valid is False


def test_ram_bounds_and_errors():
    # Input: RAM(size_bytes=8, line_size=1). Attempt ram.read(100) and ram.write(100,1).
    # Expected: Both operations raise IndexError.
    """RAM should raise IndexError for out-of-range addresses; ensure read/write enforce bounds."""
    ram = RAM(size_bytes=8, line_size=1)
    with pytest.raises(IndexError):
        ram.read(100)
    with pytest.raises(IndexError):
        ram.write(100, 1)


def test_randomized_small_stress():
    # Input: Cache(num_blocks=16, associativity=4, line_size=2, replacement='LRU', write_policy='write-back').
    # 200 random addresses in [0,63]; for each randomly choose read or write.
    # Expected: No exceptions are raised and each access returns a tuple.
    """A small randomized access sequence to exercise corner cases quickly.

    This is not a formal property test, just a short smoke to ensure no
    unexpected exceptions occur for mixed reads/writes across configs.
    """
    import random

    c = Cache(num_blocks=16, associativity=4, line_size=2, replacement='LRU', write_policy='write-back')
    rand_addrs = [random.randint(0, 63) for _ in range(200)]
    for a in rand_addrs:
        # mix reads and writes
        is_write = random.random() < 0.35
        res = c.access(a, is_write=is_write)
        assert isinstance(res, tuple)
