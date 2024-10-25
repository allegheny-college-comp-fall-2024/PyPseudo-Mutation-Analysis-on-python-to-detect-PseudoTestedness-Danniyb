import ast
import astor
import json
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MutantInserter(ast.NodeTransformer):
    def __init__(self, plugin_name, mutants):
        self.plugin_name = plugin_name
        self.mutants = mutants

    def visit_FunctionDef(self, node):
        """Visit and transform function definitions"""
        # Mutant insertion logic for specific functions
        new_body = []
        
        if node.name == 'add' and 'skip-addition' in self.mutants:
            new_body.append(ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('skip-addition'):\n"
                f"    print('Mutant skip-addition active, skipping addition')\n"
                f"    return a"
            ).body[0])

        if node.name == 'subtract' and 'invert-subtraction' in self.mutants:
            new_body.append(ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('invert-subtraction'):\n"
                f"    print('Mutant invert-subtraction active, inverting subtraction')\n"
                f"    return a + b"
            ).body[0])

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

def load_mutants(mutant_file):
    """Load mutants from the control file"""
    with open(mutant_file, 'r') as f:
        return json.load(f)

def instrument_code(source_code, plugin_name, mutants):
    """Instrument the source code by inserting mutations"""
    tree = ast.parse(source_code)
    inserter = MutantInserter(plugin_name, mutants)
    mutated_tree = inserter.visit(tree)
    ast.fix_missing_locations(mutated_tree)
    return astor.to_source(mutated_tree)

def run_instrumentation(input_file, mutant_file):
    """Run the instrumentation process"""
    try:
        # Load the mutants from the control file
        mutants_data = load_mutants(mutant_file)
        enabled_mutants = mutants_data.get('enabled_mutants', [])

        # Read the input Python file
        with open(input_file, 'r') as f:
            source_code = f.read()

        # Instrument the code with mutations
        mutated_code = instrument_code(source_code, 'self.plugin', enabled_mutants)

        # Write the mutated code back to the same file
        with open(input_file, 'w') as f:
            f.write(mutated_code)
            
        logger.info(f"Successfully instrumented {input_file}")
            
    except Exception as e:
        logger.error(f"Error during instrumentation: {e}")
        raise

def restore_original(file_path, backup_path):
    """Restore the original code from backup"""
    try:
        if backup_path and os.path.exists(backup_path):
            with open(backup_path, 'r') as f:
                original_code = f.read()
            
            with open(file_path, 'w') as f:
                f.write(original_code)
                
            logger.info(f"Successfully restored original code for {file_path}")
    except Exception as e:
        logger.error(f"Error restoring original code: {e}")
        raise