import os
import shutil
import logging
from pathlib import Path
import json
import sys
import site

logger = logging.getLogger(__name__)

def setup_project_environment(project_path):
    """
    Set up working environment for target project
    
    Args:
        project_path: Path to target project
    Returns:
        Path: working_dir
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

    # Copy project files maintaining directory structure
    for item in project_path.glob("**/*"):
        if item.is_file() and not item.name.startswith('__pycache__'):
            relative_path = item.relative_to(project_path)
            target_path = working_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)
    
    # Create a .pth file that will tell Python where to find pypseudo_instrumentation
    # This is more reliable than trying to copy the actual module
    with open(pypseudo_dir / 'pypseudo_paths.pth', 'w') as f:
        # Add the path to site-packages where poetry installed the module
        for path in site.getsitepackages():
            f.write(f"{path}\n")
        # Also add the path to the pypseudo_instrumentation source
        f.write(f"{Path(__file__).parent.parent.parent}\n")
        
    # Set PYTHONPATH to include the .pypseudo directory
    os.environ['PYTHONPATH'] = f"{str(pypseudo_dir)}:{os.environ.get('PYTHONPATH', '')}"
    
    logger.info(f"Set PYTHONPATH to include {pypseudo_dir}")
    
    return working_dir

def inject_mutation_support(target_file):
    """Inject necessary imports and support code into target file"""
    is_test_file = Path(target_file).name.startswith('test_') or 'test' in Path(target_file).name
    
    support_code = """
# Auto-generated mutation support code
import os
import sys
import pytest
from pathlib import Path

# Add parent directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Add .pypseudo directory to path
_support_dir = current_dir / '.pypseudo'
if _support_dir.exists():
    sys.path.insert(0, str(_support_dir))

# Import support modules
"""
    
    if is_test_file:
        support_code += """
from .pypseudo.mutation_support import MutationPlugin, is_mutant_enabled

@pytest.fixture(scope='session')
def plugin():
    # Set path to config file
    config_path = str(Path(__file__).parent / '.pypseudo' / 'mutants.json')
    os.environ['PYPSEUDO_CONFIG_FILE'] = config_path
    
    # Create and initialize plugin
    plugin = MutationPlugin(config_path)
    plugin.load_mutants()
    return plugin
"""
    else:
        support_code += """
from .pypseudo.mutation_support import is_mutant_enabled
"""
    
    with open(target_file, 'r') as f:
        content = f.read()
        
    with open(target_file, 'w') as f:
        f.write(support_code + '\n' + content)

def copy_support_files(working_dir, mutants_config):
    """Copy support files to the working directory"""
    support_dir = working_dir / '.pypseudo'
    support_dir.mkdir(exist_ok=True)
    
    # Create __init__.py to make it a package
    with open(support_dir / '__init__.py', 'w') as f:
        f.write('''# PyPseudo support package
# Import directly from mutation_support
from .mutation_support import is_mutant_enabled

__all__ = ['is_mutant_enabled']
''')
    
    # Write the config file
    with open(support_dir / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=2)
    
    # Find and copy mutation_support.py with correct nested package structure
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    # Updated locations to check the nested package structure
    possible_locations = [
        # Check nested package structure (Poetry standard)
        project_root.parent / 'pypseudo_instrumentation' / 'pypseudo_instrumentation' / 'mutation_support.py',
        project_root / 'pypseudo_instrumentation' / 'pypseudo_instrumentation' / 'mutation_support.py',
        
        # Also check older locations as fallback
        project_root.parent / 'pypseudo_instrumentation' / 'mutation_support.py',
        project_root / 'pypseudo_instrumentation' / 'mutation_support.py',
        Path.cwd().parent / 'pypseudo_instrumentation' / 'mutation_support.py',
        Path.cwd().parent / 'pypseudo_instrumentation' / 'pypseudo_instrumentation' / 'mutation_support.py',
    ]
    
    # Print debugging info to help locate the file
    logger.info(f"Current directory: {current_dir}")
    logger.info(f"Project root: {project_root}")
    
    for location in possible_locations:
        logger.info(f"Checking location: {location}")
        if location.exists():
            logger.info(f"Found mutation_support.py at {location}")
            shutil.copy2(location, support_dir / 'mutation_support.py')
            logger.info(f"Copied mutation_support.py to {support_dir}")
            return  # Exit function once file is found and copied
    
    # If no file is found, raise an error with more information
    logger.error("Could not find mutation_support.py in any expected location")
    logger.error("Searched locations:")
    for location in possible_locations:
        logger.error(f"  - {location}")
    
    # As a last resort, try to use the installed package path
    try:
        import pypseudo_instrumentation
        source_path = Path(pypseudo_instrumentation.__file__).parent / 'mutation_support.py'
        logger.info(f"Trying installed package: {source_path}")
        if source_path.exists():
            shutil.copy2(source_path, support_dir / 'mutation_support.py')
            logger.info(f"Copied mutation_support.py from installed package")
            return
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import pypseudo_instrumentation: {e}")
    
    raise FileNotFoundError("mutation_support.py not found")