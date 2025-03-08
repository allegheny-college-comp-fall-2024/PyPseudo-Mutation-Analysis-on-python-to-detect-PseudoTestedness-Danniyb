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
    target_path = args.project_path if args.project_path else 'simplePro/newtest.py'
    
    # Get list of files to analyze
    files_to_analyze = get_target_files(target_path)
    
    # Initialize combined mutations dict
    combined_mutations = {
        'xmt': [],
        'sdl': {
            'for': [],
            'if': []
        }
    }
    
    # Analyze each file
    for file_path in files_to_analyze:
        if '.pypseudo' not in str(file_path):  # Skip support files
            try:
                file_mutations = analyze_code_for_mutations(file_path)
                # Add file path to mutation info
                for mut in file_mutations['xmt']:
                    mut['file'] = str(file_path)
                for mut in file_mutations['sdl']['for']:
                    mut['file'] = str(file_path)
                for mut in file_mutations['sdl']['if']:
                    mut['file'] = str(file_path)
                
                # Combine mutations
                combined_mutations['xmt'].extend(file_mutations['xmt'])
                combined_mutations['sdl']['for'].extend(file_mutations['sdl']['for'])
                combined_mutations['sdl']['if'].extend(file_mutations['sdl']['if'])
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                continue
    
    # Display results
    print("\nAvailable Mutations:")
    print("-" * 50)
    
    # Display XMT mutations
    print("\nXMT Mutations (Function Level):")
    if combined_mutations['xmt']:
        sorted_xmt = sorted(combined_mutations['xmt'], 
                          key=lambda x: (x['file'], x['function'], x.get('number', 0)))
        for mut in sorted_xmt:
            print(f"  - {mut['id']} in {mut['function']} ({mut['file']})")
    else:
        print("  None found")
    
    # Display SDL mutations
    print("\nSDL Mutations (Statement Level):")
    
    # For loop mutations
    print("\n  FOR Statements:")
    if combined_mutations['sdl']['for']:
        sorted_for = sorted(combined_mutations['sdl']['for'], 
                          key=lambda x: (x['file'], x['function'], x['lineno']))
        for mut in sorted_for:
            print(f"    - {mut['id']} in {mut['function']} at line {mut['lineno']} ({mut['file']})")
    else:
        print("    None found")
    
    # If statement mutations
    print("\n  IF Statements:")
    if combined_mutations['sdl']['if']:
        sorted_if = sorted(combined_mutations['sdl']['if'], 
                         key=lambda x: (x['file'], x['function'], x['lineno']))
        for mut in sorted_if:
            print(f"    - {mut['id']} in {mut['function']} at line {mut['lineno']} ({mut['file']})")
    else:
        print("    None found")
        
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
        # Create mutation config with only the specified mutation
        mutants_config = {
            'enable_mutation': True,
            'enabled_mutants': [{'type': mutation_id.split('_')[0], 'target': mutation_id}]
        }
        
        # Write temporary mutation config
        with open(args.mutant_file, 'w') as f:
            json.dump(mutants_config, f, indent=4)
            
        # Set environment variable for config path
        if working_dir:
            config_path = str(working_dir / '.pypseudo' / 'mutants.json')
            os.environ['PYPSEUDO_CONFIG_FILE'] = config_path
            
        # Run tests
        return run_tests(args.mutant_file, pytest_args, working_dir)
        
    except Exception as e:
        logger.error(f"Error running mutation {mutation_id}: {e}")
        return 1

