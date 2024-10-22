import pytest
import argparse
from mutation_plugin import MutationPlugin
from simplePro.calculator import Calculator
from instrumentation import run_instrumentation


def run_tests(mutant_file, pytest_args):
    # Initialize the MutationPlugin with the mutant file
    plugin = MutationPlugin(mutant_file)
    
    # Run pytest programmatically with the provided arguments
    print(f"Running pytest with arguments: {pytest_args}")
    pytest.main(pytest_args, plugins=[plugin])

def main():
    # Use argparse to handle command-line arguments
    parser = argparse.ArgumentParser(description='Run mutation testing with pytest.')
    parser.add_argument('--mutant-file', required=True, help='Path to the mutant file.')
    parser.add_argument('--json-report', action='store_true', help='Generate a JSON report.')
    parser.add_argument('--json-report-file', help='Path to save the JSON report.')
    parser.add_argument('--cov', help='Module or directory to measure coverage for.')
    parser.add_argument('--cov-report', help='Coverage report format (e.g., json, term, etc.).')

    args, unknown = parser.parse_known_args()

    # Prepare pytest arguments
    pytest_args = []
    if args.json_report:
        pytest_args.extend(['--json-report'])
    if args.json_report_file:
        pytest_args.extend(['--json-report-file', args.json_report_file])
    if args.cov:
        pytest_args.extend(['--cov', args.cov])
    if args.cov_report:
        pytest_args.extend(['--cov-report', args.cov_report])

    # Instrument the code
    run_instrumentation('simplePro/calculator.py', 'simplePro/mutated_calculator.py', args.mutant_file)

    # Initialize the plugin and inject it into Calculator
    plugin = MutationPlugin(args.mutant_file)
    calculator = Calculator(plugin)  # Inject the plugin instance into the calculator
    
    # Call run_tests with the parsed mutant_file and pytest_args
    run_tests(args.mutant_file, pytest_args)

if __name__ == "__main__":
    main()
