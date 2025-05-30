import pytest
import json
import os
import sys
from pathlib import Path

class MutationPlugin:
    def __init__(self, mutant_file=None):
        self.mutant_file = mutant_file
        self.mutation_enabled = False
        self.collecting_coverage = False
        self.enabled_mutants = []
        self.xmt_targets = set()  # functions to apply XMT
        self.sdl_targets = set()  # statement types for SDL
        self.coverage_collector = None  # Will be set by the coverage collector

    @pytest.hookimpl(tryfirst=True)
    def pytest_addoption(self, parser):
        parser.addoption(
            "--mutant-file", action="store", default=None, help="Path to the mutant file"
        )

    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(self, config):
        mutant_file = self.mutant_file or config.getoption("--mutant-file")
        
        if mutant_file and os.path.exists(mutant_file):
            # Set environment variable for config path
            os.environ['PYPSEUDO_CONFIG_FILE'] = str(mutant_file)
            
            with open(mutant_file, 'r') as f:
                mutants_data = json.load(f)
                self.mutation_enabled = mutants_data.get('enable_mutation', False)
                self.collecting_coverage = mutants_data.get('collect_coverage', False)
                
                # For coverage collection
                if self.collecting_coverage:
                    try:
                        from pypseudo_instrumentation import start_coverage_collection
                        start_coverage_collection()
                        print("Coverage collection mode enabled")
                    except ImportError:
                        print("Error: pypseudo_instrumentation not installed")
                
                # For mutation testing
                if self.mutation_enabled:
                    self.enabled_mutants = mutants_data.get('enabled_mutants', [])
                    self._process_mutants(self.enabled_mutants)
                    print(f"XMT targets: {self.xmt_targets}")
                    print(f"SDL targets: {self.sdl_targets}")
                else:
                    print("Mutations disabled.")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item):
        """Called before each test is run"""
        if self.collecting_coverage:
            try:
                from pypseudo_instrumentation import set_current_test
                set_current_test(item.nodeid)
                
                # If we have a coverage collector registered, tell it about this test
                if self.coverage_collector:
                    self.coverage_collector.current_test = item.nodeid
            except ImportError:
                pass

    def _process_mutants(self, mutants):
        """Process mutant configurations"""
        print("\n=== Debug: Processing Mutants ===")
        print(f"Input mutants: {json.dumps(mutants, indent=2)}")
        
        for mutant in mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                else:
                    self.xmt_targets.add(mutant['target'])
                print(f"Added XMT target: {mutant['target']}")
            elif mutant['type'] == 'sdl':
                self.sdl_targets.update(mutant['target'])
                print(f"Added SDL targets: {mutant['target']}")
        
        print(f"Final targets:")
        print(f"  - XMT: {self.xmt_targets}")
        print(f"  - SDL: {self.sdl_targets}")

    def load_mutants(self):
        """Load mutant data from file"""
        if self.mutant_file and os.path.exists(self.mutant_file):
            # Set environment variable for config path
            os.environ['PYPSEUDO_CONFIG_FILE'] = str(self.mutant_file)
            
            with open(self.mutant_file, 'r') as f:
                mutants_data = json.load(f)
                self.mutation_enabled = mutants_data.get('enable_mutation', False)
                self.collecting_coverage = mutants_data.get('collect_coverage', False)
                
                if self.mutation_enabled:
                    print("Mutations enabled.")
                    self.enabled_mutants = mutants_data.get('enabled_mutants', [])
                    self._process_mutants(self.enabled_mutants)
                    if self.enabled_mutants:
                        print("Active mutations:")
                        for mutant in self.enabled_mutants:
                            print(f"  - Type: {mutant['type']}, Target: {mutant['target']}")
                else:
                    print("Mutations disabled.")

    def register_coverage_collector(self, collector):
        """Register a coverage collector to receive coverage events"""
        self.coverage_collector = collector
        
        # Monkey-patch the pypseudo_instrumentation's register_coverage function
        try:
            import pypseudo_instrumentation.mutation_support as ms
            def register_coverage(mutant_id, test_id):
                if self.coverage_collector:
                    self.coverage_collector.register_mutant_coverage(mutant_id, test_id)
            
            # Replace the function
            ms.register_coverage = register_coverage
        except ImportError:
            print("Error: Could not monkey-patch register_coverage function")

    def is_mutant_enabled(self, mutant_id):
        """Check if mutation is enabled for given ID"""
        if not self.config.get('enable_mutation', False):
            print(f"\nMutation check [{mutant_id}]: disabled globally")
            return False

        parts = mutant_id.split('_')
        if len(parts) < 2:
            print(f"\nMutation check [{mutant_id}]: invalid format")
            return False
                
        mut_type = parts[0]      # xmt or sdl
        target_name = parts[1]   # function/statement name
        mutation_num = '_'.join(parts[2:]) if len(parts) > 2 else None

        print(f"\nMutation check [{mutant_id}]:")
        print(f"- Type: {mut_type}")
        print(f"- Target name: {target_name}")
        print(f"- Number: {mutation_num}")
        print(f"- XMT targets: {self.xmt_targets}")
        print(f"- SDL targets: {self.sdl_targets}")

        for mutant in self.enabled_mutants:
            if mutant['type'] == mut_type:
                if mut_type == 'xmt':
                    if mutant['target'] == '*':
                        print(f"- XMT wildcard match")
                        return True
                    target_match = mutant['target'] == f"{target_name}_{mutation_num}"
                    print(f"- XMT specific match: {target_match}")
                    return target_match
                else:  # SDL
                    target_match = target_name in mutant.get('target', [])
                    print(f"- SDL match: {target_match}")
                    return target_match

        print(f"- No matching mutation found")
        return False