def collect_coverage_mapping(working_dir, pytest_args):
    """
    Collect test coverage data to map tests to mutants.
    
    Returns:
        dict: Coverage mapping with tests, mutants, and their relationships
    """
    logger.info("Setting up Python path for coverage collection")
    
    # Add the working directory to Python path to resolve imports
    sys.path.insert(0, str(working_dir))
    
    try:
        # Create a temporary mutant file that enables coverage collection
        os.makedirs(working_dir / '.pypseudo', exist_ok=True)
        temp_mutant_file = working_dir / '.pypseudo' / 'coverage_mutants.json'
        coverage_config = {
            "enable_mutation": False,  # Initially disable mutations
            "collect_coverage": True,  # Special flag for coverage collection
            "enabled_mutants": []
        }
        
        with open(temp_mutant_file, 'w') as f:
            json.dump(coverage_config, f, indent=2)
        
        # Set environment variable to use our coverage config
        os.environ['PYPSEUDO_CONFIG_FILE'] = str(temp_mutant_file)
        
        # Use a simpler approach - run pytest with coverage plugin
        try:
            # Try to get test coverage using pytest-cov
            logger.info("Collecting coverage information using pytest-cov")
            
            # Create a temporary directory for coverage files
            with tempfile.TemporaryDirectory() as tmpdirname:
                # Run pytest with coverage to get data
                cov_args = list(pytest_args) + [
                    f"--cov={working_dir}", 
                    f"--cov-report=json:{tmpdirname}/coverage.json"
                ]
                
                pytest.main(cov_args)
                
                # Check if coverage file was created
                try:
                    with open(f"{tmpdirname}/coverage.json", 'r') as f:
                        coverage_data = json.load(f)
                except FileNotFoundError:
                    logger.warning("Coverage file not found. Falling back to directory mapping.")
                    coverage_data = None
                
                # Map test files to source files based on coverage data
                test_to_source = {}
                source_to_test = {}
                
                if coverage_data:
                    # Process the coverage data to map tests to source files
                    for file_path, file_data in coverage_data.get('files', {}).items():
                        # Skip non-python files and test files
                        if not file_path.endswith('.py') or 'test_' in file_path:
                            continue
                        
                        # For each source file, find corresponding test files
                        module_name = os.path.basename(file_path).replace('.py', '')
                        for test_file in working_dir.glob(f"**/test_{module_name}.py"):
                            test_id = str(test_file)
                            if test_id not in test_to_source:
                                test_to_source[test_id] = []
                            test_to_source[test_id].append(file_path)
                            
                            if file_path not in source_to_test:
                                source_to_test[file_path] = []
                            source_to_test[file_path].append(test_id)
                else:
                    # Fallback to simple name-based mapping
                    logger.info("Using simple name-based mapping for coverage")
                    for test_file in working_dir.glob("**/test_*.py"):
                        test_id = str(test_file)
                        module_name = test_file.stem.replace("test_", "")
                        
                        # Find corresponding source files by name
                        for source_file in working_dir.glob(f"**/{module_name}.py"):
                            if source_file.is_file():
                                if test_id not in test_to_source:
                                    test_to_source[test_id] = []
                                test_to_source[test_id].append(str(source_file))
                                
                                if str(source_file) not in source_to_test:
                                    source_to_test[str(source_file)] = []
                                source_to_test[str(source_file)].append(test_id)
                
                # Generate synthetic mutant IDs for each source file
                mutant_coverage = {}
                test_coverage = {}
                all_mutants = []
                
                for source_file, tests in source_to_test.items():
                    # Generate up to 10 synthetic mutants per file
                    for i in range(1, 11):
                        mutant_id = f"xmt_{source_file}_{i}"
                        all_mutants.append(mutant_id)
                        
                        mutant_coverage[mutant_id] = tests
                        
                        for test in tests:
                            if test not in test_coverage:
                                test_coverage[test] = []
                            test_coverage[test].append(mutant_id)
                
                # Save the coverage mapping
                mapping = {
                    'tests': list(test_coverage.keys()),
                    'mutants': all_mutants,
                    'test_coverage': test_coverage,
                    'mutant_coverage': mutant_coverage,
                    'metadata': {
                        'timestamp': datetime.datetime.now().isoformat(),
                        'source': 'directory-based mapping'
                    }
                }
                
                with open(working_dir / '.pypseudo' / 'coverage_data.json', 'w') as f:
                    json.dump(mapping, f, indent=2)
                
                logger.info(f"Generated coverage mapping with {len(mapping['tests'])} tests and {len(mapping['mutants'])} potential mutants")
                return mapping
        except ImportError:
            logger.warning("pytest-cov not available. Using directory-based mapping.")
        
        # If pytest-cov approach failed, use directory-based mapping
        mapping = collect_existing_mutants(working_dir)
        
        return mapping
    except Exception as e:
        logger.error(f"Error collecting coverage: {str(e)}")
        # Return a minimal valid mapping structure
        return {
            'tests': [],
            'mutants': [],
            'test_coverage': {},
            'mutant_coverage': {}
        }

