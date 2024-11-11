import pytest
import argparse
import logging
import shutil
import os
import json
import ast
from contextlib import contextmanager
import signal
from mutation_plugin import MutationPlugin
from instrumentation import run_instrumentation, restore_original

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_code_for_mutations(file_path):
    """Analyze code and return available mutation points"""
    with open(file_path, 'r') as f:
        source_code = f.read()
    
    tree = ast.parse(source_code)
    
    class MutationAnalyzer(ast.NodeVisitor):
        def __init__(self):
            self.mutations = {
                'xmt': set(),  # Function names
                'sdl': {
                    'for': [],
                    'if': [],
                }
            }
            self.current_function = None
            
        def visit_FunctionDef(self, node):
            if not (node.name.startswith('__') and node.name.endswith('__')):
                self.mutations['xmt'].add(node.name)
            self.current_function = node.name
            self.generic_visit(node)
            
        def visit_For(self, node):
            self.mutations['sdl']['for'].append({
                'function': self.current_function,
                'lineno': node.lineno
            })
            self.generic_visit(node)
            
        def visit_If(self, node):
            self.mutations['sdl']['if'].append({
                'function': self.current_function,
                'lineno': node.lineno
            })
            self.generic_visit(node)
    
    analyzer = MutationAnalyzer()
    analyzer.visit(tree)
    return analyzer.mutations

def list_available_mutations(args):
    """List all available mutation points in the code"""
    target_file = 'simplePro/calculator.py'
    mutations = analyze_code_for_mutations(target_file)
    
    print("\nAvailable Mutations:")
    print("-" * 50)
    print("\nXMT Mutations (Function Level):")
    for func in sorted(mutations['xmt']):
        print(f"  - xmt_{func}")
    
    print("\nSDL Mutations (Statement Level):")
    for stmt_type, locations in mutations['sdl'].items():
        print(f"\n  {stmt_type.upper()} Statements:")
        for loc in locations:
            print(f"    - sdl_{stmt_type} in {loc['function']} (line {loc['lineno']})")

def run_single_mutation_test(mutant_file, mutation_id, pytest_args):
    """Run tests with a single mutation enabled"""
    with open(mutant_file, 'r') as f:
        mutants_data = json.load(f)
    
    # Configure for single mutation
    mutants_data['enable_mutation'] = True
    if mutation_id.startswith('xmt_'):
        function_name = mutation_id.replace('xmt_', '')
        mutants_data['enabled_mutants'] = [{'type': 'xmt', 'target': function_name}]
    else:
        stmt_type = mutation_id.replace('sdl_', '')
        mutants_data['enabled_mutants'] = [{'type': 'sdl', 'target': [stmt_type]}]
    
    with open(mutant_file, 'w') as f:
        json.dump(mutants_data, f, indent=4)
    
    # Run tests and collect results
    result = run_tests(mutant_file, pytest_args)
    return result

def run_all_mutations(args, pytest_args):
    """Run tests with each mutation one by one"""
    target_file = 'simplePro/calculator.py'
    mutations = analyze_code_for_mutations(target_file)
    results = {}
    
    # Run XMT mutations
    for func in mutations['xmt']:
        mutation_id = f"xmt_{func}"
        print(f"\nTesting mutation: {mutation_id}")
        result = run_single_mutation_test(args.mutant_file, mutation_id, pytest_args)
        results[mutation_id] = {
            'passed': result == 0,
            'function': func,
            'type': 'xmt'
        }
    
    # Run SDL mutations
    for stmt_type, locations in mutations['sdl'].items():
        mutation_id = f"sdl_{stmt_type}"
        print(f"\nTesting mutation: {mutation_id}")
        result = run_single_mutation_test(args.mutant_file, mutation_id, pytest_args)
        results[mutation_id] = {
            'passed': result == 0,
            'locations': locations,
            'type': 'sdl'
        }
    
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
    
    # Mutation type flags
    parser.add_argument('--xmt', action='store_true',
                       help='Use extreme mutation testing only')
    parser.add_argument('--sdl', action='store_true',
                       help='Use statement deletion testing only')
    
    # Mutation control flags
    parser.add_argument('--enable-mutations', action='store_true',
                       help='Enable mutations during test run')
    parser.add_argument('--disable-mutations', action='store_true',
                       help='Disable all mutations during test run')
    parser.add_argument('--single-mutant', 
                       help='Run tests with only specified mutant enabled (e.g., "xmt_add" or "sdl_for")')
    
    # Your existing arguments remain the same...
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

    target_file = 'simplePro/calculator.py'
    backup_path = f"{target_file}.backup"
    original_backup_path = f"{target_file}.original"
    original_mutants = None #Intialize here 

    try:
        if args.list_mutations:
            list_available_mutations(args)
            return

        if args.run_all_mutations:
            results = run_all_mutations(args, pytest_args)
            generate_mutation_report(results)
            return
        
        if args.restore:
            logger.info(f"Restoring {target_file} to original state")
            if os.path.exists(original_backup_path):
                shutil.copy2(original_backup_path, target_file)
                os.remove(original_backup_path)
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                logger.info(f"Successfully restored {target_file} to original state")
            else:
                logger.warning("No original backup found. Cannot restore to original state.")
            return

        # Create original backup if it doesn't exist
        if not os.path.exists(original_backup_path):
            logger.info(f"Creating original backup of {target_file}")
            shutil.copy2(target_file, original_backup_path)

        # Create working backup
        logger.info(f"Creating working backup of {target_file}")
        shutil.copy2(target_file, backup_path)

        # Load and filter mutations based on flags
        with open(args.mutant_file, 'r') as f:
            mutants_data = json.load(f)
            original_mutants = json.loads(json.dumps(mutants_data))  # Deep copy
        
        filtered_mutants = filter_mutations(mutants_data, args)
        
        # Write filtered mutations back to file
        with open(args.mutant_file, 'w') as f:
            json.dump(filtered_mutants, f, indent=4)

        # Run instrumentation
        logger.info("Running instrumentation...")
        run_instrumentation(target_file, args.mutant_file)

        if args.instrument:
            logger.info("Instrumentation complete")
            return

        if args.run:
            # Run tests
            logger.info("Running tests...")
            result = run_tests(args.mutant_file, pytest_args)

            if result == 0:
                logger.info("All tests passed")
            else:
                logger.warning("Some tests failed")

            # Restore from working backup after test run
            logger.info("Restoring from working backup...")
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, target_file)
                os.remove(backup_path)

    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
        if os.path.exists(original_backup_path):
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