"""
Mutation support module for PyPseudo

This module provides the core functionality for enabling and disabling
mutations in instrumented Python code.
"""

import json
import os
from pathlib import Path
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global coverage tracking
_coverage_data = {'collecting': False, 'current_test': None}

def start_coverage_collection():
    """Enable coverage collection mode"""
    _coverage_data['collecting'] = True
    logger.debug("Coverage collection enabled")

def set_current_test(test_id):
    """Set the currently running test"""
    _coverage_data['current_test'] = test_id
    logger.debug(f"Current test set to: {test_id}")

def register_coverage(mutant_id, test_id=None):
    """
    Register that a mutant was covered by the current test.
    This function will be monkey-patched by the coverage collector.
    """
    test = test_id or _coverage_data['current_test']
    logger.debug(f"Coverage registered: {mutant_id} covered by {test}")
    # The real implementation will be injected by the MutationPlugin

class MutationPlugin:
    """
    Plugin for controlling mutations in instrumented code.
    
    This class is responsible for loading mutation configurations and
    determining whether specific mutations should be enabled.
    """
    
    def __init__(self, config_file=None):
        """
        Initialize the mutation plugin.
        
        Args:
            config_file: Path to the mutation configuration file
        """
        self.config_file = config_file
        self.config = {
            "enable_mutation": False,
            "enabled_mutants": []
        }
        self.enabled_mutants = []
        self.xmt_targets = set()
        self.sdl_targets = set()
        self.load_config()
    
    def load_config(self):
        """Load mutation configuration from file"""
        try:
            if self.config_file and os.path.exists(self.config_file):
                logger.debug(f"Loading config from {self.config_file}")
                with open(self.config_file) as f:
                    self.config = json.load(f)
                    self._process_mutants()
            else:
                logger.debug(f"Config file not found or not specified: {self.config_file}")
                # Try to discover config
                discovered_config = find_config_file()
                if discovered_config:
                    logger.debug(f"Discovered config at {discovered_config}")
                    self.config_file = discovered_config
                    with open(self.config_file) as f:
                        self.config = json.load(f)
                        self._process_mutants()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            
    def _process_mutants(self):
        """Process mutants from config"""
        if not self.config.get('enable_mutation', False):
            logger.debug("Mutations disabled in config")
            return
            
        self.enabled_mutants = self.config.get('enabled_mutants', [])
        logger.debug(f"Processing {len(self.enabled_mutants)} enabled mutants")
        
        for mutant in self.enabled_mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                    logger.debug("Added XMT wildcard target")
                else:
                    self.xmt_targets.add(mutant['target'])
                    logger.debug(f"Added XMT target: {mutant['target']}")
            elif mutant['type'] == 'sdl':
                if isinstance(mutant['target'], list):
                    self.sdl_targets.update(mutant['target'])
                    logger.debug(f"Added SDL targets: {mutant['target']}")
                else:
                    self.sdl_targets.add(mutant['target'])
                    logger.debug(f"Added SDL target: {mutant['target']}")

    def load_mutants(self):
        """Reload the mutation configuration"""
        self.load_config()
            
    def is_mutant_enabled(self, mutant_id):
        """
        Check if a specific mutation should be enabled.
        
        Args:
            mutant_id: Identifier for the mutation
            
        Returns:
            bool: True if the mutation should be enabled, False otherwise
        """
        # If we're collecting coverage, register the mutant but don't enable it
        if _coverage_data['collecting']:
            register_coverage(mutant_id, _coverage_data['current_test'])
            return False
            
        if not self.config.get('enable_mutation', False):
            # Short-circuit if mutations are globally disabled
            logger.debug(f"Mutation check [{mutant_id}]: disabled globally")
            return False

        parts = mutant_id.split('_')
        if len(parts) < 2:
            logger.debug(f"Mutation check [{mutant_id}]: invalid format")
            return False
            
        mut_type = parts[0]  # xmt or sdl
        
        # For XMT: parts[1] is function name, parts[2] is number 
        # For SDL: parts[1] is statement type, parts[2] is module, parts[3] is function, parts[4] is number
        
        if mut_type == 'xmt':
            target_name = '_'.join(parts[1:-1]) if len(parts) > 2 else parts[1]
            mutation_num = parts[-1] if len(parts) > 2 else None
        else:  # SDL
            target_name = parts[1]  # statement type (for, if, etc.)
            mutation_num = parts[-1]
            
        logger.debug(f"Mutation check [{mutant_id}]:")
        logger.debug(f"- Type: {mut_type}")
        logger.debug(f"- Target name: {target_name}")
        logger.debug(f"- Number: {mutation_num}")
            
        # Single mutant case (specific mutation enabled)
        if len(self.enabled_mutants) == 1 and self.enabled_mutants[0].get('target') != '*':
            if mut_type == 'xmt':
                target_match = mutant_id == self.enabled_mutants[0]['target']
                logger.debug(f"- XMT specific match: {target_match}")
                return target_match
            else:  # SDL
                if isinstance(self.enabled_mutants[0]['target'], list):
                    target_match = target_name in self.enabled_mutants[0]['target']
                else:
                    target_match = target_name == self.enabled_mutants[0]['target']
                logger.debug(f"- SDL match: {target_match}")
                return target_match

        # General case (multiple mutations or wildcards)
        for mutant in self.enabled_mutants:
            if mutant['type'] == mut_type:
                if mut_type == 'xmt':
                    if mutant['target'] == '*':
                        logger.debug("- XMT wildcard match")
                        return True
                    
                    # Check exact match for XMT
                    full_target = f"{target_name}_{mutation_num}" if mutation_num else target_name
                    target_match = mutant['target'] == full_target
                    logger.debug(f"- XMT specific match: {target_match}")
                    return target_match
                else:  # SDL
                    # For SDL, we just need to check if the statement type is enabled
                    if isinstance(mutant['target'], list):
                        target_match = target_name in mutant['target']
                    else:
                        target_match = target_name == mutant['target']
                    logger.debug(f"- SDL match: {target_match}")
                    return target_match
                    
        logger.debug("- No matching mutation found")
        return False