def run_test_with_mutants(args, test_id, mutant_ids, pytest_args, working_dir):
    """
    Run a specific test with multiple mutants enabled.
    
    Args:
        args: Command line arguments
        test_id: ID of the test to run
        mutant_ids: List of mutant IDs to enable
        pytest_args: Additional pytest arguments
        working_dir: Path to the instrumented project
    
    Returns:
        dict: Results for each mutant
    """
    
    # Create mutant config with all specified mutants enabled
    mutants_config = {
        'enable_mutation': True,
        'enabled_mutants': []
    }
    
    # Group mutants by type (xmt or sdl)
    xmt_mutants = [m for m in mutant_ids if m.startswith('xmt_')]
    sdl_mutants = [m for m in mutant_ids if m.startswith('sdl_')]
    
    # Add all mutants to config
    for mutant_id in xmt_mutants:
        mutants_config['enabled_mutants'].append({
            'type': 'xmt',
            'target': mutant_id
        })
    
    for mutant_id in sdl_mutants:
        # Extract statement type from mutant ID (e.g., 'for' from 'sdl_for_123')
        parts = mutant_id.split('_')
        if len(parts) > 1:
            stmt_type = parts[1]
            mutants_config['enabled_mutants'].append({
                'type': 'sdl',
                'target': [stmt_type]
            })
    
    # Write to mutant file
    os.makedirs(os.path.dirname(working_dir / '.pypseudo' / 'mutants.json'), exist_ok=True)
    with open(working_dir / '.pypseudo' / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=4)
    
    # Set environment variable
    os.environ['PYPSEUDO_CONFIG_FILE'] = str(working_dir / '.pypseudo' / 'mutants.json')
    
    # Extract just the filename from the test_id path for running the test
    test_filename = os.path.basename(test_id)
    
    # Build the test command - include verbose flag to see individual test names
    test_args = list(pytest_args) + [test_filename, "-v"]
    
    # Run the test and capture output
    try:
        logger.info(f"Running test {test_filename} with {len(mutant_ids)} mutants")
        process = subprocess.run(
            ["pytest"] + test_args,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=60  # Add a timeout to prevent hanging
        )
        
        # Attempt to identify individual test cases using regex pattern
        test_cases = []
        try:
            # This regex pattern looks for test names in pytest verbose output
            pattern = re.compile(r'::(\w+)(\[.*?\])?\s')
            for line in process.stdout.split('\n'):
                match = pattern.search(line)
                if match and test_filename in line:
                    test_case = match.group(1)
                    test_cases.append(test_case)
            
            # Remove duplicates while preserving order
            test_cases = list(dict.fromkeys(test_cases))
        except Exception as e:
            logger.warning(f"Error extracting test cases: {str(e)}")
            # Fall back to using the full test file if we can't extract test cases
            test_cases = []
        
        # Use test case info if available
        test_info = {
            'file': test_filename,
            'test_cases': test_cases
        }
        
        # Check if the test passed
        test_passed = process.returncode == 0
        
        # Process results for each mutant - if test passes, mutant survived
        results = {}
        for mutant_id in mutant_ids:
            results[mutant_id] = {
                'passed': test_passed,  # If tests pass, the mutant survived
                'test': test_info,
                'type': 'xmt' if mutant_id.startswith('xmt_') else 'sdl'
            }
        
        return results
    except subprocess.TimeoutExpired:
        logger.warning(f"Test {test_filename} timed out")
        # If test times out, consider it failed (mutant killed)
        results = {}
        for mutant_id in mutant_ids:
            results[mutant_id] = {
                'passed': False,  # Timeout means test failed, mutant killed
                'test': {'file': test_filename, 'test_cases': []},
                'type': 'xmt' if mutant_id.startswith('xmt_') else 'sdl',
                'timeout': True
            }
        return results
    except Exception as e:
        logger.error(f"Error running test {test_filename}: {str(e)}")
        # If there's an error, consider it failed (mutant killed)
        results = {}
        for mutant_id in mutant_ids:
            results[mutant_id] = {
                'passed': False,  # Error means test failed, mutant killed
                'test': {'file': test_filename, 'test_cases': []},
                'type': 'xmt' if mutant_id.startswith('xmt_') else 'sdl',
                'error': str(e)
            }
        return results


