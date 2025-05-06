import ast
import astor
import json
import logging
import shutil
import os
import re
import subprocess
import sys
from pathlib import Path
from .utils import * 

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
        self.current_module = None  # Track current module name
        self.current_function = None  # Track current function
        self.process_mutants()
        logger.info(f"Initialized with targets - XMT: {self.xmt_targets}, SDL: {self.sdl_targets}")


    def _check_code_context(self, tree):
        """Check if code is class-based or procedural"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self.is_class_based = True
                break

    def _analyze_return_value(self, node):
        """Analyze function returns to determine appropriate mutation value"""
        return_stmts = []
        for n in ast.walk(node):
            if isinstance(n, ast.Return) and n.value:
                return_stmts.append(n.value)

        # If no return statements found, return None
        if not return_stmts:
            return ast.Constant(value=None)

        # Analyze first return statement's type
        first_return = return_stmts[0]
        
        if isinstance(first_return, ast.BinOp):
            # For arithmetic operations, return 0
            return ast.Num(n=0)
        elif isinstance(first_return, ast.List):
            # For list operations, return empty list
            return ast.List(elts=[], ctx=ast.Load())
        elif isinstance(first_return, ast.Dict):
            # For dict operations, return empty dict
            return ast.Dict(keys=[], values=[])
        elif isinstance(first_return, ast.Call):
            # For function calls, try to determine return type
            return ast.Num(n=0)  # Default to 0 for numeric operations
        elif isinstance(first_return, ast.Name):
            # For variable returns, default to None
            return ast.Constant(value=None)
        else:
            # Default case
            return ast.Constant(value=None)

    def _create_mutation_check(self, mutation_id, message):
        """Create appropriate mutation check based on context"""
        # Use the directly imported function
        return ast.parse(
            f"if is_mutant_enabled('{mutation_id}'):\n"
            f"    print('SDL: {message}')\n"
            f"    pass"
        ).body[0]
    
    
    def visit_Module(self, node):
        """Add necessary imports and plugin initialization for source files"""
        # Get module name from the AST
        self.current_module = getattr(node, 'module_name', 'unknown_module')
        logger.info(f"Processing module: {self.current_module}")
        
        self._check_code_context(node)
        
        # We no longer need to add imports here since they're handled in run_instrumentation
        return self.generic_visit(node)
    
                        
    def process_mutants(self):
        """Process mutation configuration"""
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
        """Handle XMT mutations at the function level"""
        # Set current function name
        self.current_function = node.name
        
        has_xmt = node.body and isinstance(node.body[0], ast.If) and self.is_xmt_mutation(node.body[0])
        
        self.generic_visit(node)
        
        if node.name.startswith('__') and node.name.endswith('__'):
            return node
                
        if not has_xmt and ('*' in self.xmt_targets or node.name in self.xmt_targets):
            # Include module name in the mutation ID (same format as SDL)
            # This is the key change - using self.current_module to include file info
            mutation_id = f"xmt_{node.name}_{self.current_module}_{self.counters['xmt']}"
            self.counters['xmt'] += 1

            return_value = self._analyze_return_value(node)

            # Use the global is_mutant_enabled function
            mutation_check = ast.If(
                test=ast.Call(
                    func=ast.Name(id='is_mutant_enabled', ctx=ast.Load()),
                    args=[ast.Str(s=mutation_id)],
                    keywords=[]
                ),
                body=[
                    ast.Expr(value=ast.Call(
                        func=ast.Name(id='print', ctx=ast.Load()),
                        args=[ast.Constant(value=f'XMT: Removing body of function {node.name} in {self.current_module}')],
                        keywords=[]
                    )),
                    ast.Return(value=return_value)
                ],
                orelse=[]
            )
            
            node.body.insert(0, mutation_check)
            logger.info(f"Added XMT mutation {mutation_id} to function {node.name}")
        
        return node
    
    def visit_If(self, node):
        """Handle SDL mutations for if statements"""
        self.nodes_visited['if'] += 1
        
        if self.is_xmt_mutation(node):
            return node

        node = self.generic_visit(node)
        
        if 'if' in self.sdl_targets:
            # Only add mutation check if we're inside a function
            if hasattr(self, 'current_function') and self.current_function:
                mutation_id = f"sdl_if_{self.current_module}_{self.current_function}_{self.counters['if']}"
                self.counters['if'] += 1
                
                mutation_check = self._create_mutation_check(mutation_id, "Skipping if statement")
                
                mutated_if = ast.If(
                    test=mutation_check.test,
                    body=mutation_check.body,
                    orelse=[node]
                )
                
                ast.copy_location(mutated_if, node)
                logger.info(f"Added SDL mutation {mutation_id} to if statement in {self.current_function}")
                return mutated_if
                
        return node

    def visit_For(self, node):
        """Handle SDL mutations for for loops"""
        self.nodes_visited['for'] += 1
        
        node = self.generic_visit(node)
        
        if 'for' in self.sdl_targets:
            # Only add mutation check if we're inside a function
            if hasattr(self, 'current_function') and self.current_function:
                mutation_id = f"sdl_for_{self.current_module}_{self.current_function}_{self.counters['for']}"
                self.counters['for'] += 1
                
                mutation_check = self._create_mutation_check(mutation_id, "Skipping for loop")
                
                mutated_for = ast.If(
                    test=mutation_check.test,
                    body=mutation_check.body,
                    orelse=[node]
                )
                
                ast.copy_location(mutated_for, node)
                logger.info(f"Added SDL mutation {mutation_id} to for loop in {self.current_function}")
                return mutated_for
                
        return node
    
class SafeMutantInserter(ast.NodeVisitor):
    """
    A specialized NodeVisitor for safe instrumentation of code with metaclasses.
    Only handles function-level (XMT) mutations to avoid metaclass conflicts.
    """
    
    def __init__(self, plugin_name, mutants):
        super().__init__()
        self.plugin_name = plugin_name
        self.mutants = mutants
        self.xmt_targets = set()
        self.counters = {'xmt': 1}
        self.current_function = None
        self.process_mutants()
        
    def process_mutants(self):
        """Process mutation configuration"""
        for mutant in self.mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                else:
                    self.xmt_targets.add(mutant['target'])
        
        logger.info(f"Initialized with targets - XMT: {self.xmt_targets}")
    
    def visit_Module(self, node):
        """Visit module but do not modify its structure"""
        self.generic_visit(node)
        return node
        
    def visit_FunctionDef(self, node):
        """Handle XMT mutations at the function level"""
        # Skip methods inside classes to avoid metaclass issues
        in_class = False
        for parent in ast.walk(node):
            if isinstance(parent, ast.ClassDef):
                in_class = True
                break
                
        if in_class:
            self.generic_visit(node)
            return node
            
        # Set current function name
        self.current_function = node.name
        
        # Check if this function already has an XMT mutation
        has_xmt = False
        if node.body and isinstance(node.body[0], ast.If):
            try:
                test_str = astor.to_source(node.body[0].test).strip()
                has_xmt = "is_mutant_enabled" in test_str and "xmt_" in test_str
            except:
                pass
        
        self.generic_visit(node)
        
        # Skip special methods
        if node.name.startswith('__') and node.name.endswith('__'):
            return node
                
        # If not already instrumented and matches targets
        if not has_xmt and ('*' in self.xmt_targets or node.name in self.xmt_targets):
            mutation_id = f"xmt_{node.name}_{self.counters['xmt']}"
            self.counters['xmt'] += 1

            # Determine appropriate return value
            return_value = None
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and hasattr(stmt, 'value') and stmt.value:
                    if isinstance(stmt.value, ast.Constant):
                        return_value = ast.Constant(value=None)
                    elif isinstance(stmt.value, ast.Num):
                        return_value = ast.Constant(value=0)
                    elif isinstance(stmt.value, ast.List):
                        return_value = ast.List(elts=[], ctx=ast.Load())
                    elif isinstance(stmt.value, ast.Dict):
                        return_value = ast.Dict(keys=[], values=[])
                    else:
                        return_value = ast.Constant(value=None)
                    break
            
            if not return_value:
                # No return found, use None
                return_value = ast.Constant(value=None)

            # Create the mutation check
            mutation_check = ast.If(
                test=ast.Call(
                    func=ast.Name(id='is_mutant_enabled', ctx=ast.Load()),
                    args=[ast.Str(s=mutation_id)],
                    keywords=[]
                ),
                body=[
                    ast.Expr(value=ast.Call(
                        func=ast.Name(id='print', ctx=ast.Load()),
                        args=[ast.Constant(value=f'XMT: Removing body of function {node.name}')],
                        keywords=[]
                    )),
                    ast.Return(value=return_value)
                ],
                orelse=[]
            )
            
            node.body.insert(0, mutation_check)
            logger.info(f"Added XMT mutation {mutation_id} to function {node.name}")
        
        return node

def instrument_code(source_code, plugin_name, mutants, module_name=None):
    """
    Main instrumentation function that processes source code and adds mutations.
    
    Args:
        source_code: The source code to instrument
        plugin_name: Name of the mutation plugin
        mutants: Mutation configurations to apply
        module_name: Name of the source file being processed
    
    Returns:
        str: The instrumented source code
    """
    logger.info("Starting code instrumentation")
    try:
        # Parse the source code into an AST
        tree = ast.parse(source_code)
        
        # Ensure module name is set
        if module_name:
            tree.module_name = module_name
        else:
            tree.module_name = "unknown_module"
            logger.warning("No module name provided, using 'unknown_module'")
        
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

def instrument_code_safe(source_code, plugin_name, mutants, module_name=None):
    """
    Safe instrumentation function for code with metaclasses.
    Only instruments function-level mutations to avoid metaclass conflicts.
    
    Args:
        source_code: The source code to instrument
        plugin_name: Name of the mutation plugin
        mutants: Mutation configurations to apply
        module_name: Name of the source file being processed
    
    Returns:
        str: The instrumented source code
    """
    logger.info("Starting safe code instrumentation")
    try:
        # Parse the source code into an AST
        tree = ast.parse(source_code)
        
        # Ensure module name is set
        if module_name:
            tree.module_name = module_name
        else:
            tree.module_name = "unknown_module"
            logger.warning("No module name provided, using 'unknown_module'")
        
        # Create a specialized mutant inserter for safe mode
        inserter = SafeMutantInserter(plugin_name, mutants)
        mutated_tree = inserter.visit(tree)
        
        # Fix locations in the AST after modifications
        ast.fix_missing_locations(mutated_tree)
        
        logger.info("Safe code instrumentation completed successfully")
        return astor.to_source(mutated_tree)
    except Exception as e:
        logger.error(f"Error during safe instrumentation: {str(e)}")
        raise

def run_instrumentation(input_file, mutant_file, safe_mode=False):
    """
    Orchestrates the complete instrumentation process for a file.
    """
    try:
        # Check if pypseudo_instrumentation is installed
        try:
            import pypseudo_instrumentation
        except ImportError:
            logger.error("ERROR: pypseudo_instrumentation package is not installed.")
            logger.error("Please install it with: poetry install -e ./pypseudo_instrumentation")
            return

        with open(mutant_file) as f:
            mutants_data = json.load(f)
            enabled_mutants = mutants_data.get('enabled_mutants', [])

        with open(input_file, 'r') as f:
            source_code = f.read()

        # Get module name from file path
        module_name = Path(input_file).stem
        # Get the actual filename for module identification
        filename = Path(input_file).name

        is_test_file = module_name.startswith('test_') or 'test' in module_name

        # First, remove any existing mutation support imports
        source_code = re.sub(
            r'import os.*?from pypseudo_instrumentation import.*?plugin\.load_mutants\(\).*?\n',
            '',
            source_code,
            flags=re.DOTALL | re.MULTILINE
        )
        
        # Also remove any individual imports of mutation_support
        source_code = re.sub(
            r'from pypseudo_instrumentation import.*?\n',
            '',
            source_code,
            flags=re.MULTILINE
        )

        if is_test_file:
            # For test files, simply add our fixture at the top and leave the rest intact
            # Create support code with package imports
            support_code = """import os
