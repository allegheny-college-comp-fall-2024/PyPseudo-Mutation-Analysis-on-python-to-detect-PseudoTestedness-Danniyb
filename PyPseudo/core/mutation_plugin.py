import pytest
import json
import os

class MutationPlugin:
    def __init__(self, mutant_file=None):
        self.mutant_file = mutant_file
        self.mutation_enabled = False
        self.enabled_mutants = []
        self.xmt_targets = set()  # functions to apply XMT
        self.sdl_targets = set()  # statement types for SDL

    @pytest.hookimpl(tryfirst=True)
    def pytest_addoption(self, parser):
        parser.addoption(
            "--mutant-file", action="store", default=None, help="Path to the mutant file"
        )

    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(self, config):
        mutant_file = self.mutant_file or config.getoption("--mutant-file")
        
        if mutant_file and os.path.exists(mutant_file):
            with open(mutant_file, 'r') as f:
                mutants_data = json.load(f)
                self.mutation_enabled = mutants_data.get('enable_mutation', False)
                
                if self.mutation_enabled:
                    self.enabled_mutants = mutants_data.get('enabled_mutants', [])
                    self._process_mutants(self.enabled_mutants)
                    print(f"XMT targets: {self.xmt_targets}")
                    print(f"SDL targets: {self.sdl_targets}")
                else:
                    print("Mutations disabled.")

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
            with open(self.mutant_file, 'r') as f:
                mutants_data = json.load(f)
                self.mutation_enabled = mutants_data.get('enable_mutation', False)
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

    def is_mutant_enabled(self, mutant_id):
        """Check if mutation is enabled for given ID"""
        print(f"\n=== Debug: Mutation Check for {mutant_id} ===")
        print(f"Mutation enabled flag: {self.mutation_enabled}")
        print(f"Current enabled_mutants: {json.dumps(self.enabled_mutants, indent=2)}")
            
        if not self.mutation_enabled:
            print("Result: Mutations globally disabled")
            return False

        # Parse mutation ID
        parts = mutant_id.split('_')
        if len(parts) < 2:
            print("Result: Invalid mutation ID format")
            return False
                
        mut_type = parts[0]  # xmt or sdl
        target = parts[1]    # Function/statement name
        number = parts[2] if len(parts) > 2 else None  # Mutation number
            
        print(f"Parsed mutation:")
        print(f"  - Type: {mut_type}")
        print(f"  - Target: {target}")
        print(f"  - Number: {number}")
        print(f"Current targets:")
        print(f"  - XMT: {self.xmt_targets}")
        print(f"  - SDL: {self.sdl_targets}")

        # For XMT mutations
        if mut_type == 'xmt':
            exact_id = '_'.join([target, number]) if number else target
            result = exact_id in self.xmt_targets
            print(f"XMT check: {exact_id} in {self.xmt_targets} = {result}")
            return result

        # For SDL mutations    
        if mut_type == 'sdl':
            stmt_type = target
            result = stmt_type in self.sdl_targets
            print(f"SDL check: {stmt_type} in {self.sdl_targets} = {result}")
            return result

        print("Result: No matching mutation type")
        return False