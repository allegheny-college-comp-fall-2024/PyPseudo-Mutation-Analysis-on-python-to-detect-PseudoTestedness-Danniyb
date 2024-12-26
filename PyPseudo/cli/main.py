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

def run_single_mutation_test(args, mutation_id, pytest_args):
    """
    Run tests with a single mutation enabled.
    
    Args:
        args: Command line arguments
        mutation_id: ID of mutation to test
        pytest_args: Additional pytest arguments
    
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
            
        # Run tests
        return run_tests(args.mutant_file, pytest_args)
        
    except Exception as e:
        logger.error(f"Error running mutation {mutation_id}: {e}")
        return 1

def run_all_mutations(args, pytest_args):
    """Run tests with each mutation one by one"""
    # Determine target path and get mutations
    target_path = args.project_path if args.project_path else 'simplePro/newtest.py'
    all_mutations = {
        'xmt': [],
        'sdl': {'for': [], 'if': []}
    }
    
    # Collect mutations from all files
    for file_path in get_target_files(target_path):
        if '.pypseudo' not in str(file_path):
            try:
                file_mutations = analyze_code_for_mutations(file_path)
                # Add file info to mutations
                for mut in file_mutations['xmt']:
                    mut['file'] = str(file_path)
                all_mutations['xmt'].extend(file_mutations['xmt'])
                
                for stmt_type in ['for', 'if']:
                    for mut in file_mutations['sdl'][stmt_type]:
                        mut['file'] = str(file_path)
                    all_mutations['sdl'][stmt_type].extend(file_mutations['sdl'][stmt_type])
                    
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                continue
    
    results = {}
    
    # Run XMT mutations
    print("\nRunning XMT mutations:")
    for mut in sorted(all_mutations['xmt'], key=lambda x: (x['file'], x['function'], x['number'])):
        mutation_id = mut['id']
        print(f"\nTesting mutation: {mutation_id} in {mut['file']}")
        result = run_single_mutation_test(args, mutation_id, pytest_args)
        results[mutation_id] = {
            'passed': result == 0,
            'file': mut['file'],
            'function': mut['function'],
            'type': 'xmt',
            'number': mut['number']
        }
    
    # Run SDL mutations
    print("\nRunning SDL mutations:")
    
    # Process both for and if mutations
    for stmt_type in ['for', 'if']:
        print(f"\nProcessing {stmt_type.upper()} statement mutations:")
        for mut in sorted(all_mutations['sdl'][stmt_type], 
                         key=lambda x: (x['file'], x['function'], x['lineno'])):
            mutation_id = mut['id']
            print(f"\nTesting mutation: {mutation_id} in {mut['file']}")
            result = run_single_mutation_test(args, mutation_id, pytest_args)
            results[mutation_id] = {
                'passed': result == 0,
                'file': mut['file'],
                'function': mut['function'],
                'type': 'sdl',
                'statement_type': stmt_type,
                'line': mut['lineno'],
                'number': mut.get('number', 0)
            }
    
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
            'target': str(target_path)
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

def run_tests(mutant_file, pytest_args):
    """Run tests with the mutation plugin"""
    plugin = MutationPlugin(mutant_file)
    plugin.load_mutants()
    
    try:
        with timeout(30):  # Add 30 second timeout
            result = pytest.main(pytest_args, plugins=[plugin])
            return result
    except TimeoutException:
        logger.error("Test execution timed out")
        return 1
    except Exception as e:
        logger.error(f"Error during test execution: {str(e)}")
        return 1

@contextmanager
def timeout(seconds):
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

class TimeoutException(Exception):
    pass

def filter_mutations(mutants_data, args):
    """Filter mutations based on command line arguments"""
    # Handle mutation enabling/disabling
    if args.disable_mutations:
        mutants_data['enable_mutation'] = False
    else:
        mutants_data['enable_mutation'] = True
    
    # Handle single mutant case
    if args.single_mutant:
        parts = args.single_mutant.split('_')
        mut_type = parts[0]
        target = '_'.join(parts[1:])  # Join remaining parts for numbered mutations
        
        if mut_type == 'xmt':
            mutants_data['enabled_mutants'] = [{'type': 'xmt', 'target': target}]
        else:
            mutants_data['enabled_mutants'] = [{'type': 'sdl', 'target': [target]}]
        return mutants_data
    
    filtered_mutants = []
    if args.sdl:
        filtered_mutants.append({'type': 'sdl', 'target': ['if']})
        filtered_mutants.append({'type': 'sdl', 'target': ['for']})
    if args.xmt:
        filtered_mutants.append({'type': 'xmt', 'target': '*'})
    
    if not filtered_mutants:
        filtered_mutants = [
            {'type': 'xmt', 'target': '*'},
            {'type': 'sdl', 'target': ['for']},
            {'type': 'sdl', 'target': ['if']}
        ]
    
    mutants_data['enabled_mutants'] = filtered_mutants
    return mutants_data

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
    
    # project path argument
    parser.add_argument('--project-path',
                       help='Path to the project to analyze. If not provided, will use default target file.')
    
    # mutation type flags
    parser.add_argument('--xmt', action='store_true',
                       help='Use extreme mutation testing only')
    parser.add_argument('--sdl', action='store_true',
                       help='Use statement deletion testing only')
    
    # mutation control flags
    parser.add_argument('--enable-mutations', action='store_true',
                       help='Enable mutations during test run')
    parser.add_argument('--disable-mutations', action='store_true',
                       help='Disable all mutations during test run')
    parser.add_argument('--single-mutant', 
                       help='Run tests with only specified mutant enabled (e.g., "xmt_add" or "sdl_for")')
    
    # Reporting arguments
    parser.add_argument('--mutant-file', required=True, help='Path to the mutant file.')
    parser.add_argument('--json-report', action='store_true', help='Generate a JSON report.')
    parser.add_argument('--json-report-file', help='Path to save the JSON report.')
    parser.add_argument('--cov', help='Module or directory to measure coverage for.')
    parser.add_argument('--cov-report', help='Coverage report format (e.g., json, term, etc.).')

    args = parser.parse_args()

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

    # Set target paths
    target_file = args.project_path if args.project_path else 'simplePro/newtest.py'
    is_project_mode = args.project_path is not None
    
    if is_project_mode:
        working_dir = Path(target_file).parent / f"{Path(target_file).name}_pypseudo_work"
    else:
        backup_path = f"{target_file}.backup"
        original_backup_path = f"{target_file}.original"
    
    original_mutants = None #Initialize here 

    try:
        if args.list_mutations:
            target = working_dir if is_project_mode else target_file
            list_available_mutations(args, target)
            return

        if args.run_all_mutations:
            target = working_dir if is_project_mode else target_file
            results = run_all_mutations(args, pytest_args, target)
            generate_mutation_report(results)
            return
        
        if args.restore:
            if is_project_mode:
                logger.info(f"Restoring project {target_file}")
                restore_project(target_file)
            else:
                logger.info(f"Restoring {target_file} to original state")
                restore_original(target_file, original_backup_path)
            return

        # Load and filter mutations based on flags
        with open(args.mutant_file, 'r') as f:
            mutants_data = json.load(f)
            original_mutants = json.loads(json.dumps(mutants_data))  # Deep copy
        
        filtered_mutants = filter_mutations(mutants_data, args)
        
        # Write filtered mutations back to file
        with open(args.mutant_file, 'w') as f:
            json.dump(filtered_mutants, f, indent=4)

        if args.instrument:
            logger.info("Running instrumentation...")
            if is_project_mode:
                process_project(target_file, args.mutant_file)
            else:
                # Create original backup if it doesn't exist
                if not os.path.exists(original_backup_path):
                    logger.info(f"Creating original backup of {target_file}")
                    shutil.copy2(target_file, original_backup_path)

                # Create working backup
                logger.info(f"Creating working backup of {target_file}")
                shutil.copy2(target_file, backup_path)
                
                run_instrumentation(target_file, args.mutant_file)
            
            logger.info("Instrumentation complete")
            return

        if args.run:
            logger.info("Running tests...")
            target = working_dir if is_project_mode else target_file
            result = run_tests(args.mutant_file, pytest_args, target)

            if result == 0:
                logger.info("All tests passed")
            else:
                logger.warning("Some tests failed")

            # Restore from backup for file mode
            if not is_project_mode:
                logger.info("Restoring from working backup...")
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, target_file)
                    os.remove(backup_path)

    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
        if not is_project_mode and os.path.exists(original_backup_path):
            logger.info("Attempting to restore from original backup after error...")
            shutil.copy2(original_backup_path, target_file)
            if os.path.exists(backup_path):
                os.remove(backup_path)
        raise

    finally:
        # Only restore mutants file if we have original_mutants
        if original_mutants is not None:
            with open(args.mutant_file, 'w') as f:
                json.dump(original_mutants, f, indent=4)

if __name__ == "__main__":
    main()