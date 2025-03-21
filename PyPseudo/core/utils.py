import os
import shutil
import logging
import tomli
from pathlib import Path
import json

logger = logging.getLogger(__name__)

import os
import shutil
import logging
import importlib.util
from pathlib import Path
import json
import tomli  # For parsing TOML files
import subprocess
import sys

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
    
    # Copy project files maintaining directory structure
    for item in project_path.glob("**/*"):
        if item.is_file() and not item.name.startswith('__pycache__'):
            relative_path = item.relative_to(project_path)
            target_path = working_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)
    
    # Handle dependencies
    install_project_dependencies(working_dir)
            
    return working_dir

def install_project_dependencies(project_dir):
    """
    Install dependencies for the target project.
    
    Args:
        project_dir: Path to the working directory of the project
    """
    project_dir = Path(project_dir)
    
    # Check for pyproject.toml first (Poetry)
    pyproject_path = project_dir / "pyproject.toml"
    requirements_path = project_dir / "requirements.txt"
    
    if pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomli.load(f)
            
            logger.info("Installing dependencies from pyproject.toml")
            
            # Create a virtual environment for the project
            venv_dir = project_dir / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
            
            # Get the pip executable from the virtual environment
            pip_cmd = str(venv_dir / "bin" / "pip") if not os.name == "nt" else str(venv_dir / "Scripts" / "pip")
            
            # Install Poetry if using Poetry project
            if "tool" in pyproject_data and "poetry" in pyproject_data["tool"]:
                dependencies = []
                
                # Get dependencies from pyproject.toml
                if "dependencies" in pyproject_data["tool"]["poetry"]:
                    for dep, version in pyproject_data["tool"]["poetry"]["dependencies"].items():
                        if dep != "python":  # Skip python version constraint
                            if isinstance(version, str):
                                dependencies.append(f"{dep}{version}")
                            else:
                                dependencies.append(dep)
                
                # Install dependencies
                if dependencies:
                    cmd = [pip_cmd, "install"] + dependencies
                    logger.info(f"Running: {' '.join(cmd)}")
                    subprocess.run(cmd, check=True)
                    
                # Install development dependencies
                dev_dependencies = []
                if "group" in pyproject_data["tool"]["poetry"] and "dev" in pyproject_data["tool"]["poetry"]["group"]:
                    dev_deps = pyproject_data["tool"]["poetry"]["group"]["dev"]["dependencies"]
                    for dep, version in dev_deps.items():
                        if isinstance(version, str):
                            dev_dependencies.append(f"{dep}{version}")
                        else:
                            dev_dependencies.append(dep)
                
                if dev_dependencies:
                    cmd = [pip_cmd, "install"] + dev_dependencies
                    logger.info(f"Running: {' '.join(cmd)}")
                    subprocess.run(cmd, check=True)
            
            # Install the project itself in development mode
            subprocess.run([pip_cmd, "install", "-e", str(project_dir)], check=True)
            
        except Exception as e:
            logger.error(f"Error installing dependencies from pyproject.toml: {e}")
    
    # Fallback to requirements.txt
    elif requirements_path.exists():
        try:
            logger.info("Installing dependencies from requirements.txt")
            
            # Create a virtual environment for the project
            venv_dir = project_dir / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
            
            # Get the pip executable from the virtual environment
            pip_cmd = str(venv_dir / "bin" / "pip") if not os.name == "nt" else str(venv_dir / "Scripts" / "pip")
            
            # Install dependencies from requirements.txt
            subprocess.run([pip_cmd, "install", "-r", str(requirements_path)], check=True)
            
            # Install the project itself in development mode
            subprocess.run([pip_cmd, "install", "-e", str(project_dir)], check=True)
            
        except Exception as e:
            logger.error(f"Error installing dependencies from requirements.txt: {e}")
    else:
        logger.warning("No dependency files (pyproject.toml or requirements.txt) found")

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
    """Copy support files to the working directory"""
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
        