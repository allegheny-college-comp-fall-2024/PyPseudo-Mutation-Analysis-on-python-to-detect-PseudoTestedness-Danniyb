# import pytest
# import os
# import json

# class PseudoTest:
#     enabled_mutants = set()
#     mutation_enabled = False

#     @staticmethod
#     def exec(mutant_id):
#         if not PseudoTest.mutation_enabled:
#             return False
#         return mutant_id in PseudoTest.enabled_mutants

# def pytest_addoption(parser):
#     """Add command line option to provide mutant file."""
#     parser.addoption(
#         "--mutant-file", action="store", default=None, help="Path to the mutant file"
#     )

# @pytest.hookimpl(tryfirst=True)
# def pytest_runtest_setup(item):
#     """Setup test environment before each test."""
#     mutant_file = item.config.getoption("--mutant-file")
#     if mutant_file and os.path.exists(mutant_file):
#         with open(mutant_file, 'r') as f:
#             mutants_data = json.load(f)
#             # Enable/Disable mutation based on `enable_mutation` field
#             PseudoTest.mutation_enabled = mutants_data.get('enable_mutation', False)
#             if PseudoTest.mutation_enabled:
#                 PseudoTest.enabled_mutants = set(mutants_data.get('enabled_mutants', []))
#             else:
#                 PseudoTest.enabled_mutants = set()
