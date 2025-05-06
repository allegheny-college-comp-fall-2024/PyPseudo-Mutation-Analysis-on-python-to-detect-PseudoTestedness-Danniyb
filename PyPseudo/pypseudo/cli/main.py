import astor 
import pytest
import argparse
import logging
import shutil
import os
import json
import ast
from contextlib import contextmanager
import signal
from pathlib import Path
import datetime  
import sys
import tempfile
import subprocess
import re
import glob
from pypseudo.core.instrumentation import *  # Use full package path

# Add the parent directory to Python path to find pypseudo_instrumentation
current_file = Path(__file__)
parent_dir = current_file.parent.parent.parent  # Adjust depending on the actual structure
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    import pypseudo_instrumentation
except ImportError:
    print("ERROR: pypseudo_instrumentation package is not installed or not in Python path.")
    print(f"Current Python path: {sys.path}")
    print("Please install it with: poetry install -e ./pypseudo_instrumentation")
    sys.exit(1)

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

# Import from core
from core.mutation_plugin import MutationPlugin
from core.instrumentation import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MutationAnalyzer(ast.NodeVisitor):
    """
    Analyzes Python source code to identify existing mutations by traversing the AST.
    This analyzer specifically looks for instrumented mutation checks in the code.
    """
    
    def __init__(self):
        # Initialize data structures for tracking different types of mutations
        self.mutations = {
            'xmt': [],
            'sdl': {
                'for': [],
                'if': []
            }
        }
        # Track the current function being analyzed
        self.current_function = None
        # Debugging counters to help track traversal
        self.nodes_visited = {
            'functions': 0,
            'if_stmts': 0,
            'for_loops': 0
        }
        
    def extract_mutation_details(self, test_node):
        """
        Extracts mutation ID and type from an if statement's test condition.
        
        Args:
            test_node: The AST node containing the test condition
                
        Returns:
            tuple: (mutation_type, mutation_id, number) or (None, None, None) if not a mutation
        """
        try:
            # We need to handle the case where test_node might be None
            if not isinstance(test_node, ast.If):
                return None, None, None
                
            # Get the test condition's source
            test_str = astor.to_source(test_node.test).strip()
            
            # Check for mutation pattern - now checks both forms
            if not ('self.plugin.is_mutant_enabled' in test_str or 
                   'plugin.is_mutant_enabled' in test_str or
                   'is_mutant_enabled' in test_str):
                return None, None, None
            
            # Extract mutation ID - extract text between quotes
            start_quote = test_str.find("'") + 1
            end_quote = test_str.find("'", start_quote)
            
            if start_quote > 0 and end_quote > start_quote:
                mutation_id = test_str[start_quote:end_quote]
                # Extract mutation number for sorting
                number = int(mutation_id.split('_')[-1])
                
                if mutation_id.startswith('xmt_'):
                    return 'xmt', mutation_id, number
                elif mutation_id.startswith('sdl_'):
                    return 'sdl', mutation_id, number
                        
        except Exception as e:
            logger.debug(f"Error extracting mutation details: {str(e)}")
        return None, None, None


    def get_print_message(self, node):
        """
        Extracts the print message from a mutation block to help verify mutation type.
        
        Args:
            node: AST If node containing the mutation check
            
        Returns:
            str: The print message or None if not found
        """
        try:
            # Look for the print statement in the body
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if isinstance(call.func, ast.Name) and call.func.id == 'print':
                        return astor.to_source(call.args[0]).strip().strip("'\"")
        except:
            pass
        return None

    def visit_FunctionDef(self, node):
        """
        Visits function definitions to find XMT mutations.
        These are always at the start of the function body.
        """
        self.current_function = node.name
        
        # Check first statement for XMT mutation
        if node.body and isinstance(node.body[0], ast.If):
            mut_type, mut_id, number = self.extract_mutation_details(node.body[0])
            
            if mut_type == 'xmt':
                self.mutations['xmt'].append({
                    'id': mut_id,
                    'function': node.name,
                    'lineno': getattr(node.body[0], 'lineno', 0),
                    'number': number  # Add mutation number for sorting
                })
                logger.debug(f"Found XMT mutation {mut_id} in {node.name}")
        
        self.generic_visit(node)

    def visit_If(self, node):
        """
        Visits if statements to find SDL if-statement mutations.
        """
        mut_type, mut_id, number = self.extract_mutation_details(node)
        
        if mut_type == 'sdl' and mut_id.startswith('sdl_if_'):
            self.mutations['sdl']['if'].append({
                'id': mut_id,
                'function': self.current_function,
                'lineno': getattr(node, 'lineno', 0),
                'number': number  # Add mutation number for sorting
            })
            logger.debug(f"Found SDL if mutation {mut_id} in {self.current_function}")
                
        self.generic_visit(node)

    def visit_For(self, node):
        """
        Visits for loops to find SDL for-loop mutations.
        For loops with SDL mutations are typically wrapped in an if statement.
        """
        self.nodes_visited['for_loops'] += 1
        
        # Look at parent node if it exists
        parent = getattr(node, 'parent', None)
        if isinstance(parent, ast.If):
            mut_type, mut_id = self.extract_mutation_details(parent)
            
            if mut_type == 'sdl' and mut_id.startswith('sdl_for_'):
                # Verify it's an SDL mutation by checking the print message
                print_msg = self.get_print_message(parent)
                if print_msg and 'SDL: Skipping for loop' in print_msg:
                    self.mutations['sdl']['for'].append({
                        'id': mut_id,
                        'function': self.current_function,
                        'lineno': getattr(node, 'lineno', 0)
                    })
                    logger.debug(f"Found SDL for mutation {mut_id}")
                    
        self.generic_visit(node)