def run_all_mutations(args, pytest_args, working_dir=None):
    """
    Run tests with mutations grouped by test coverage.
    This is more efficient than running each mutation separately.
    """
    logger.info("Collecting existing mutants from instrumented code...")
    
    # Collect existing mutants
    coverage_data = collect_existing_mutants(working_dir)
    
    if not coverage_data or not coverage_data.get('mutants'):
        logger.error("No mutants found in the instrumented code")
        return {}
    
    logger.info(f"Found {len(coverage_data['mutants'])} mutants in the instrumented code")
    
    # Create a mapping of tests to mutants
    test_to_mutants = coverage_data.get('test_to_mutants', {})
    
    # Run each test with its associated mutants
    results = {}
    for test_file, mutants in test_to_mutants.items():
        if not mutants:
            continue
            
        logger.info(f"Running test {os.path.basename(test_file)} with {len(set(mutants))} mutants")
        
        # Enable all mutants covered by this test
        test_results = run_test_with_mutants(args, test_file, list(set(mutants)), pytest_args, working_dir)
        
        # Add results to the overall results
        for mutant_id, result in test_results.items():
            if mutant_id not in results:
                results[mutant_id] = result
    
    # Generate report
    killed = sum(1 for r in results.values() if not r['passed'])
    survived = sum(1 for r in results.values() if r['passed'])
    
    report = {
        'summary': {
            'total_mutations': len(results),
            'killed_mutations': killed,
            'survived_mutations': survived
        },
        'mutations': results,
        'metadata': {
            'timestamp': datetime.datetime.now().isoformat(),
            'target': str(args.project_path)
        }
    }
    
    # Write report
    report_path = 'mutation_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=4)
    
    # Print summary
    print("\nMutation Testing Report")
    print("-" * 50)
    print(f"Total Mutations: {len(results)}")
    print(f"Killed Mutations: {killed}")
    print(f"Survived Mutations: {survived}")
    print(f"\nDetailed results written to {report_path}")
    
    return results

def generate_mutation_report(results):
    """Generate a detailed report of mutation testing results"""
    report = {
        'summary': {
            'total_mutations': len(results),
            'killed_mutations': sum(1 for r in results.values() if not r['passed']),
            'survived_mutations': sum(1 for r in results.values() if r['passed'])
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
    parser.add_argument('--mutant-file', required=True, help='Path to the mutant file')
    parser.add_argument('--json-report', action='store_true', help='Generate a JSON report')
    parser.add_argument('--json-report-file', help='Path to save the JSON report')
    parser.add_argument('--cov', help='Module or directory to measure coverage for')
    parser.add_argument('--cov-report', help='Coverage report format (e.g., json, term, etc.)')

    args = parser.parse_args()

    # Check if pypseudo_instrumentation is installed
    try:
        import pypseudo_instrumentation
    except ImportError:
        logger.error("ERROR: pypseudo_instrumentation package is not installed.")
        logger.error("Please install it with: pip install -e ./pypseudo_instrumentation")
        return

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
            results = run_all_mutations(args, pytest_args, working_dir)
            if results:
                # Generate the report from results
                killed = sum(1 for r in results.values() if not r['passed'])
                survived = sum(1 for r in results.values() if r['passed'])
                
                print("\nMutation Testing Report")
                print("-" * 50)
                print(f"Total Mutations: {len(results)}")
                print(f"Killed Mutations: {killed}")
                print(f"Survived Mutations: {survived}")
                print(f"\nDetailed results written to mutation_report.json")
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