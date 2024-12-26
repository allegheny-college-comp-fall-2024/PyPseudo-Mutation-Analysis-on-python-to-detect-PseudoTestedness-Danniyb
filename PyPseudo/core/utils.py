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
    """
    Inject necessary imports and support code into target file
    
    Args:
        target_file: Path to file being instrumented
    """
    support_code = """
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / '.pypseudo'))

from mutation_support import is_mutant_enabled, MutationPlugin
"""
    
    with open(target_file, 'r') as f:
        content = f.read()
    
    with open(target_file, 'w') as f:
        f.write(support_code + '\n' + content)

def copy_support_files(working_dir, mutants_config):
    """
    Copy necessary support files to project
    
    Args:
        working_dir: Path to working directory
        mutants_config: Dictionary containing mutation configuration
    """
    support_dir = working_dir / '.pypseudo'
    support_dir.mkdir(exist_ok=True)
    
    # Write mutation configuration
    with open(support_dir / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=2)
    
    # Copy core functionality
    core_files = {
        'mutation_support.py': '''
from pathlib import Path
import json

class MutationPlugin:
    def __init__(self, config_file):
        self.config_file = config_file
        self.load_config()
    
    def load_config(self):
        with open(self.config_file) as f:
            self.config = json.load(f)
    
    def is_mutant_enabled(self, mutant_id):
        return self.config.get('enable_mutation', False)

plugin = MutationPlugin(Path(__file__).parent / 'mutants.json')

def is_mutant_enabled(mutant_id):
    return plugin.is_mutant_enabled(mutant_id)
'''
    }
    
    for filename, content in core_files.items():
        with open(support_dir / filename, 'w') as f:
            f.write(content)