def analyze_code_for_mutations(file_path):
    """
    Analyzes a Python source file to find all existing mutations.
    
    Args:
        file_path: Path to the Python source file to analyze
        
    Returns:
        dict: Dictionary containing all found mutations
    """
    logger.info(f"Analyzing mutations in {file_path}")
    
    try:
        # Read the source code
        with open(file_path, 'r') as f:
            source_code = f.read()
            
        # Parse into AST
        tree = ast.parse(source_code)
        
        # Set up parent references
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                setattr(child, 'parent', parent)
                
        # Analyze the AST
        analyzer = MutationAnalyzer()
        analyzer.visit(tree)
        
        # Log traversal statistics
        logger.debug(f"Visited {analyzer.nodes_visited['functions']} functions")
        logger.debug(f"Visited {analyzer.nodes_visited['if_stmts']} if statements")
        logger.debug(f"Visited {analyzer.nodes_visited['for_loops']} for loops")
        
        return analyzer.mutations
        
    except Exception as e:
        logger.error(f"Error analyzing mutations in {file_path}: {str(e)}")
        raise

def collect_existing_mutants(working_dir):
    """
    Collect all existing mutants from the instrumented code.
    
    Args:
        working_dir: Path to the instrumented project
    
    Returns:
        dict: Mapping of mutants to test files
    """
    logger.info("Collecting existing mutants from instrumented code")
    
    # Find all Python files in the project
    py_files = glob.glob(str(working_dir) + "/**/*.py", recursive=True)
    
    # Pattern to match mutation IDs in code
    mutant_pattern = re.compile(r"is_mutant_enabled\(['\"](xmt_[^'\"]+|sdl_[^'\"]+)['\"]")
    
    # Collect all mutants
    all_mutants = set()
    file_to_mutants = {}
    
    for py_file in py_files:
        file_mutants = set()
        
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                
                # Find all mutant IDs in this file
                matches = mutant_pattern.findall(content)
                if matches:
                    file_mutants.update(matches)
                    all_mutants.update(matches)
                    
                    # Store mutants for this file
                    file_to_mutants[py_file] = list(file_mutants)
        except Exception as e:
            logger.debug(f"Error reading {py_file}: {e}")
    
    logger.info(f"Found {len(all_mutants)} mutants in the instrumented code")
    
    # Map test files to mutants
    test_to_mutants = {}
    
    # For each source file, find corresponding test files
    for source_file, mutants in file_to_mutants.items():
        if not mutants:
            continue
            
        # Get the module name without path and extension
        module_name = os.path.basename(source_file).replace(".py", "")
        
        # Find test files that might test this module
        test_files = glob.glob(str(working_dir) + f"/**/test_{module_name}.py", recursive=True)
        if not test_files:
            # Try with wildcard
            test_files = glob.glob(str(working_dir) + f"/**/test_*.py", recursive=True)
        
        for test_file in test_files:
            if test_file not in test_to_mutants:
                test_to_mutants[test_file] = []
            test_to_mutants[test_file].extend(mutants)
    
    # If no mapping found, use a simple approach
    if not test_to_mutants:
        logger.info("No test-to-mutant mapping found. Using all tests for all mutants.")
        test_files = glob.glob(str(working_dir) + "/**/test_*.py", recursive=True)
        for test_file in test_files:
            test_to_mutants[test_file] = list(all_mutants)
    
    # Remove duplicates in the lists
    for test_file in test_to_mutants:
        test_to_mutants[test_file] = list(set(test_to_mutants[test_file]))
    
    return {
        'mutants': list(all_mutants),
        'test_to_mutants': test_to_mutants,
        'mutant_coverage': {m: [t for t, ms in test_to_mutants.items() if m in ms] for m in all_mutants}
    }

def get_target_files(path):
    """
    Get list of Python files to analyze.
    
    Args:
        path: Path to file or directory
        
    Returns:
        list: List of Python file paths
    """
    path = Path(path)
    if path.is_file():
        return [path]
    elif path.is_dir():
        return list(path.glob("**/*.py"))
    return []

def list_available_mutations(args):
    """Lists all mutations currently present in the code."""
    # Determine target path
    original_path = Path(args.project_path)
    
    # Check if there's an instrumented version
    instrumented_path = original_path.parent / f"{original_path.name}_pypseudo_work"
    if not instrumented_path.exists():
        logger.error(f"No instrumented version found at {instrumented_path}. Run --instrument first.")
        return {}
        
    # Use the collect_existing_mutants function to scan the instrumented code
    logger.info(f"Scanning for mutations in {instrumented_path}")
    coverage_data = collect_existing_mutants(instrumented_path)
    
    # Group mutations by type
    xmt_mutations = []
    sdl_mutations = {'for': [], 'if': [], 'while': [], 'return': [], 'try': []}
    
    for mutant_id in coverage_data.get('mutants', []):
        if mutant_id.startswith('xmt_'):
            xmt_mutations.append({'id': mutant_id})
        elif mutant_id.startswith('sdl_'):
            parts = mutant_id.split('_')
            if len(parts) > 1:
                stmt_type = parts[1]
                if stmt_type in sdl_mutations:
                    sdl_mutations[stmt_type].append({'id': mutant_id})
    
    # Display results
    print("\nAvailable Mutations:")
    print("-" * 50)
    
    # Display XMT mutations
    print("\nXMT Mutations (Function Level):")
    if xmt_mutations:
        for mut in xmt_mutations:
            print(f"  - {mut['id']}")
    else:
        print("  None found")
    
    # Display SDL mutations
    print("\nSDL Mutations (Statement Level):")
    
    for stmt_type, mutations in sdl_mutations.items():
        print(f"\n  {stmt_type.upper()} Statements:")
        if mutations:
            for mut in mutations:
                print(f"    - {mut['id']}")
        else:
            print("    None found")
            
    # Create a structure similar to the original return value
    combined_mutations = {
        'xmt': xmt_mutations,
        'sdl': sdl_mutations
    }
        
    return combined_mutations

