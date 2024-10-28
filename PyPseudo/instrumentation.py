# instrumentation.py
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
        self.xmt_targets = set()
        self.sdl_targets = set()
        self._process_mutants(mutants)

    def _process_mutants(self, mutants):
        for mutant in mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                else:
                    self.xmt_targets.add(mutant['target'])
            elif mutant['type'] == 'sdl':
                self.sdl_targets.update(mutant['target'])

    def visit_FunctionDef(self, node):
        """Handle XMT mutations"""
        self.generic_visit(node)
        
        # Skip __init__ methods and any other special methods
        if node.name.startswith('__') and node.name.endswith('__'):
            return node
            
        # Regular function handling
        if '*' in self.xmt_targets or node.name in self.xmt_targets:
            mutation_check = ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('xmt_{node.name}'):\n"
                f"    print(f'XMT: Removing body of function {node.name}')\n"
                f"    return None"
            ).body[0]
            node.body.insert(0, mutation_check)
        
        return node

    def visit_For(self, node):
        """Handle SDL mutations for for statements"""
        self.generic_visit(node)
        
        if 'for' in self.sdl_targets:
            mutation_check = ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('sdl_for'):\n"
                f"    print('SDL: Skipping for loop')\n"
                f"    pass"
            ).body[0]
            return ast.If(
                test=mutation_check.test,
                body=mutation_check.body,
                orelse=[node]  # Keep original for loop in else branch
            )
        
        return node

    def visit_If(self, node):
        """Handle SDL mutations for if statements"""
        self.generic_visit(node)
        
        if 'if' in self.sdl_targets:
            mutation_check = ast.parse(
                f"if {self.plugin_name}.is_mutant_enabled('sdl_if'):\n"
                f"    print('SDL: Skipping if statement')\n"
                f"    pass"
            ).body[0]
            return ast.If(
                test=mutation_check.test,
                body=mutation_check.body,
                orelse=[node]  # Keep original if statement in else branch
            )
        
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