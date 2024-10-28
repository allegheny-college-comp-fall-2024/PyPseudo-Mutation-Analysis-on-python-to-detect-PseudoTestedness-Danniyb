import pytest
import argparse
import logging
import shutil
import os
import json
from mutation_plugin import MutationPlugin
from instrumentation import run_instrumentation, restore_original

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_tests(mutant_file, pytest_args):
    """Run tests with the mutation plugin"""
    plugin = MutationPlugin(mutant_file)
    plugin.load_mutants()
    return pytest.main(pytest_args, plugins=[plugin])

def filter_mutations(mutants_data, args):
    """Filter mutations based on command line arguments"""
    # Always enable mutations when filtering
    mutants_data['enable_mutation'] = True
    
    if not (args.xmt or args.sdl):  # If neither specified, keep all
        mutants_data['enabled_mutants'] = [
            {'type': 'xmt', 'target': '*'},  # Enable XMT for all functions
            {'type': 'sdl', 'target': ['for', 'if']}  # Enable SDL for for/if statements
        ]
        return mutants_data
        
    filtered_mutants = []
    if args.xmt:
        filtered_mutants.append({'type': 'xmt', 'target': '*'})
    if args.sdl:
        filtered_mutants.append({'type': 'sdl', 'target': ['for', 'if']})
    
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
    
    # Mutation type flags
    parser.add_argument('--xmt', action='store_true',
                       help='Use extreme mutation testing only')
    parser.add_argument('--sdl', action='store_true',
                       help='Use statement deletion testing only')
    
    # Required and existing arguments
    parser.add_argument('--mutant-file', required=True, help='Path to the mutant file.')
    parser.add_argument('--json-report', action='store_true', help='Generate a JSON report.')
    parser.add_argument('--json-report-file', help='Path to save the JSON report.')
    parser.add_argument('--cov', help='Module or directory to measure coverage for.')
    parser.add_argument('--cov-report', help='Coverage report format (e.g., json, term, etc.).')

    args = parser.parse_args()

    target_file = 'simplePro/calculator.py'
    backup_path = f"{target_file}.backup"
    original_backup_path = f"{target_file}.original"
    original_mutants = None  # Initialize here

    try:
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