"""
PyPseudo Instrumentation Support Package

This package provides the necessary components for PyPseudo mutation testing
to work with instrumented Python code.
"""

from .mutation_support import is_mutant_enabled, MutationPlugin

track_execution = lambda x: None  # Default no-op function