def run_single_mutation_test(args, mutation_id, pytest_args, working_dir=None):
    """
    Run tests with a single mutation enabled.
    
    Args:
        args: Command line arguments
        mutation_id: ID of mutation to test
        pytest_args: Additional pytest arguments
        working_dir: Path to working directory
    
    Returns:
        int: Test result (0 for pass, non-zero for fail)
    """
    try:
        # Make sure working_dir is a Path object
        if working_dir and not isinstance(working_dir, Path):
            working_dir = Path(working_dir)
            
        # Set up json-report for pytest
        json_report_file = working_dir / '.pypseudo' / 'pytest_report.json'
        os.makedirs(os.path.dirname(json_report_file), exist_ok=True)
        
        # Add json-report to pytest args if not already there
        json_report_args = []
        if not any('--json-report' in arg for arg in pytest_args):
            json_report_args.append('--json-report')
        if not any('--json-report-file' in arg for arg in pytest_args):
            json_report_args.append(f'--json-report-file={json_report_file}')
        
        # Create mutation config with only the specified mutation
        mut_type = 'xmt' if mutation_id.startswith('xmt_') else 'sdl'
        
        if mut_type == 'xmt':
            mutants_config = {
                'enable_mutation': True,
                'enabled_mutants': [{
                    'type': 'xmt',
                    'target': mutation_id
                }]
            }
        else:  # SDL
            parts = mutation_id.split('_')
            if len(parts) > 1:
                stmt_type = parts[1]
                mutants_config = {
                    'enable_mutation': True,
                    'enabled_mutants': [{
                        'type': 'sdl',
                        'target': [stmt_type]
                    }]
                }
            else:
                logger.warning(f"Invalid mutant ID format: {mutation_id}")
                return 1
        
        # Write temporary mutation config
        config_path = str(working_dir / '.pypseudo' / 'mutants.json')
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(mutants_config, f, indent=4)
            
        # Set environment variable for config path
        os.environ['PYPSEUDO_CONFIG_FILE'] = config_path
            
        # Run tests
        env = os.environ.copy()
        cmd = ["python", "-m", "pytest"] + pytest_args + json_report_args
        
        process = subprocess.run(
            cmd,
            cwd=working_dir,
            env=env,
            capture_output=True, 
            text=True
        )
        
        return process.returncode
        
    except Exception as e:
        logger.error(f"Error running mutation {mutation_id}: {e}")
        return 1

# def collect_coverage_mapping(working_dir, pytest_args=None):
#     """
#     Collect test coverage data to map tests to mutants.
    
#     Args:
#         working_dir: Path to the instrumented project
#         pytest_args: Additional pytest arguments
    
#     Returns:
#         dict: Coverage mapping with tests, mutants, and their relationships
#     """
#     logger.info("Setting up Python path for coverage collection")
    
#     # Make sure working_dir is a Path object
#     if not isinstance(working_dir, Path):
#         working_dir = Path(working_dir)
    
#     # Add the working directory to Python path to resolve imports
#     working_dir_str = str(working_dir)
    
#     try:
#         # Create a temporary directory for coverage files
#         with tempfile.TemporaryDirectory() as tmpdirname:
#             # Run pytest with coverage to get data
#             coverage_args = []
#             if pytest_args:
#                 coverage_args.extend(pytest_args)
            
#             # Add coverage arguments
#             coverage_args.extend([
#                 f"--cov={working_dir_str}", 
#                 f"--cov-report=json:{tmpdirname}/coverage.json"
#             ])
            
#             logger.info(f"Running tests with coverage: pytest {' '.join(coverage_args)}")
            
#             # Run pytest with coverage
#             try:
#                 test_env = os.environ.copy()
#                 test_env['PYTHONPATH'] = working_dir_str + os.pathsep + test_env.get('PYTHONPATH', '')
                
#                 process = subprocess.run(
#                     ["python", "-m", "pytest"] + coverage_args,
#                     cwd=working_dir,
#                     capture_output=True,
#                     text=True,
#                     env=test_env
#                 )
                
#                 logger.debug(f"Coverage command return code: {process.returncode}")
#                 logger.debug(f"Coverage command stdout: {process.stdout}")
#                 if process.stderr:
#                     logger.debug(f"Coverage command stderr: {process.stderr}")
#             except Exception as e:
#                 logger.error(f"Error running pytest with coverage: {e}")
            
#             # Check if coverage file was created
#             try:
#                 with open(f"{tmpdirname}/coverage.json", 'r') as f:
#                     coverage_data = json.load(f)
#                     logger.info("Successfully loaded coverage data")
#             except FileNotFoundError:
#                 logger.warning("Coverage file not found. Falling back to simple mapping.")
#                 coverage_data = None
            
#             # Pattern to match mutation IDs in code
#             mutant_pattern = re.compile(r"is_mutant_enabled\(['\"](xmt_[^'\"]+|sdl_[^'\"]+)['\"]")
            
#             # Find all mutants in the code
#             all_mutants = set()
#             file_to_mutants = {}
            
#             for py_file in working_dir.glob("**/*.py"):
#                 if py_file.name.startswith('__pycache__') or '.pypseudo' in str(py_file):
#                     continue
                    
#                 try:
#                     with open(py_file, 'r') as f:
#                         content = f.read()
                        
#                         # Find all mutant IDs in this file
#                         matches = mutant_pattern.findall(content)
#                         if matches:
#                             file_to_mutants[str(py_file)] = list(set(matches))
#                             all_mutants.update(matches)
#                 except Exception as e:
#                     logger.debug(f"Error reading {py_file}: {e}")
            
