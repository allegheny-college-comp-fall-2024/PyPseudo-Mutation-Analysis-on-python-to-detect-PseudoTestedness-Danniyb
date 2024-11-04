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
        for mutant in mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                else:
                    self.xmt_targets.add(mutant['target'])
            elif mutant['type'] == 'sdl':
                self.sdl_targets.update(mutant['target'])

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
        if not self.mutation_enabled:
            return False
            
        # Handle XMT mutations
        if mutant_id.startswith('xmt_'):
            function_name = mutant_id.replace('xmt_', '')
            return '*' in self.xmt_targets or function_name in self.xmt_targets
            
        # Handle SDL mutations
        if mutant_id.startswith('sdl_'):
            stmt_type = mutant_id.replace('sdl_', '')
            return stmt_type in self.sdl_targets
            
        return False