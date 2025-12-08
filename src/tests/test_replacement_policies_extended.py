"""Extended tests for replacement policies across sets and line sizes.

These tests programmatically exercise LRU, FIFO and Random policies with
multiple `num_blocks`, `associativity` and `line_size` combinations to ensure
eviction behavior is correct when sets have to evict a way.

The tests are written to run under pytest, but they also work when invoked
via the project's venv python -m pytest.
"""

from src.core.cache import Cache


def _fill_and_evict(cache: Cache, line_size: int, target_set: int = 0):
    """Fill a single set completely, then access a new tag mapping to same set
    to trigger an eviction. Returns a tuple (evicted_tag, existing_tags).
    """
    # Use actual cache params (in case Cache adjusted associativity)
    assoc = cache.associativity
    num_sets = cache.num_sets

    # choose addresses that map to target_set: block_addr = target_set + k * num_sets
    addrs = [( (target_set + k * num_sets) * line_size ) for k in range(assoc)]

    # fill all ways
    for a in addrs:
        res = cache.access(a, is_write=False)
        assert res is not None

    # existing tags are 0..assoc-1 (because block_addr // num_sets == k)
    existing_tags = list(range(0, assoc))

    # touch the first tag to change recency for LRU tests
    _ = cache.access(addrs[0], is_write=False)

    # Now access a *new* block_addr that maps to the same set but has tag = assoc
    new_block_addr = (target_set + assoc * num_sets)
    new_addr = new_block_addr * line_size
    res = cache.access(new_addr, is_write=False)
    evicted = res[3]
    return evicted, existing_tags


def test_policies_various_configs():
    policies = ['LRU', 'FIFO', 'Random']
    # choose num_blocks and associativity pairs that divide evenly
    num_blocks_list = [4, 8, 16]
    assoc_choices = [1, 2, 4, 8]
    line_sizes = [1, 2, 4]

    for nb in num_blocks_list:
        for assoc in assoc_choices:
            if assoc > nb or nb % assoc != 0:
                continue
            for ls in line_sizes:
                for policy in policies:
                    # pass line_size into Cache so address -> block mapping matches test addresses
                    c = Cache(num_blocks=nb, associativity=assoc, replacement=policy, line_size=ls)
                    # sanity: caching internal params should be consistent
                    assert c.num_blocks == nb
                    assert c.associativity == assoc
                    # exercise filling set 0 and cause eviction
                    evicted, tags = _fill_and_evict(c, line_size=ls, target_set=0)
                    assert evicted is not None, f"Policy {policy} should evict when full (nb={nb}, assoc={assoc}, ls={ls})"
                    if policy == 'LRU':
                        # we accessed addrs[0] after filling, so LRU should evict tag 1 (the oldest)
                        # in small assoc==1 case, evicted tag will be 0
                        if assoc == 1:
                            expected = 0
                        else:
                            expected = 1
                        assert evicted.tag == expected, f"LRU evicted {evicted.tag}, expected {expected} (nb={nb}, a={assoc}, ls={ls})"
                    elif policy == 'FIFO':
                        # FIFO evicts the first inserted, which is tag 0
                        assert evicted.tag == 0, f"FIFO evicted {evicted.tag}, expected 0 (nb={nb}, a={assoc}, ls={ls})"
                    elif policy == 'Random':
                        assert evicted.tag in tags, f"Random evicted {evicted.tag} not in {tags}"
