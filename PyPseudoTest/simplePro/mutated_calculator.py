class Calculator:

    def __init__(self, plugin):
        self.plugin = plugin

    def add(self, a, b):
        if self.plugin.is_mutant_enabled('skip-addition'):
            print('Mutant skip-addition active, skipping addition')
            return a
        return a + b

    def subtract(self, a, b):
        if self.plugin.is_mutant_enabled('invert-subtraction'):
            print('Mutant invert-subtraction active, inverting subtraction')
            return a + b
        return a - b

    def multiply(self, a, b):
        if self.plugin.is_mutant_enabled('skip-multiplication'):
            print('Mutant skip-multiplication active, skipping multiplication')
            return 1
        return a * b

    def divide(self, a, b):
        if self.plugin.is_mutant_enabled('skip-division'):
            print('Mutant skip-division active, skipping division')
            return None
        if b == 0:
            return None
        return a / b
