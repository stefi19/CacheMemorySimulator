from src.simulation.simulation import Simulation


class Var:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class FakeUI:
    def __init__(self):
        self.associativity = Var(2)
        self.cache_size = Var(16)
        self.line_size = Var(1)
        self.replacement_policy = Var('LRU')
        self.write_hit_policy = Var('write-back')
        self.write_miss_policy = Var('write-allocate')
        self.address_width = Var(8)
        self.input = Var('')
        self.scenario_var = Var('Matrix Traversal')
        self.num_passes = Var(1)


def test_builtin_scenarios_produce_results():
    scenarios = [
        'Matrix Traversal',
        'Random Access',
    ]
    for name in scenarios:
        ui = FakeUI()
        ui.scenario_var.set(name)
        sim = Simulation(ui)
        results = sim.run_simulation(num_passes=1)
        assert isinstance(results, list)
        assert len(results) > 0, f"Scenario {name} produced no results"