import sys
import pytest
from pathlib import Path

# Import from pypseudo_instrumentation package
from pypseudo_instrumentation import MutationPlugin

@pytest.fixture(scope='session')
def plugin():
    # Set path to config file
    config_path = str(Path(__file__).parent / '.pypseudo' / 'mutants.json')
    os.environ['PYPSEUDO_CONFIG_FILE'] = config_path
    
    # Create and initialize plugin
    plugin = MutationPlugin(config_path)
    plugin.load_mutants()
    return plugin

"""
            # Check if there's a preexisting plugin fixture that needs to be removed
            fixture_pattern = r'@pytest\.fixture(?:\([^)]*\))?\s*\ndef\s+plugin\s*\([^)]*\):.*?(?:return|yield).*?plugin.*?\n'
            source_code = re.sub(fixture_pattern, '', source_code, flags=re.DOTALL)
            
            # Add our support code at the beginning and leave the rest untouched
            source_code = support_code + source_code
        else:
            # For regular Python files
            # Add imports at the top
            import_header = """# PyPseudo instrumentation imports
import os
from pathlib import Path
from pypseudo_instrumentation import is_mutant_enabled

# Set environment variable for config file location
os.environ['PYPSEUDO_CONFIG_FILE'] = str(Path(__file__).parent / '.pypseudo' / 'mutants.json')

