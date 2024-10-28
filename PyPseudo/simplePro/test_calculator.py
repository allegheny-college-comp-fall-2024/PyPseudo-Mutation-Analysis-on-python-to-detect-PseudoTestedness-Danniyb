import pytest
from calculator import Calculator
from mutation_plugin import MutationPlugin

# Fixture for the plugin
@pytest.fixture
def plugin():
    plugin = MutationPlugin(mutant_file="mutants.json")
    plugin.load_mutants()
    return plugin

# Fixture for the Calculator class that takes the plugin
@pytest.fixture
def calculator(plugin):
    return Calculator(plugin)

def test_add(calculator):
    assert calculator.add(1, 2) == 3
    assert calculator.add(-1, 1) == 0
    assert calculator.add(100, 50) == 150
    assert calculator.add(0, 0) == 0
    assert calculator.add(-5, -5) == -10
    assert calculator.add(5, -3) == 2
    assert calculator.add(-5, 3) == -2

def test_subtract(calculator):
    assert calculator.subtract(5, 3) == 2
    assert calculator.subtract(10, 5) == 5
    assert calculator.subtract(0, 0) == 0
    assert calculator.subtract(-5, -3) == -2
    assert calculator.subtract(-5, 5) == -10
    assert calculator.subtract(5, -3) == 8

def test_multiply(calculator):
    assert calculator.multiply(3, 3) == 9
    assert calculator.multiply(2, 5) == 10
    assert calculator.multiply(10, 0) == 0
    assert calculator.multiply(-2, 4) == -8
    assert calculator.multiply(-3, -3) == 9
    assert calculator.multiply(0, 10) == 0
    assert calculator.multiply(5, -2) == -10

def test_divide(calculator):
    assert calculator.divide(10, 2) == 5
    assert calculator.divide(9, 3) == 3
    assert calculator.divide(5, 1) == 5
    assert calculator.divide(-10, 2) == -5
    assert calculator.divide(10, -2) == -5
    assert calculator.divide(-10, -2) == 5
    assert calculator.divide(7, 2) == 3  # Integer division
    assert calculator.divide(-7, 2) == -3
    assert calculator.divide(7, -2) == -3
    assert calculator.divide(-7, -2) == 3

def test_divide_by_zero(calculator):
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calculator.divide(5, 0)

def test_modulus(calculator):
    assert calculator.modulus(10, 3) == 1
    assert calculator.modulus(9, 4) == 1
    assert calculator.modulus(5, 5) == 0
    assert calculator.modulus(-10, 3) == -1
    assert calculator.modulus(10, -3) == 1
    assert calculator.modulus(-10, -3) == -1
    assert calculator.modulus(7, 2) == 1
    assert calculator.modulus(-7, 2) == -1
    assert calculator.modulus(7, -2) == 1
    assert calculator.modulus(-7, -2) == -1

def test_modulus_by_zero(calculator):
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calculator.modulus(5, 0)

def test_power(calculator):
    assert calculator.power(2, 3) == 8
    assert calculator.power(5, 0) == 1
    assert calculator.power(-2, 3) == -8
    assert calculator.power(2, -2) == 0.25
    assert calculator.power(0, 5) == 0
    assert calculator.power(0, 0) == 1  # Commonly defined as 1
    assert calculator.power(5, -1) == 0.2
    assert calculator.power(-2, -2) == 0.25

def test_square_root(calculator):
    assert abs(calculator.square_root(4) - 2) < 1e-9
    assert abs(calculator.square_root(9) - 3) < 1e-9
    assert abs(calculator.square_root(0) - 0) < 1e-9
    assert abs(calculator.square_root(25) - 5) < 1e-9
    assert abs(calculator.square_root(2) - 1.41421356) < 1e-7  # Non-perfect square
    assert abs(calculator.square_root(1e-10) - 1e-05) < 1e-9  # Very small number
    assert abs(calculator.square_root(1e+10) - 1e+05) < 1e-4  # Very large number

def test_square_root_of_negative(calculator):
    with pytest.raises(ValueError, match="Cannot take the square root of a negative number"):
        calculator.square_root(-4)

def test_square_root_non_converging(calculator):
    # Force the method to fail by setting max_iterations to 1
    with pytest.raises(ValueError, match="Failed to converge to a solution"):
        calculator.square_root(4, max_iterations=1)