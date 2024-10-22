import ast
import astor
import json

# Read mutants from the control file
def load_mutants(mutant_file):
    with open(mutant_file, 'r') as f:
        return json.load(f)

# Instrumentation to insert mutants into the code
class MutantInserter(ast.NodeTransformer):
    def __init__(self, plugin_name, mutants):
        self.plugin_name = plugin_name
        self.mutants = mutants

    def visit_FunctionDef(self, node):
        # Mutant insertion logic for specific functions
        new_body = []
        if node.name == 'add' and 'skip-addition' in self.mutants:
            # Inject mutation for addition
            new_body.append(ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('skip-addition'):\n"
                f"    print('Mutant skip-addition active, skipping addition')\n"
                f"    return a"
            ).body[0])

        if node.name == 'subtract' and 'invert-subtraction' in self.mutants:
            # Inject mutation for subtraction
            new_body.append(ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('invert-subtraction'):\n"
                f"    print('Mutant invert-subtraction active, inverting subtraction')\n"
                f"    return a + b"
            ).body[0])

        # Continue for multiplication and division
        if node.name == 'multiply' and 'skip-multiplication' in self.mutants:
            new_body.append(ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('skip-multiplication'):\n"
                f"    print('Mutant skip-multiplication active, skipping multiplication')\n"
                f"    return 1"
            ).body[0])

        if node.name == 'divide' and 'skip-division' in self.mutants:
            new_body.append(ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('skip-division'):\n"
                f"    print('Mutant skip-division active, skipping division')\n"
                f"    return None"
            ).body[0])

        # Append the original function body
        new_body.extend(node.body)
        node.body = new_body

        return node

def instrument_code(source_code, plugin_name, mutants):
    # Parse the source code into an AST
    tree = ast.parse(source_code)

    # Insert mutants into the AST
    inserter = MutantInserter(plugin_name, mutants)
    mutated_tree = inserter.visit(tree)

    # Return the modified code
    return astor.to_source(mutated_tree)

# Example usage
def run_instrumentation(input_file, output_file, mutant_file):
    # Load the mutants from the control file
    mutants_data = load_mutants(mutant_file)
    enabled_mutants = mutants_data['enabled_mutants']

    # Read the input Python file
    with open(input_file, 'r') as f:
        source_code = f.read()

    # Instrument the code by inserting mutations
    mutated_code = instrument_code(source_code, 'self.plugin', enabled_mutants)

    # Write the mutated code to the output file
    with open(output_file, 'w') as f:
        f.write(mutated_code)

# Usage example
run_instrumentation('simplePro/calculator.py', 'simplePro/mutated_calculator.py', 'mutants.json')