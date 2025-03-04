import json
import os
from pathlib import Path

class MutationPlugin:
    def __init__(self, config_file=None):
        self.config_file = config_file
        self.config = {}
        self.enabled_mutants = []
        self.xmt_targets = set()
        self.sdl_targets = set()
        self.load_config()
    
    def load_config(self):
        try:
            if self.config_file and os.path.exists(self.config_file):
                with open(self.config_file) as f:
                    self.config = json.load(f)
                    self._process_mutants()
            else:
                print(f"Config file not found: {self.config_file}")
        except Exception as e:
            print(f"Error loading config: {e}")
            
    def _process_mutants(self):
        """Process mutants from config"""
        if not self.config.get('enable_mutation', False):
            return
            
        self.enabled_mutants = self.config.get('enabled_mutants', [])
        for mutant in self.enabled_mutants:
            if mutant['type'] == 'xmt':
                if mutant['target'] == '*':
                    self.xmt_targets.add('*')
                else:
                    self.xmt_targets.add(mutant['target'])
            elif mutant['type'] == 'sdl':
                self.sdl_targets.update(mutant['target'])

    def load_mutants(self):
        self.load_config()
            
    def is_mutant_enabled(self, mutant_id):
        """Check if mutation is enabled"""
        if not self.config.get('enable_mutation', False):
            return False

        parts = mutant_id.split('_')
        if len(parts) < 2:
            return False
            
        mut_type = parts[0]      # xmt or sdl
        target_name = '_'.join(parts[1:-1])   # function/statement name
        mutation_num = parts[-1]  # mutation number
        
        # For single mutant case
        if len(self.enabled_mutants) == 1 and self.enabled_mutants[0].get('target') != '*':
            if mut_type == 'xmt':
                return mutant_id == self.enabled_mutants[0]['target']
            else:  # SDL
                return target_name in self.enabled_mutants[0]['target']

        # For general case
        for mutant in self.enabled_mutants:
            if mutant['type'] == mut_type:
                if mut_type == 'xmt':
                    if mutant['target'] == '*':
                        return True
                    return target_name == mutant['target']
                else:  # SDL
                    return target_name in mutant['target']
                    
        return False

# Robust config file discovery
def find_config_file():
    """Find the config file using multiple strategies"""
    # Try environment variable first
    if 'PYPSEUDO_CONFIG_FILE' in os.environ:
        return os.environ['PYPSEUDO_CONFIG_FILE']
    
    # Search for config file in common locations
    search_paths = [
        Path('.pypseudo/mutants.json'),
        Path('../.pypseudo/mutants.json'),
        Path('../../.pypseudo/mutants.json'),
        Path('_pypseudo_work/.pypseudo/mutants.json'),
        Path('../_pypseudo_work/.pypseudo/mutants.json'),
        Path('../../_pypseudo_work/.pypseudo/mutants.json')
    ]
    
    for path in search_paths:
        if path.exists():
            return str(path)
    
    return None

# Global singleton pattern for the plugin
_plugin = None

def is_mutant_enabled(mutant_id):
    """Global helper for mutation checks"""
    global _plugin
    if _plugin is None:
        config_file = find_config_file()
        _plugin = MutationPlugin(config_file)
    return _plugin.is_mutant_enabled(mutant_id)