"""
            # Combine import header with original source
            source_code = import_header + source_code
            
            # Now instrument the code
            mutated_code = instrument_code(source_code, 'plugin', enabled_mutants, filename)
            source_code = mutated_code

        with open(input_file, 'w') as f:
            f.write(source_code)

    except Exception as e:
        logger.error(f"Error during instrumentation: {e}")
        raise

def process_project(project_path, mutant_file, safe_mode=False):
    """
    Process an entire project for instrumentation
    
    Args:
        project_path: Path to the project
        mutant_file: Path to mutation configuration
        safe_mode: Whether to use conservative instrumentation for complex projects
    """
    try:
        # Ensure required packages are installed
        try:
            logger.info("Installing required packages in working directory...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "pytest-json-report"],
                check=True,
                capture_output=True
            )
            logger.info("Required packages installed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install required packages: {e}")
            if hasattr(e, 'stdout'):
                logger.error(f"stdout: {e.stdout.decode() if e.stdout else ''}")
            if hasattr(e, 'stderr'):
                logger.error(f"stderr: {e.stderr.decode() if e.stderr else ''}")
            
        # Verify mutation_support.py is available
        current_dir = Path(__file__).parent
        project_root = current_dir.parent.parent
        mutation_support_path = project_root / 'pypseudo_instrumentation' / 'mutation_support.py'
        
        if not mutation_support_path.exists():
            logger.warning(f"mutation_support.py not found at {mutation_support_path}")
            # Try alternative locations
            for path in [
                current_dir.parent.parent.parent / 'pypseudo_instrumentation' / 'mutation_support.py',
                Path.cwd() / 'pypseudo_instrumentation' / 'mutation_support.py',
                Path.cwd().parent / 'pypseudo_instrumentation' / 'mutation_support.py'
            ]:
                if path.exists():
                    logger.info(f"Found mutation_support.py at {path}")
                    break
            else:
                logger.error("Could not find mutation_support.py in any expected location")
        else:
            logger.info(f"Found mutation_support.py at {mutation_support_path}")
            
        working_dir = setup_project_environment(project_path)
        
        # Create __init__.py with proper imports
        init_content = """# Auto-generated initialization code
import os
import sys
from pathlib import Path

# Set environment variable for config path
os.environ['PYPSEUDO_CONFIG_FILE'] = str(Path(__file__).parent / '.pypseudo' / 'mutants.json')
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
                run_instrumentation(py_file, mutant_file, safe_mode=safe_mode)
                
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