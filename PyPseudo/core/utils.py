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
    
    # Copy project files
    for item in project_path.glob("**/*"):
        if item.is_file():
            relative_path = item.relative_to(project_path)
            target_path = working_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)
            
    return working_dir

def inject_mutation_support(target_file):
    """Inject necessary imports and support code"""
    support_code = """
# Auto-generated mutation support code
import os
import sys
from pathlib import Path

# Get absolute path to .pypseudo directory
_support_dir = Path(__file__).resolve().parent / '.pypseudo'
if _support_dir.exists():
    sys.path.insert(0, str(_support_dir))

# Import mutation support
from mutation_support import is_mutant_enabled, MutationPlugin
plugin = MutationPlugin(str(_support_dir / 'mutants.json'))
"""
    
    with open(target_file, 'r') as f:
        content = f.read()
    
    with open(target_file, 'w') as f:
        f.write(support_code + '\n' + content)
        

def copy_support_files(working_dir, mutants_config):
    """Copy necessary support files to project"""
    # Create .pypseudo directory for support files
    support_dir = working_dir / '.pypseudo'
    support_dir.mkdir(exist_ok=True)
    
    # Write mutation configuration
    with open(support_dir / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=2)
        
    # Copy mutation support module with updated template
    with open(support_dir / 'mutation_support.py', 'w') as f:
        f.write('''
import json
from pathlib import Path

class MutationPlugin:
    def __init__(self, config_file):
        self.config_file = config_file
        self.load_config()
    
    def load_config(self):
        try:
            with open(self.config_file) as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {}
            
    def load_mutants(self):
        """Reload mutation configuration"""
        self.load_config()
            
    def is_mutant_enabled(self, mutant_id):
        # Extract mutant info
        parts = mutant_id.split('_')
        if len(parts) < 2:
            return False
            
        mut_type = parts[0]  # xmt or sdl
        target = '_'.join(parts[1:-1])  # Function name or statement type
        
        # Check if mutation is enabled
        for mutant in self.config.get('enabled_mutants', []):
            if mutant['type'] == mut_type:
                if mut_type == 'xmt':
                    if mutant['target'] == target or mutant['target'] == '*':
                        return self.config.get('enable_mutation', False)
                else:  # SDL
                    if target in mutant.get('target', []):
                        return self.config.get('enable_mutation', False)
        return False

plugin = None

def is_mutant_enabled(mutant_id):
    """Global helper function for mutation checks"""
    global plugin
    if plugin is None:
        config_file = Path(__file__).parent / 'mutants.json'
        plugin = MutationPlugin(str(config_file))
    return plugin.is_mutant_enabled(mutant_id)
''')