#             # Find test files
#             test_files = []
#             for py_file in working_dir.glob("**/*.py"):
#                 if py_file.name.startswith('test_') and py_file.name.endswith('.py'):
#                     test_files.append(str(py_file))
            
#             # Map test files to mutants based on coverage
#             test_to_mutants = {}
            
#             if coverage_data and 'files' in coverage_data:
#                 logger.info("Using coverage data to map tests to modules")
                
#                 # For each source file, find which test files cover it
#                 for file_path, file_data in coverage_data['files'].items():
#                     # Skip non-python files and test files
#                     if not file_path.endswith('.py') or 'test_' in file_path:
#                         continue
                        
#                     # Get mutants for this file
#                     mutants = file_to_mutants.get(file_path, [])
#                     if not mutants:
#                         continue
                    
#                     # Get the list of tests that cover this file
#                     if 'contexts' in file_data and file_data['contexts']:
#                         for context in file_data['contexts']:
#                             test_id = context.get('test_id')
#                             if test_id:
#                                 # Find the test file from the test_id
#                                 for test_file in test_files:
#                                     if test_id.startswith(test_file):
#                                         if test_file not in test_to_mutants:
#                                             test_to_mutants[test_file] = []
#                                         test_to_mutants[test_file].extend(mutants)
            
#             # If we couldn't get coverage data or no mapping was found, use a simple approach
#             if not test_to_mutants:
#                 logger.info("Using simple name-based mapping for coverage")
#                 for test_file in test_files:
#                     # Get the module name from the test file name
#                     test_module = os.path.basename(test_file).replace('test_', '').replace('.py', '')
                    
#                     # Find source files that might be tested by this test file
#                     for source_file, mutants in file_to_mutants.items():
#                         source_module = os.path.basename(source_file).replace('.py', '')
                        
#                         # If the module names match or the test module is in the source module name
#                         if source_module == test_module or test_module in source_module:
#                             if test_file not in test_to_mutants:
#                                 test_to_mutants[test_file] = []
#                             test_to_mutants[test_file].extend(mutants)
            
#             # If still no mapping, use all mutants for all tests
#             if not test_to_mutants:
#                 logger.info("No specific mapping found. Using all tests for all mutants.")
#                 for test_file in test_files:
#                     test_to_mutants[test_file] = list(all_mutants)
            
#             # Remove duplicates in the lists
#             for test_file in test_to_mutants:
#                 test_to_mutants[test_file] = list(set(test_to_mutants[test_file]))
            
#             # Create the reverse mapping (mutant -> tests)
#             mutant_to_tests = {}
#             for test_file, mutants in test_to_mutants.items():
#                 for mutant in mutants:
#                     if mutant not in mutant_to_tests:
#                         mutant_to_tests[mutant] = []
#                     mutant_to_tests[mutant].append(test_file)
            
#             # Create the final mapping
#             mapping = {
#                 'tests': list(test_to_mutants.keys()),
#                 'mutants': list(all_mutants),
#                 'test_to_mutants': test_to_mutants,
#                 'mutant_to_tests': mutant_to_tests,
#                 'metadata': {
#                     'timestamp': datetime.datetime.now().isoformat(),
#                     'source': 'coverage-based mapping' if coverage_data else 'name-based mapping'
#                 }
#             }
            
#             # Save the mapping for future use
#             try:
#                 os.makedirs(working_dir / '.pypseudo', exist_ok=True)
#                 with open(working_dir / '.pypseudo' / 'coverage_mapping.json', 'w') as f:
#                     json.dump(mapping, f, indent=2)
#             except Exception as e:
#                 logger.error(f"Error saving coverage mapping: {e}")
            
#             logger.info(f"Generated coverage mapping with {len(mapping['tests'])} tests and {len(mapping['mutants'])} mutants")
#             return mapping
            
#     except Exception as e:
#         logger.error(f"Error collecting coverage: {str(e)}")
#         # Return a minimal valid mapping structure
#         return {
#             'tests': [],
#             'mutants': [],
#             'test_to_mutants': {},
#             'mutant_to_tests': {}
#         }
    
# def run_test_with_mutants(args, test_file, mutant_ids, pytest_args, working_dir):
#     """
#     Run a specific test with multiple mutants enabled.
    
#     Args:
#         args: Command line arguments
#         test_file: Path to the test file
#         mutant_ids: List of mutant IDs to enable
#         pytest_args: Additional pytest arguments
#         working_dir: Path to the instrumented project
    
#     Returns:
#         dict: Results for each mutant
#     """
#     # Get the filename without path for logging
#     test_filename = os.path.basename(test_file)
    
#     # Make sure working_dir is a Path object
#     working_dir = Path(working_dir)
    
#     # Setup logging
#     logger.info(f"Testing {test_filename} with {len(mutant_ids)} mutants")
#     logger.info(f"Working directory: {working_dir}")
    
#     # Function to run a test with the same approach as run_single_mutation_test
#     def run_test(mutant_config, label):
#         try:
#             # Write to mutant file
#             mutant_file_path = working_dir / '.pypseudo' / 'mutants.json'
#             os.makedirs(os.path.dirname(mutant_file_path), exist_ok=True)
#             with open(mutant_file_path, 'w') as f:
#                 json.dump(mutant_config, f, indent=4)
            
#             # Set environment variable
#             os.environ['PYPSEUDO_CONFIG_FILE'] = str(mutant_file_path)
            
#             # Display config for debugging
#             logger.debug(f"{label} config: {json.dumps(mutant_config, indent=2)}")
            
#             # Instead of running a specific test file, just run all tests
#             # This matches what --single-mutant does
#             # Use os.system to exactly match the approach used in --run
#             cmd = "cd " + str(working_dir) + " && python -m pytest"
#             if pytest_args:
#                 cmd += " " + " ".join(pytest_args)
            
