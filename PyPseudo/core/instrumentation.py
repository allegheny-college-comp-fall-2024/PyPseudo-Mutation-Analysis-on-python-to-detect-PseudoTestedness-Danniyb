import ast
import astor
import json
import logging
import shutil
import os
import re
from pathlib import Path
from .utils import setup_project_environment, inject_mutation_support, copy_support_files

# Configure logging for better debugging and monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MutantInserter(ast.NodeTransformer):
    def __init__(self, plugin_name, mutants):
        # Initialize basic configuration
        super().__init__()
        self.plugin_name = plugin_name
        self.mutants = mutants
        self.xmt_targets = set()
        self.sdl_targets = set()
        self.counters = {'xmt': 1, 'for': 1, 'if': 1}
        self.nodes_visited = {'if': 0, 'for': 0}
        self.is_class_based = False  # Track if code is class-based
        self.process_mutants()
        logger.info(f"Initialized with targets - XMT: {self.xmt_targets}, SDL: {self.sdl_targets}")


    def _check_code_context(self, tree):
        """Check if code is class-based or procedural"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self.is_class_based = True
                break

    def _create_mutation_check(self, mutation_id, message):
        """Create appropriate mutation check based on context"""
        plugin_ref = "self.plugin" if self.is_class_based else "plugin"
        return ast.parse(
            f"if {plugin_ref}.is_mutant_enabled('{mutation_id}'):\n"
            f"    print({message!r})\n"
            f"    return None"
        ).body[0]
    

    def visit_Module(self, node):
        """Add necessary imports for procedural code"""
        self._check_code_context(node)
        
        if not self.is_class_based:
            # Add imports and setup code for procedural modules
            import_code = '''
    import os
    import sys
    from pathlib import Path

    # Add local .pypseudo directory to path
    _support_dir = Path(__file__).parent / '.pypseudo'
    if _support_dir.exists():
        sys.path.insert(0, str(_support_dir))

    # Import from local support directory
    from mutation_support import MutationPlugin, is_mutant_enabled

    # Initialize plugin with local config
    plugin = MutationPlugin(str(_support_dir / 'mutants.json'))
    plugin.load_mutants()  # Load mutation configuration'''

            # Parse the imports with dedent to remove any leading whitespace
            from textwrap import dedent
            imports = ast.parse(dedent(import_code).strip()).body
            
            # Add imports at the start of the module
            node.body = imports + node.body
                
        return self.generic_visit(node)
    
                        
    def process_mutants(self):
        for mutant in self.mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                else:
                    self.xmt_targets.add(mutant['target'])
            elif mutant['type'] == 'sdl':
                self.sdl_targets.update(mutant['target'])


    def is_xmt_mutation(self, node):
        """
        Check if a node is an XMT mutation check by examining its test condition.
        This helps us preserve XMT mutations when adding SDL mutations.
        """
        if isinstance(node, ast.If):
            try:
                test_source = astor.to_source(node.test)
                return 'is_mutant_enabled' in test_source and "'xmt_" in test_source
            except:
                return False
        return False


    def visit_FunctionDef(self, node):
        """
        Handle XMT mutations at the function level while preserving existing mutations.
        """
        # Check if this function already has an XMT mutation
        has_xmt = node.body and isinstance(node.body[0], ast.If) and self.is_xmt_mutation(node.body[0])
        
        # Visit children first to handle nested statements
        self.generic_visit(node)
        
        # Skip special methods
        if node.name.startswith('__') and node.name.endswith('__'):
            return node
            
        # Only add XMT mutation if function is targeted and doesn't already have one
        if not has_xmt and ('*' in self.xmt_targets or node.name in self.xmt_targets):
            mutation_id = f"xmt_{node.name}_{self.counters['xmt']}"
            self.counters['xmt'] += 1

            message = f'XMT: Removing body of function {node.name}'
            mutation_check = self._create_mutation_check(mutation_id, message)
            
            node.body.insert(0, mutation_check)
            logger.info(f"Added XMT mutation {mutation_id} to function {node.name}")
        
        return node


    def visit_If(self, node):
        """
        Handle SDL mutations for if statements while preserving XMT mutations.
        """
        self.nodes_visited['if'] += 1
        logger.debug(f"Visiting If node #{self.nodes_visited['if']}")

        # Skip if this is an XMT mutation check
        if self.is_xmt_mutation(node):
            logger.debug("Preserving XMT mutation check")
            return node

        # Visit children first
        node = self.generic_visit(node)
        
        # Add SDL mutation if targeted
        if 'if' in self.sdl_targets:
            mutation_id = f"sdl_if_{self.counters['if']}"
            self.counters['if'] += 1
            
            # Create context-aware mutation check
            plugin_ref = "self.plugin" if self.is_class_based else "plugin"
            mutation_check = ast.parse(
                f"if {plugin_ref}.is_mutant_enabled('{mutation_id}'):\n"
                f"    print('SDL: Skipping if statement')\n"
                f"    pass"
            ).body[0]
            
            logger.info(f"Added SDL mutation {mutation_id} to if statement")
            
            # Create if statement with mutated check and original as else
            mutated_if = ast.If(
                test=mutation_check.test,
                body=mutation_check.body,
                orelse=[node]
            )
            
            # Copy source location info for better error reporting
            ast.copy_location(mutated_if, node)
            return mutated_if
        
        return node


    def visit_For(self, node):
        """
        Handle SDL mutations for for loops while preserving other mutations.
        """
        self.nodes_visited['for'] += 1
        logger.debug(f"Visiting For node #{self.nodes_visited['for']}")

        # Visit children first to handle any nested mutations
        node = self.generic_visit(node)
        
        # Add SDL mutation if targeted
        if 'for' in self.sdl_targets:
            mutation_id = f"sdl_for_{self.counters['for']}"
            self.counters['for'] += 1
            
            # Create context-aware mutation check
            plugin_ref = "self.plugin" if self.is_class_based else "plugin"
            mutation_check = ast.parse(
                f"if {plugin_ref}.is_mutant_enabled('{mutation_id}'):\n"
                f"    print('SDL: Skipping for loop')\n"
                f"    pass"
            ).body[0]
            
            logger.info(f"Added SDL mutation {mutation_id} to for loop")
            
            # Create if statement wrapping the for loop
            mutated_for = ast.If(
                test=mutation_check.test,
                body=mutation_check.body,
                orelse=[node]
            )
            
            # Copy location information
            ast.copy_location(mutated_for, node)
            return mutated_for
        
        return node


def instrument_code(source_code, plugin_name, mutants):
    """
    Main instrumentation function that processes source code and adds mutations.
    
    Args:
        source_code: The source code to instrument
        plugin_name: Name of the mutation plugin
        mutants: Mutation configurations to apply
    
    Returns:
        str: The instrumented source code
    """
    logger.info("Starting code instrumentation")
    try:
        tree = ast.parse(source_code)
        
        # Create and run the mutant inserter
        inserter = MutantInserter(plugin_name, mutants)
        mutated_tree = inserter.visit(tree)
        
        # Fix locations in the AST after modifications
        ast.fix_missing_locations(mutated_tree)
        
        logger.info("Code instrumentation completed successfully")
        return astor.to_source(mutated_tree)
    except Exception as e:
        logger.error(f"Error during instrumentation: {str(e)}")
        raise

def run_instrumentation(input_file, mutant_file):
    """
    Orchestrates the complete instrumentation process for a file.
    
    Args:
        input_file: Path to the Python file to instrument
        mutant_file: Path to the mutation configuration file
    """
    try:
        # Load mutation configurations
        with open(mutant_file) as f:
            mutants_data = json.load(f)
            enabled_mutants = mutants_data.get('enabled_mutants', [])

        # Read source code
        with open(input_file, 'r') as f:
            source_code = f.read()

        # Special handling for test files
        is_test_file = Path(input_file).name.startswith('test_') or 'test' in Path(input_file).name
        if is_test_file:
            support_code = """
