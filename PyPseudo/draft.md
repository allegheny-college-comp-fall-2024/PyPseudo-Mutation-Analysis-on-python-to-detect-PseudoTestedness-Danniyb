1. **Working Directory Creation and Project Isolation**
```python
def setup_project_environment(project_path):
    """Creates isolated working copy of target project"""
    project_path = Path(project_path)
    working_dir = project_path.parent / f"{project_path.name}_pypseudo_work"
    working_dir.mkdir(exist_ok=True)
    
    # Copy project files preserving structure
    for item in project_path.glob("**/*"):
        if item.is_file():
            relative_path = item.relative_to(project_path)
            target_path = working_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)
```
Key Points:
- Uses `pathlib.Path` for cross-platform path handling
- Creates separate working directory using project name
- Preserves original project structure in working copy

2. **Support Code Injection**
```python
def copy_support_files(working_dir, mutants_config):
    """Copies minimal required support code"""
    support_dir = working_dir / '.pypseudo'
    support_dir.mkdir(exist_ok=True)
    
    # Only copy essential files
    with open(support_dir / 'mutants.json', 'w') as f:
        json.dump(mutants_config, f, indent=2)
        
    with open(support_dir / 'mutation_support.py', 'w') as f:
        f.write(minimal_support_code)  # Only core mutation functionality
```
Key Points:
- Creates hidden `.pypseudo` directory for support code
- Only copies minimal required functionality
- No dependency on tool's original location

3. **Dynamic Import Management**
```python
# Code injected into each instrumented file
support_code = """
import os
import sys
from pathlib import Path

_support_dir = Path(__file__).parent / '.pypseudo'
if _support_dir.exists():
    sys.path.insert(0, str(_support_dir))

from mutation_support import MutationPlugin, is_mutant_enabled
"""
```
Key Points:
- Uses `sys.path` manipulation for local imports
- Only affects instrumented files' runtime
- No global Python environment changes

4. **Assumptions and Requirements**:
- Target project must be valid Python
- Python's import system for dynamic path addition
- Working directory write permissions
- No conflicting `.pypseudo` directory in target

5. **Key Python Features Used**:
- `pathlib.Path`: Path manipulation
- `shutil`: File operations
- `sys.path`: Python import system
- `ast`: Code transformation
- `importlib`: Dynamic imports

6. **Independence Mechanisms**:
```plaintext
Original Structure:          Working Structure:
/project/                   /project_pypseudo_work/
└── code.py                ├── .pypseudo/
                          │   ├── mutation_support.py
                          │   └── mutants.json
                          └── code.py (instrumented)
```

This setup ensures:
- Tool code never needs to be in project's path
- Each project gets its own isolated support code
- No interference between different projects
- Original project remains untouched

