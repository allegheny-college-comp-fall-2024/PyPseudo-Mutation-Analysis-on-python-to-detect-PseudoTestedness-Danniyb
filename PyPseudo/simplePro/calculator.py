class Calculator:
    def __init__(self, plugin):
        self.plugin = plugin

    def add(self, a, b):
        # Step-by-step addition
        result = a
        while b > 0:
            result += 1
            b -= 1
        while b < 0:
            result -= 1
            b += 1
        return result

    def subtract(self, a, b):
        # Step-by-step subtraction
        result = a
        while b > 0:
            result -= 1
            b -= 1
        while b < 0:
            result += 1
            b += 1
        return result

    def multiply(self, a, b):
        # Step-by-step multiplication using repeated addition
        result = 0
        positive_b = abs(b)
        for _ in range(positive_b):
            result = self.add(result, a)
        if b < 0:
            result = -result
        return result

    def divide(self, a, b):
        # Step-by-step division using repeated subtraction
        if b == 0:
            raise ValueError("Cannot divide by zero")
        abs_a = abs(a)
        abs_b = abs(b)
        quotient = 0
        while abs_a >= abs_b:
            abs_a = self.subtract(abs_a, abs_b)
            quotient = self.add(quotient, 1)
        if (a < 0 and b > 0) or (a > 0 and b < 0):
            quotient = -quotient
        return quotient

    def modulus(self, a, b):
        # Step-by-step modulus using repeated subtraction
        if b == 0:
            raise ValueError("Cannot divide by zero")
        abs_a = abs(a)
        abs_b = abs(b)
        while abs_a >= abs_b:
            abs_a = self.subtract(abs_a, abs_b)
        if a < 0:
            abs_a = -abs_a
        return abs_a

    def power(self, a, b):
        # Step-by-step power calculation using repeated multiplication
        if b == 0:
            return 1
        result = 1
        for _ in range(abs(b)):
            result = self.multiply(result, a)
        if b < 0:
            return 1 / result
        return result

    def square_root(self, a, tolerance=1e-10, max_iterations=1000):
        # Step-by-step square root using Newton-Raphson method
        if a < 0:
            raise ValueError("Cannot take the square root of a negative number")
        if a == 0:
            return 0
        x = a
        for _ in range(max_iterations):
            root = 0.5 * (x + a / x)
            if abs(root - x) < tolerance:
                return root
            x = root
        raise ValueError("Failed to converge to a solution")