#             logger.debug(f"Running command: {cmd}")
            
#             # Run the test with the same approach used in run_tests
#             return_code = os.system(cmd)
#             passed = return_code == 0
            
#             return passed, "", ""  # We don't capture stdout/stderr with os.system
#         except Exception as e:
#             logger.error(f"Error running {label} test: {str(e)}")
#             return False, "", str(e)
    
#     # Create baseline config with no mutations enabled
#     baseline_config = {
#         'enable_mutation': False,
#         'enabled_mutants': []
#     }
    
#     # Run baseline test
#     logger.info(f"Running baseline test for {test_filename}")
#     baseline_passed, _, _ = run_test(baseline_config, "Baseline")
    
#     if not baseline_passed:
#         logger.warning(f"Baseline test failed for {test_filename}")
        
#         # Return results where we can't determine the status
#         results = {}
#         for mutant_id in mutant_ids:
#             results[mutant_id] = {
#                 'passed': None,  # None means we couldn't determine
#                 'test': {
#                     'file': test_filename,
#                     'test_cases': []
#                 },
#                 'type': 'xmt' if mutant_id.startswith('xmt_') else 'sdl',
#                 'error': "Baseline test failed"
#             }
#         return results
        
#     logger.info(f"Baseline test passed for {test_filename}, now running with mutations")
    
#     # Now run each mutant individually
#     results = {}
#     for mutant_id in mutant_ids:
#         # Create mutant config with just this mutant enabled
#         mut_type = 'xmt' if mutant_id.startswith('xmt_') else 'sdl'
        
#         if mut_type == 'xmt':
#             mutant_config = {
#                 'enable_mutation': True,
#                 'enabled_mutants': [{
#                     'type': 'xmt',
#                     'target': mutant_id
#                 }]
#             }
#         else:  # SDL
#             parts = mutant_id.split('_')
#             if len(parts) > 1:
#                 stmt_type = parts[1]
#                 mutant_config = {
#                     'enable_mutation': True,
#                     'enabled_mutants': [{
#                         'type': 'sdl',
#                         'target': [stmt_type]
#                     }]
#                 }
#             else:
#                 logger.warning(f"Skipping invalid mutant ID: {mutant_id}")
#                 continue
        
#         logger.info(f"Running test with mutant {mutant_id}")
        
#         # Run test with the mutant
#         mutant_passed, _, _ = run_test(mutant_config, f"Mutant {mutant_id}")
        
#         # In mutation testing, a SURVIVED mutant is one where tests PASS despite the mutation
#         # This indicates pseudo-tested code
#         results[mutant_id] = {
#             'passed': mutant_passed,  # If tests pass, the mutant survived
#             'test': {
#                 'file': test_filename,
#                 'test_cases': []  # We'll fill this later
#             },
#             'type': mut_type
#         }
    
#     # After running all mutants, try to extract test case names from a successful run
#     try:
#         # Run pytest with --collect-only to get test names
#         cmd = f"cd {working_dir} && python -m pytest --collect-only -v {test_file}"
#         process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
#         # Extract test case names from output
#         test_cases = []
#         pattern = re.compile(r'::(\w+)(\[.*?\])?\s')
#         for line in process.stdout.split('\n'):
#             match = pattern.search(line)
#             if match and test_filename in line:
#                 test_case = match.group(1)
#                 test_cases.append(test_case)
        
#         # Add test case names to all results
#         for result in results.values():
#             result['test']['test_cases'] = test_cases
            
#     except Exception as e:
#         logger.warning(f"Error extracting test cases: {str(e)}")
    
#     return results


def run_tests_with_config(config: dict, description: str, working_dir: Path) -> tuple[dict, int]:
    """Run tests with a specific mutation configuration"""
    # Convert working_dir to absolute path
    working_dir = working_dir.resolve()
    
    # Write config to file
    config_file = working_dir / '.pypseudo' / 'mutants.json'
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    # Set environment variable to point to config file
    os.environ['PYPSEUDO_CONFIG_FILE'] = str(config_file)
    
    # Ensure the report directory exists
    report_dir = working_dir / '.pypseudo'
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / 'pytest_report.json'
    
    # Run pytest with JSON report and additional options for better error reporting
    cmd = [
        'python', '-m', 'pytest',  # Use python -m pytest to ensure correct environment
        '--json-report',
        f'--json-report-file={report_file}',
        '--json-report-omit=log,props,logfile',
        '--json-report-indent=2',
        '--capture=no',  # Ensure we capture all output
        '-v',  # Verbose output
        '--tb=short',  # Shorter traceback format
        '--disable-warnings',  # Disable pytest warnings
        '--import-mode=importlib',  # Use importlib mode for better import handling
        str(working_dir)  # Add working directory as the test path
    ]
    
    logger.info(f"\nRunning {description}...")
    logger.debug(f"Command: {' '.join(cmd)}")
    logger.debug(f"Working directory: {working_dir}")
    
    # Create a clean environment for pytest
    env = os.environ.copy()
    env['PYTHONPATH'] = str(working_dir) + os.pathsep + env.get('PYTHONPATH', '')
    
    # Run pytest with the command
    try:
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            env=env
        )
        
        # Log output for debugging
        logger.debug(f"Exit code: {result.returncode}")
        if result.stdout:
            logger.debug("stdout: %s", result.stdout)
        if result.stderr:
            logger.debug("stderr: %s", result.stderr)
        
        # Read and parse the JSON report
        try:
            with open(report_file, 'r') as f:
                report = json.load(f)
                
            # Log test summary
            total = report.get('total', 0)
            passed = report.get('passed', 0)
            failed = report.get('failed', 0)
            error = report.get('error', 0)
            skipped = report.get('skipped', 0)
            
            logger.info(f"Test Summary: {total} total, {passed} passed, {failed} failed, {error} error, {skipped} skipped")
            
        except Exception as e:
            logger.error("Error reading JSON report: %s", e)
            logger.error("Report file path: %s", report_file)
            logger.error("Current working directory: %s", os.getcwd())
            logger.error("Working directory: %s", working_dir)
            raise
            
        return report, result.returncode
        
    except subprocess.CalledProcessError as e:
        logger.error("Pytest command failed with exit code %d", e.returncode)
        logger.error("stdout: %s", e.stdout)
        logger.error("stderr: %s", e.stderr)
        raise
    except Exception as e:
        logger.error("Unexpected error running pytest: %s", str(e))
        raise