import sys
from pathlib import Path

support_dir = Path(__file__).parent / '.pypseudo'
if support_dir.exists():
    sys.path.insert(0, str(support_dir))

from mutation_support import MutationPlugin

@pytest.fixture
def plugin():
    plugin = MutationPlugin(str(Path(__file__).parent / '.pypseudo' / 'mutants.json'))
    plugin.load_mutants()
    return plugin
"""
            # Replace existing plugin fixture if present
            source_code = re.sub(
                r'@pytest\.fixture\s*\ndef\s+plugin\s*\(\s*\)[\s\S]*?return\s+plugin\s*\n',
                '',
                source_code
            )
            source_code = support_code + '\n' + source_code

        else:
            # Regular file instrumentation
            mutated_code = instrument_code(source_code, 'plugin', enabled_mutants)
            source_code = mutated_code

        # Write modified code
        with open(input_file, 'w') as f:
            f.write(source_code)

    except Exception as e:
        logger.error(f"Error during instrumentation: {e}")
        raise


def process_project(project_path, mutant_file):
    """
    Process an entire project for instrumentation
    
    Args:
        project_path: Path to the project
        mutant_file: Path to mutation configuration
    """
    try:
        working_dir = setup_project_environment(project_path)
        
        # Create __init__.py with proper imports
        init_content = """# Auto-generated initialization code
import os
import sys
from pathlib import Path

# Add .pypseudo directory to path
_support_dir = Path(__file__).parent / '.pypseudo'
if _support_dir.exists():
    sys.path.insert(0, str(_support_dir))

# Import mutation support and initialize plugin
from mutation_support import MutationPlugin, is_mutant_enabled
plugin = MutationPlugin(str(_support_dir / 'mutants.json'))
plugin.load_mutants()
"""
        
        # Create __init__.py in working directory
        init_file = working_dir / '__init__.py'
        with open(init_file, 'w') as f:
            f.write(init_content)
        
        # Copy support files
        with open(mutant_file) as f:
            mutants_config = json.load(f)
        copy_support_files(working_dir, mutants_config)
        
        # Process Python files
        for py_file in working_dir.glob("**/*.py"):
            if '.pypseudo' not in str(py_file) and py_file.name != '__init__.py':
                run_instrumentation(py_file, mutant_file)
                
        return working_dir
    except Exception as e:
        logger.error(f"Error processing project: {e}")
        raise


def restore_original(file_path, backup_path):
    """Restore the original code from backup - file-based restore"""
    try:
        if os.path.exists(backup_path):
            # Read backup content
            with open(backup_path, 'r') as backup_file:
                original_content = backup_file.read()
            
            # Write backup content to original file
            with open(file_path, 'w') as target_file:
                target_file.write(original_content)
            
            # Remove backup file after successful restore
            os.remove(backup_path)
            logger.info(f"Successfully restored {file_path}")
        else:
            logger.warning(f"No backup file found at {backup_path}")
    except Exception as e:
        logger.error(f"Error restoring original code: {e}")
        raise

def restore_project(project_path):
    """Restore a project to its original state"""
    try:
        # Get paths
        original_path = Path(project_path)
        working_dir = original_path.parent / f"{original_path.name}_pypseudo_work"
        
        if not working_dir.exists():
            logger.warning(f"No instrumented version found at {working_dir}")
            return
            
        # Clean up working directory
        shutil.rmtree(working_dir)
        logger.info(f"Successfully cleaned up instrumented project at {working_dir}")
        
    except Exception as e:
        logger.error(f"Error restoring project: {e}")
        raise