def find_config_file():
    """
    Find the mutation configuration file.
    
    This function uses multiple strategies to locate the configuration file:
    1. Check environment variable
    2. Search common locations
    
    Returns:
        str: Path to the configuration file, or None if not found
    """
    # Try environment variable first
    if 'PYPSEUDO_CONFIG_FILE' in os.environ:
        config_path = os.environ['PYPSEUDO_CONFIG_FILE']
        if os.path.exists(config_path):
            return config_path
        else:
            logger.debug(f"Config file from environment variable not found: {config_path}")
    
    # Search for config file in common locations
    search_paths = [
        Path('.pypseudo/mutants.json'),
        Path('../.pypseudo/mutants.json'),
        Path('../../.pypseudo/mutants.json'),
        Path('../../../.pypseudo/mutants.json'),
        Path('_pypseudo_work/.pypseudo/mutants.json'),
        Path('../_pypseudo_work/.pypseudo/mutants.json'),
        Path('../../_pypseudo_work/.pypseudo/mutants.json'),
        Path('../../../_pypseudo_work/.pypseudo/mutants.json')
    ]
    
    for path in search_paths:
        if path.exists():
            return str(path)
    
    # Additional search based on module paths
    for module_path in sys.path:
        potential_path = Path(module_path) / '.pypseudo' / 'mutants.json'
        if potential_path.exists():
            return str(potential_path)
    
    logger.debug("Config file not found in any location")
    return None

# Global singleton plugin instance
_plugin = None

def is_mutant_enabled(mutant_id):
    """
    Check if a mutation should be enabled.
    
    This is the main entry point for instrumented code to check
    if a specific mutation should be applied.
    
    Args:
        mutant_id: Identifier for the mutation
        
    Returns:
        bool: True if the mutation should be enabled, False otherwise
    """
    # If we're collecting coverage, register it
    if _coverage_data['collecting']:
        register_coverage(mutant_id, _coverage_data['current_test'])
        return False
        
    global _plugin
    if _plugin is None:
        config_file = find_config_file()
        _plugin = MutationPlugin(config_file)
    return _plugin.is_mutant_enabled(mutant_id)