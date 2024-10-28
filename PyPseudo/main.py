import pytest
import argparse
import logging
import shutil
import os
from mutation_plugin import MutationPlugin
from instrumentation import run_instrumentation, restore_original

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_tests(mutant_file, pytest_args):
    """Run tests with the mutation plugin"""
    plugin = MutationPlugin(mutant_file)
    plugin.load_mutants()  # Use existing method name
    return pytest.main(pytest_args, plugins=[plugin])

def main():
    # Use your existing argument parser setup
    parser = argparse.ArgumentParser(description='Run mutation testing with pytest.')
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

    try:
        # Create backup of original file
        logger.info(f"Creating backup of {target_file}")
        shutil.copy2(target_file, backup_path)

        # Run instrumentation on the original file
        logger.info("Running instrumentation...")
        run_instrumentation(target_file, args.mutant_file)

        # Run tests
        logger.info("Running tests...")
        result = run_tests(args.mutant_file, pytest_args)

        if result == 0:
            logger.info("All tests passed")
        else:
            logger.warning("Some tests failed")

    except Exception as e:
        logger.error(f"Error during testing: {str(e)}")
        raise

    finally:
        # Restore original file
        logger.info("Restoring original file...")
        restore_original(target_file, backup_path)
        
        # Clean up backup file
        if os.path.exists(backup_path):
            os.remove(backup_path)

if __name__ == "__main__":
    main()