import pytest
from calculator import Calculator
# from mutated_calculator import Calculator
from mutation_plugin import MutationPlugin

# Fixture for the plugin
@pytest.fixture
def plugin():
    plugin = MutationPlugin(mutant_file="mutants.json")
    plugin.load_mutants()  # Call load_mutants instead of load_data
    return plugin

# Fixture for the Calculator class that takes the plugin
@pytest.fixture
def calculator(plugin):
    return Calculator(plugin)

@pytest.mark.parametrize("a, b, expected", [
    (1, 2, 3),
    (-1, 1, 0),
    (100, 50, 150)
])
def test_add(calculator, a, b, expected):
    assert calculator.add(a, b) == expected

@pytest.mark.parametrize("a, b, expected", [
    (5, 3, 2),
    (10, 5, 5),
    (0, 0, 0)
])
def test_subtract(calculator, a, b, expected):
    assert calculator.subtract(a, b) == expected

@pytest.mark.parametrize("a, b, expected", [
    (3, 3, 9),
    (2, 5, 10),
    (10, 0, 0)
])
def test_multiply(calculator, a, b, expected):
    assert calculator.multiply(a, b) == expected

@pytest.mark.parametrize("a, b, expected", [
    (10, 2, 5),
    (9, 3, 3),
    (5, 0, None)
])
def test_divide(calculator, a, b, expected):
    assert calculator.divide(a, b) == expected