def install_project_dependencies(working_dir: Path) -> bool:
    """
    Install project dependencies using Poetry.
    
    Args:
        working_dir: Path to the project directory
        
    Returns:
        bool: True if installation was successful, False otherwise
    """
    try:
        logger.info("Installing project dependencies...")
        # Run poetry install in the project directory
        result = subprocess.run(
            ['poetry', 'install'],
            cwd=working_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error("Failed to install dependencies:")
            logger.error(result.stderr)
            return False
            
        logger.info("Successfully installed project dependencies")
        return True
        
    except Exception as e:
        logger.error("Error installing dependencies: %s", str(e))
        return False

def run_all_mutations(args: argparse.Namespace) -> None:
    """Run all mutations and generate a report."""
    # Convert project path to absolute path and get working directory
    project_path = Path(args.project_path).resolve()
    working_dir = project_path.parent / f"{project_path.name}_pypseudo_work"
    
    logger.info(f"Running mutations in {working_dir}")
    
    # Verify working directory exists
    if not working_dir.exists():
        logger.error(f"No instrumented version found at {working_dir}. Run --instrument first.")
        return
    
    # Get baseline test results
    logger.info("Running baseline tests...")
    baseline_report, baseline_exit = run_tests_with_config(
        {"enable_mutation": False},
        "Baseline",
        working_dir
    )
    
    if baseline_exit != 0:
        logger.error("Baseline tests failed")
        return
    
    # Store baseline test outcomes
    baseline_test_outcomes = {}
    for test in baseline_report.get('tests', []):
        if isinstance(test, dict):
            test_id = test.get('nodeid', '')
            if test_id:
                baseline_test_outcomes[test_id] = {
                    'passed': test.get('outcome', '') == 'passed',
                    'outcome': test.get('outcome', '')
                }
    
    # Get all mutants from the instrumented code
    logger.info("Collecting mutants from instrumented code...")
    mutants_data = collect_existing_mutants(working_dir)
    if not mutants_data or not mutants_data.get('mutants'):
        logger.error("No mutants found in instrumented code")
        return
    
    all_mutants = mutants_data['mutants']
    logger.info(f"Found {len(all_mutants)} mutants")
    
    # Run each mutant individually
    results = []
    for mutant_id in all_mutants:
        logger.info(f"\nTesting mutant: {mutant_id}")
        
        # Create mutant config with only this mutant enabled
        mut_type = 'xmt' if mutant_id.startswith('xmt_') else 'sdl'
        if mut_type == 'xmt':
            mutant_config = {
                "enable_mutation": True,
                "enabled_mutants": [{
                    "type": "xmt",
                    "target": mutant_id
                }]
            }
        else:  # SDL
            parts = mutant_id.split('_')
            if len(parts) > 1:
                stmt_type = parts[1]
                mutant_config = {
                    "enable_mutation": True,
                    "enabled_mutants": [{
                        "type": "sdl",
                        "target": [stmt_type]
                    }]
                }
            else:
                logger.warning(f"Invalid mutant ID format: {mutant_id}")
                continue
        
        # Run tests with this mutant
        mutant_report, mutant_exit = run_tests_with_config(
            mutant_config,
            f"Mutant {mutant_id}",
            working_dir
        )
        
        # Process test results
        killed = False
        killed_by = []
        
        # A mutant is killed if any test fails or if the test run exits with non-zero code
        if mutant_exit != 0:
            killed = True
            logger.info(f"Mutant {mutant_id} killed by test failures")
        
        # Check for test failures
        for test in mutant_report.get('tests', []):
            if isinstance(test, dict):
                test_id = test.get('nodeid', '')
                mutant_outcome = test.get('outcome', '')
                
                # If any test fails or errors, the mutant is killed
                if mutant_outcome in ['failed', 'error']:
                    killed = True
                    logger.info(f"Mutant {mutant_id} killed by test: {test_id}")
                    
                    # Get test failure details
                    details = ''
                    if isinstance(test.get('call'), dict):
                        call_outcome = test['call'].get('outcome', {})
                        if isinstance(call_outcome, dict):
                            details = call_outcome.get('longrepr', '')
                    elif isinstance(test.get('setup'), dict):
                        setup_outcome = test['setup'].get('outcome', {})
                        if isinstance(setup_outcome, dict):
                            details = setup_outcome.get('longrepr', '')
                    
                    killed_by.append({
                        'test_id': test_id,
                        'outcome': mutant_outcome,
                        'details': details
                    })
                    break  # Stop after first failure
        
        # Record results
        results.append({
            'mutant_id': mutant_id,
            'killed': killed,
            'killed_by': killed_by,
            'total_tests': mutant_report.get('total', 0),
            'passed_tests': mutant_report.get('passed', 0),
            'failed_tests': mutant_report.get('failed', 0),
            'error_tests': mutant_report.get('error', 0)
        })
        
        # If mutant was killed, we can move to the next one
        if killed:
            continue
    
    # Generate and display report
    report = generate_mutation_report(results)
    print("\nMutation Testing Report:")
    print("=" * 50)
    print(f"Total Mutants: {len(results)}")
    print(f"Killed Mutants: {sum(1 for r in results if r['killed'])}")
    print(f"Survived Mutants: {sum(1 for r in results if not r['killed'])}")
    print("\nDetailed Results:")
    print("-" * 50)
    
    for result in results:
        status = "KILLED" if result['killed'] else "SURVIVED"
        print(f"\nMutant: {result['mutant_id']}")
        print(f"Status: {status}")
        if result['killed']:
            print("Killed by:")
            for kill in result['killed_by']:
                print(f"  - Test: {kill['test_id']}")
                print(f"    Outcome: {kill['outcome']}")
                if kill['details']:
                    print(f"    Details: {kill['details']}")
        print(f"Test Summary: {result['passed_tests']} passed, {result['failed_tests']} failed, {result['error_tests']} errors")

def setup_logging(verbose=False):
    """
    Set up logging configuration.
    
    Args:
        verbose: Whether to enable debug logging
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Clear existing handlers to avoid duplicate messages
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler for standard output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Create a formatter with timestamp
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add handlers to the root logger
    root_logger.addHandler(console_handler)
    
    # Create a file handler for debug logs
    file_handler = logging.FileHandler('pypseudo.log', mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Return the logger for convenience
    return root_logger


def generate_mutation_report(results):
    """Generate a detailed report of mutation testing results"""
    report = {
        'summary': {
            'total_mutations': len(results),
            'killed_mutations': sum(1 for r in results if r['killed']),
            'survived_mutations': sum(1 for r in results if not r['killed'])
        },
        'mutations': results
    }
    
    # Write detailed report
    with open('mutation_report.json', 'w') as f:
        json.dump(report, f, indent=4)
    
    # Print summary
    print("\nMutation Testing Report")
    print("-" * 50)
    print(f"Total Mutations: {report['summary']['total_mutations']}")
    print(f"Killed Mutations: {report['summary']['killed_mutations']}")
    print(f"Survived Mutations: {report['summary']['survived_mutations']}")
    print("\nDetailed results written to mutation_report.json")



class TimeoutException(Exception):
    """Exception raised when a timeout occurs"""
    pass

@contextmanager
def timeout(seconds):
    """Context manager for timing out operations"""
    def handler(signum, frame):
        raise TimeoutException()
    
    # Set the timeout handler
    previous_handler = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_tests(mutant_file, pytest_args, target_path=None):
    """Run tests with the mutation plugin"""
    try:
        # Get the instrumented directory path
        working_dir = None
        if target_path:
            original_path = Path(target_path)
            # Check if path already contains _pypseudo_work
            if "_pypseudo_work" in str(original_path):
                working_dir = original_path
            else:
                working_dir = original_path.parent / f"{original_path.name}_pypseudo_work"
                
            if not working_dir.exists():
                raise ValueError(f"No instrumented version found at {working_dir}. Run --instrument first.")

        # Update mutation config in work directory
        work_mutants_file = working_dir / '.pypseudo' / 'mutants.json'
        with open(mutant_file, 'r') as f:
            current_config = json.load(f)
            
        # Write updated config to work directory
        with open(work_mutants_file, 'w') as f:
            json.dump(current_config, f, indent=2)
            
        # Set environment variable for config path
        os.environ['PYPSEUDO_CONFIG_FILE'] = str(work_mutants_file)

        plugin = MutationPlugin(str(work_mutants_file))
        plugin.load_mutants()
        
        with timeout(30):  # Add 30 second timeout
            if working_dir:
                # Add working directory to Python path
                sys.path.insert(0, str(working_dir))
                
                # Update pytest args to point to working directory
                test_dir = working_dir
                if test_dir not in pytest_args:
                    pytest_args = [str(test_dir)] + pytest_args
            
            result = pytest.main(pytest_args, plugins=[plugin])
            return result
            
    except TimeoutException:
        logger.error("Test execution timed out")
        return 1
    except Exception as e:
        logger.error(f"Error during test execution: {str(e)}")
        return 1

def filter_mutations(mutants_data, args):
    """Filter mutations based on command line arguments"""
    print("\n=== Debug: Filter Mutations Start ===")
    print(f"Initial mutants_data: {json.dumps(mutants_data, indent=2)}")

    # For instrumentation phase
    if args.instrument:
        filtered_mutants = {
            "enable_mutation": True,
            "enabled_mutants": []
        }
        
        # Add XMT mutations if flag is set
        if args.xmt:
            filtered_mutants["enabled_mutants"].append({
                "type": "xmt",
                "target": "*"
            })
            
        # Add SDL mutations if flag is set
        if args.sdl:
            filtered_mutants["enabled_mutants"].append({
                "type": "sdl",
                "target": ["for", "if", "while", "return", "try"]
            })
            
        return filtered_mutants
        
    # For test running phase
    filtered_mutants = {
        "enable_mutation": False,  # Default to disabled
        "enabled_mutants": []
    }

    # Handle disable mutations flag
    if args.disable_mutations:
        return filtered_mutants

    # Handle enable mutations
    if args.enable_mutations or args.xmt or args.sdl:
        filtered_mutants["enable_mutation"] = True

        # Handle single mutant case
        if args.single_mutant:
            parts = args.single_mutant.split('_')
            mut_type = parts[0]
            
            if mut_type == "xmt":
                filtered_mutants["enabled_mutants"].append({
                    "type": "xmt",
                    "target": args.single_mutant  # Keep full mutation ID
                })
            elif mut_type == "sdl":
                filtered_mutants["enabled_mutants"].append({
                    "type": "sdl",
                    "target": [parts[1]]
                })
            return filtered_mutants

        # Handle XMT/SDL flags
        if args.xmt:
            filtered_mutants["enabled_mutants"].append({
                "type": "xmt",
                "target": "*"
            })
            
        if args.sdl:
            filtered_mutants["enabled_mutants"].append({
                "type": "sdl",
                "target": ["for", "if", "while", "return", "try"]
            })
            
    return filtered_mutants

def main():
    parser = argparse.ArgumentParser(description='Run mutation testing with pytest.')
    
    # Operation mode group
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--instrument', action='store_true',
                          help='Only instrument code with mutations')
    mode_group.add_argument('--run', action='store_true',
                          help='Run mutation testing')
    mode_group.add_argument('--restore', action='store_true',
                          help='Restore code to original state')
    mode_group.add_argument('--list-mutations', action='store_true',
                          help='List all available mutation points in the code')
    mode_group.add_argument('--run-all-mutations', action='store_true',
                          help='Run tests with each mutation one by one')
    
    # Project path and mutation flags
    parser.add_argument('--project-path', required=True,
                       help='Path to the project to analyze')
    parser.add_argument('--safe-mode', action='store_true',
                   help='Use conservative instrumentation for complex libraries with metaclasses')
    parser.add_argument('--xmt', action='store_true',
                       help='Use extreme mutation testing only')
    parser.add_argument('--sdl', action='store_true',
                       help='Use statement deletion testing only')
    parser.add_argument('--enable-mutations', action='store_true',
                       help='Enable mutations during test run')
    parser.add_argument('--disable-mutations', action='store_true',
                       help='Disable all mutations during test run')
    parser.add_argument('--single-mutant', 
                       help='Run tests with only specified mutant enabled (e.g., "xmt_add_1" or "sdl_for_1")')
    
    # Reporting arguments
    parser.add_argument('--mutant-file', required=False, help='Path to the mutant file')
    parser.add_argument('--json-report', action='store_true', help='Generate a JSON report')
    parser.add_argument('--json-report-file', help='Path to save the JSON report')
    parser.add_argument('--cov', help='Module or directory to measure coverage for')
    parser.add_argument('--cov-report', help='Coverage report format (e.g., json, term, etc.)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose debug output')

    args = parser.parse_args()

    # Set up logging
    logger = setup_logging(args.verbose)

    # Check if pypseudo_instrumentation is installed
    try:
        import pypseudo_instrumentation
    except ImportError:
        logger.error("ERROR: pypseudo_instrumentation package is not installed.")
        logger.error("Please install it with: pip install -e ./pypseudo_instrumentation")
        return

    # Set default mutant file if not provided
    # Handle default mutant file path
    if not args.mutant_file:
        project_path = Path(args.project_path)
        # Try in project config directory
        default_mutant_file = project_path / 'config' / 'mutants.json'
        if default_mutant_file.exists():
            args.mutant_file = str(default_mutant_file)
        else:
            # Fall back to the default mutants.json in the tool's directory
            default_mutant_file = Path(__file__).parent.parent / 'config' / 'mutants.json'
            if default_mutant_file.exists():
                args.mutant_file = str(default_mutant_file)
            else:
                # Last resort - use the one in the current directory
                args.mutant_file = 'mutants.json'
        print(f"Using default mutant file: {args.mutant_file}")
    
    # Prepare pytest arguments
    pytest_args = []
    if args.json_report:
        pytest_args.append('--json-report')
    if args.json_report_file:
        pytest_args.extend(['--json-report-file', args.json_report_file])
    if args.cov:
        pytest_args.extend(['--cov', args.cov])
    if args.cov_report:
        pytest_args.extend(['--cov-report', args.cov_report])

    # Set up paths
    project_path = Path(args.project_path)
    working_dir = project_path.parent / f"{project_path.name}_pypseudo_work"
    original_mutants = None

    try:
        if args.restore:
            logger.info(f"Restoring project {project_path}")
            restore_project(project_path)
            return

        if args.list_mutations:
            if working_dir.exists():
                list_available_mutations(args)
            else:
                logger.error("No instrumented version found. Run --instrument first.")
            return

        # Load and filter mutations
        with open(args.mutant_file, 'r') as f:
            mutants_data = json.load(f)
            original_mutants = json.loads(json.dumps(mutants_data))  # Deep copy

        filtered_mutants = filter_mutations(mutants_data, args)
        
        # Write filtered mutations
        with open(args.mutant_file, 'w') as f:
            json.dump(filtered_mutants, f, indent=4)

        if args.instrument:
            logger.info("Running instrumentation...")
            working_dir = process_project(project_path, args.mutant_file, safe_mode=args.safe_mode)
            if working_dir:
                logger.info("Instrumentation complete")
            else:
                logger.error("Instrumentation failed")
            return

        if args.run:
            if not working_dir.exists():
                logger.error("No instrumented version found. Run --instrument first.")
                return
                
            logger.info("Running tests...")
            # Set environment variable for config path
            os.environ['PYPSEUDO_CONFIG_FILE'] = str(working_dir / '.pypseudo' / 'mutants.json')
            
            result = run_tests(args.mutant_file, pytest_args, working_dir)

            if result == 0:
                logger.info("All tests passed")
            else:
                logger.warning("Some tests failed")
            return

        if args.run_all_mutations:
            if not working_dir.exists():
                logger.error("No instrumented version found. Run --instrument first.")
                return
                    
            logger.info("Running all mutations grouped by test coverage...")
            run_all_mutations(args)
            return

    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
        # Clean up working directory on error if it exists
        if working_dir.exists():
            logger.info("Cleaning up working directory after error...")
            shutil.rmtree(working_dir)
        raise

    finally:
        # Restore original mutants configuration
        if original_mutants is not None:
            with open(args.mutant_file, 'w') as f:
                json.dump(original_mutants, f, indent=4)

if __name__ == "__main__":
    main()