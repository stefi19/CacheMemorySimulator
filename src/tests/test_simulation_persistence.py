from src.simulation.simulation import Simulation


class Var:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class FakeUI:
    """Minimal UI-like object providing only the .get() variables
    required by Simulation and the K_associative_cache builder.
    """
    def __init__(self):
        # core configuration
        self.associativity = Var(2)
        self.cache_size = Var(4)
        self.line_size = Var(1)
        self.replacement_policy = Var('LRU')
        self.write_hit_policy = Var('write-back')
        self.write_miss_policy = Var('write-allocate')
        self.address_width = Var(8)
        # input/scenario
        self.input = Var('')
        self.scenario_var = Var('Matrix Traversal')
        self.num_passes = Var(1)


def test_simulation_reuses_cache_wrapper_and_accumulates_stats():
    ui = FakeUI()
    sim = Simulation(ui)

    # run once
    results1 = sim.run_simulation(num_passes=1)
    assert hasattr(sim, 'cache_wrapper') and sim.cache_wrapper is not None
    wrapper1 = sim.cache_wrapper
    core1 = wrapper1.cache
    stats1 = wrapper1.sim.stats.accesses

    # run again; wrapper should be reused and stats should increase
    results2 = sim.run_simulation(num_passes=1)
    wrapper2 = sim.cache_wrapper
    core2 = wrapper2.cache

    assert wrapper1 is wrapper2, "Cache wrapper should be reused across runs"
    assert core1 is core2, "Core cache should be the same instance across runs"
    assert wrapper2.sim.stats.accesses >= stats1 + 1, "Stats should accumulate across runs"


def test_replacement_policy_objects_persist_between_runs():
    ui = FakeUI()
    sim = Simulation(ui)

    sim.run_simulation(num_passes=1)
    core = sim.cache_wrapper.cache
    # there should be replacement policy objects (one per set)
    assert hasattr(core, 'replacement_policy_objs') and len(core.replacement_policy_objs) > 0
    before = core.replacement_policy_objs[0]

    # run again and ensure the same policy object instance remains
    sim.run_simulation(num_passes=1)
    after = core.replacement_policy_objs[0]
    assert before is after, "Replacement policy objects should not be recreated between runs"
