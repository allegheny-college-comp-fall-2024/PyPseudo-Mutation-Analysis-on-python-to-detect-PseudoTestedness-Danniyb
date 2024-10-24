import pytest
import json
import os

class MutationPlugin:
    def __init__(self, mutant_file=None):
        self.mutant_file = mutant_file
        self.mutation_enabled = False
        self.enabled_mutants = set()

    @pytest.hookimpl(tryfirst=True)
    def pytest_addoption(self, parser):
        """
        Add command line option to provide the mutant file.
        This allows passing --mutant-file from the command line.
        """
        parser.addoption(
            "--mutant-file", action="store", default=None, help="Path to the mutant file"
        )

    @pytest.hookimpl(tryfirst=True)
    def pytest_configure(self, config):
        """
        Configure pytest to load mutant data from the provided mutant file.
        This method reads the mutant file and sets up the mutation settings.
        """
        mutant_file = self.mutant_file or config.getoption("--mutant-file")
        
        if mutant_file and os.path.exists(mutant_file):
            with open(mutant_file, 'r') as f:
                mutants_data = json.load(f)
                self.mutation_enabled = mutants_data.get('enable_mutation', False)
                
                if self.mutation_enabled:
                    print(f"Mutations enabled. Loading mutants from {mutant_file}.")
                    self.enabled_mutants = set(mutants_data.get('enabled_mutants', []))
                    print(f"Active mutants: {self.enabled_mutants}")
                else:
                    print("Mutations disabled.")
                    self.enabled_mutants = set()
        else:
            print(f"Mutant file '{mutant_file}' not found or mutation disabled.")
            self.enabled_mutants = set()

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item):
        """
        Hook that runs before every test. 
        You can implement mutation-specific setup logic here if needed.
        """
        if not self.mutation_enabled:
            print("Mutation is disabled. Running tests without mutation.")
        else:
            print(f"Mutation is enabled for the following mutants: {self.enabled_mutants}")

    def load_mutants(self):
        """
        Load mutant data manually from the provided mutant file.
        This method is used when running the tests programmatically from main.py.
        """
        if self.mutant_file and os.path.exists(self.mutant_file):
            with open(self.mutant_file, 'r') as f:
                mutants_data = json.load(f)
                self.mutation_enabled = mutants_data.get('enable_mutation', False)
                
                if self.mutation_enabled:
                    print(f"Mutations enabled. Loading mutants from {self.mutant_file}.")
                    self.enabled_mutants = set(mutants_data.get('enabled_mutants', []))
                    print(f"Active mutants: {self.enabled_mutants}")
                else:
                    print("Mutations disabled.")
                    self.enabled_mutants = set()
        else:
            print(f"Mutant file '{self.mutant_file}' not found or mutation disabled.")
            self.enabled_mutants = set()

    def is_mutant_enabled(self, mutant_id):
        """
        Check if the given mutant is enabled. This method will be used in the
        actual code (like in Calculator class) to apply mutations.
        """
        is_enabled = str(mutant_id in self.enabled_mutants)
        print(f"Checking if mutant '{mutant_id}' is enabled: {is_enabled}")
        return self.mutation_enabled and is_enabled
