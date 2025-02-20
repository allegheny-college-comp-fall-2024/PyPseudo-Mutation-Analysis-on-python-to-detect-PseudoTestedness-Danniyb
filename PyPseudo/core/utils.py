import os
import shutil
import logging
import importlib.util
from pathlib import Path
import json

logger = logging.getLogger(__name__)

def setup_project_environment(project_path):
    """
    Set up working environment for target project
    
    Args:
        project_path: Path to target project
    Returns:
        tuple: (working_dir, backup_path)
    """
    project_path = Path(project_path)
    if not project_path.exists():
        raise ValueError(f"Project path {project_path} does not exist")
        
    # Create working directory
    working_dir = project_path.parent / f"{project_path.name}_pypseudo_work"
    working_dir.mkdir(exist_ok=True)
    
    # Create .pypseudo directory
    pypseudo_dir = working_dir / '.pypseudo'
    pypseudo_dir.mkdir(exist_ok=True)
    
    # Create __init__.py files in key directories
    for dir_path in [working_dir, working_dir / 'src', working_dir / 'tests']:
        dir_path.mkdir(exist_ok=True)
        init_file = dir_path / '__init__.py'
        if not init_file.exists():
            init_file.touch()

    # Copy mutation support files
    with open(pypseudo_dir / '__init__.py', 'w') as f:
        f.write('')  # Empty __init__.py to make it a package
    
    # Copy project files maintaining directory structure
    for item in project_path.glob("**/*"):
        if item.is_file() and not item.name.startswith('__pycache__'):
            relative_path = item.relative_to(project_path)
            target_path = working_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)
            
    return working_dir

def inject_mutation_support(target_file):
    """
    Inject necessary imports and support code into target file
    
    Args:
        target_file: Path to file being instrumented
    """
    is_test_file = Path(target_file).name.startswith('test_') or 'test' in Path(target_file).name
    
    support_code = """
# Auto-generated mutation support code
import os
import sys
from pathlib import Path

# Add parent directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Add .pypseudo directory to path
_support_dir = current_dir / '.pypseudo'
if _support_dir.exists():
    sys.path.insert(0, str(_support_dir))

# Import support modules
""" + ("""
from mutation_support import MutationPlugin, is_mutant_enabled
""" if is_test_file else """
from mutation_support import MutationPlugin, is_mutant_enabled
plugin = MutationPlugin(str(_support_dir / 'mutants.json'))
""")
    
    with open(target_file, 'r') as f:
        content = f.read()
        
    with open(target_file, 'w') as f:
        f.write(support_code + '\n' + content)
    
        
def copy_support_files(working_dir, mutants_config):
    support_dir = working_dir / '.pypseudo'
    support_dir.mkdir(exist_ok=True)
    
    with open(support_dir / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=2)
        
    support_code = '''
import json
import os
from pathlib import Path

class MutationPlugin:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = {}
        self.enabled_mutants = []
        self.xmt_targets = set()
        self.sdl_targets = set()
        self.load_config()
    
    def load_config(self):
        try:
            with open(self.config_file) as f:
                self.config = json.load(f)
                self._process_mutants()
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

_plugin = None

def is_mutant_enabled(mutant_id):
    """Global helper for mutation checks"""
    global _plugin
    if _plugin is None:
        config_file = str(Path(__file__).parent / 'mutants.json')
        _plugin = MutationPlugin(config_file)
    return _plugin.is_mutant_enabled(mutant_id)
'''
    with open(support_dir / 'mutation_support.py', 'w') as f:
        f.write(support_code)