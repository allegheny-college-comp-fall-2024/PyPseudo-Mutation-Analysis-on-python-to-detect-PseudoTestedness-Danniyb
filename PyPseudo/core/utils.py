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
    
    # Create __init__.py to make it a package
    with open(support_dir / '__init__.py', 'w') as f:
        f.write('# PyPseudo support package')
    
    # Write the config file
    with open(support_dir / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=2)
    
    # We no longer need to copy mutation_support.py
    # as it will be imported from the package