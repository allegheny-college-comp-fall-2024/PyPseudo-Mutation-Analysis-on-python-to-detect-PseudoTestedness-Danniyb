# PyPseudo

PyPseudo is a mutation testing tool for Python that identifies pseudo-tested code - code that is executed by tests but not actually verified by them. By using extreme mutation testing (XMT) and statement deletion (SDL), PyPseudo helps you identify weaknesses in your test suite and improve testing quality.

## What is Pseudo-Tested Code?

Pseudo-tested code is code that's covered by test cases, but these tests don't actually verify its functionality. For example:

```python
def add(a, b):
    # This function has a bug but tests don't catch it
    result = a + b
    return 0 if result == 0 else result

def test_add_zero():
    # This test only verifies zero case, not general addition
    assert add(0, 0) == 0
```

Even though the test covers 100% of the code, it doesn't verify that the function correctly adds two numbers. PyPseudo identifies such issues through mutation testing techniques.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/PyPseudo-Mutation-Analysis-on-python-to-detect-PseudoTestedness.git
   cd pypseudo
   ```

2. Install the main PyPseudo tool:
   ```bash
   poetry install
   ```

3. Install the instrumentation support package:
   ```bash
   cd pypseudo_instrumentation
   poetry install
   cd ..
   ```

## Usage

PyPseudo has several operation modes:

### 1. Instrument a Project

First, instrument the project with mutations:

```bash
# Instrument with XMT (Extreme Mutation Testing)
poetry run pypseudo --instrument --xmt --project-path=/path/to/project

# Instrument with SDL (Statement Deletion)
poetry run pypseudo --instrument --sdl --project-path=/path/to/project

# Instrument with both XMT and SDL
poetry run pypseudo --instrument --xmt --sdl --project-path=/path/to/project
```

Example output:
```
$ poetry run pypseudo --instrument --xmt --sdl --project-path=../../../simplePro
Using default mutant file: /Users/danielbekele/senior/comp/PyPseudo-Mutation-Analysis-on-python-to-detect-PseudoTestedness-Danniyb/pypseudo/config/mutants.json

=== Debug: Filter Mutations Start ===
Initial mutants_data: {
  "enable_mutation": false,
  "enabled_mutants": [
    {
      "type": "xmt",
      "target": "*"
    },
    {
      "type": "sdl",
      "target": [
        "for",
        "if",
        "while",
        "return",
        "try"
      ]
    }
  ]
}
2025-03-21 09:25:09,424 - root - INFO - Running instrumentation...
2025-03-21 09:25:09,424 - core.instrumentation - INFO - Installing required packages in working directory...
2025-03-21 09:25:09,739 - core.instrumentation - INFO - Required packages installed successfully.
2025-03-21 09:25:09,742 - core.utils - WARNING - No dependency files (pyproject.toml or requirements.txt) found
2025-03-21 09:25:09,744 - core.instrumentation - INFO - Starting code instrumentation
2025-03-21 09:25:09,744 - core.instrumentation - INFO - Initialized with targets - XMT: {'*'}, SDL: {'for', 'try', 'if', 'while', 'return'}
...
2025-03-21 09:25:09,748 - root - INFO - Instrumentation complete
```

### 2. Run Tests with Mutations

After instrumentation, run tests with mutations enabled:

```bash
# Run with XMT mutations
poetry run pypseudo --run --xmt --project-path=/path/to/project

# Run with SDL mutations
poetry run pypseudo --run --sdl --project-path=/path/to/project

# Run with both XMT and SDL
poetry run pypseudo --run --xmt --sdl --project-path=/path/to/project
```

### 3. Run All Mutations Efficiently

To run all mutations grouped by test coverage (more efficient):

```bash
poetry run pypseudo --run-all-mutations --project-path=/path/to/project
```

This optimized mode:
1. Collects test coverage information first
2. Groups mutations by which tests cover them
3. Runs each test with all its covered mutations at once
4. Generates a comprehensive report

### 4. List Available Mutations

To see all mutations available in a project:

```bash
poetry run pypseudo --list-mutations --project-path=/path/to/project
```

### 5. Run with Specific Mutation

To test with a specific mutation:

```bash
poetry run pypseudo --run --enable-mutations --single-mutant=xmt_add_1 --project-path=/path/to/project
```

### 6. Restore Project

To restore a project to its original state:

```bash
poetry run pypseudo --restore --project-path=/path/to/project
```

## Command Line Options

```
--instrument         Instrument code with mutations
--run                Run mutation testing
--restore            Restore code to original state
--list-mutations     List all available mutation points
--run-all-mutations  Run optimized mutation testing by test coverage

--project-path PATH  Path to the project to analyze
--mutant-file FILE   Path to the mutation configuration file (optional)
--xmt                Use extreme mutation testing
--sdl                Use statement deletion testing
--enable-mutations   Enable mutations during test run
--disable-mutations  Disable all mutations during test run
--single-mutant MUT  Run with only specified mutant (e.g., "xmt_add_1")

--json-report        Generate a JSON report
--json-report-file F Path to save the JSON report
--cov MODULE         Module or directory to measure coverage for
--cov-report FMT     Coverage report format
--safe-mode          Use conservative instrumentation for complex libraries
```

## Mutation Types

PyPseudo supports two types of mutations:

### Extreme Mutation Testing (XMT)

Removes entire function bodies and replaces them with default return values. This identifies functions that are executed by tests but whose results aren't actually verified.

Example from an instrumented file:
```python
def add(self, a, b):
    if is_mutant_enabled('xmt_add_calculator.py_1'):
        print('XMT: Removing body of function add in calculator.py')
        return None
    result = a + b
    return 0 if result == 0 else result
```

### Statement Deletion (SDL)

Removes individual statements to identify statements that are executed but not verified by tests.

Example from an instrumented file:
```python
if is_mutant_enabled('sdl_if_calculator.py_special_multiply_1'):
    print('SDL: Skipping if statement')
    pass
elif result > 1000:
    result += 1
```

## Mutation Configuration

PyPseudo uses a JSON configuration file to define which mutations to apply. The default file structure looks like:

```json
{
  "enable_mutation": false,
  "enabled_mutants": [
    {
      "type": "xmt",
      "target": "*"
    },
    {
      "type": "sdl",
      "target": [
        "for",
        "if",
        "while",
        "return",
        "try"
      ]
    }
  ]
}
```

This configuration allows you to:
- Enable/disable all mutations
- Target specific types of statements for SDL mutations
- Target specific functions or use wildcards for XMT mutations

## Architecture

PyPseudo consists of several components:

1. **CLI Interface** (`cli/main.py`): Command-line interface for the tool
2. **Instrumentation Engine** (`core/instrumentation.py`): Code instrumenter that adds mutations
3. **Mutation Plugin** (`core/mutation_plugin.py`): Pytest plugin for controlling mutations
4. **Support Package** (`pypseudo_instrumentation/`): Provides runtime mutation control

The tool works by:
1. Creating a working copy of the project
2. Instrumenting source files with mutation checks
3. Running tests with specific mutations enabled
4. Identifying which mutations cause test failures and which don't

## How Instrumentation Works

When PyPseudo instruments a file, it adds imports at the top of each file:

```python
import os
from pathlib import Path
from pypseudo_instrumentation import is_mutant_enabled
os.environ['PYPSEUDO_CONFIG_FILE'] = str(Path(__file__).parent / '.pypseudo' / 'mutants.json')
```

Then, for each function and target statement, it adds conditional checks to enable or disable mutations at runtime.

## Interpreting Results

After running PyPseudo, you'll get a report showing:

- **Killed Mutations**: Code that is properly tested (tests fail when it's mutated)
- **Survived Mutations**: Pseudo-tested code (tests pass even when it's mutated)

Focus on fixing the pseudo-tested code by:
1. Adding assertions that verify its behavior
2. Creating new tests that specifically verify it
3. Removing truly unused code

## Troubleshooting

### Module Not Found Errors

If you see `ModuleNotFoundError: No module named 'pypseudo_instrumentation'`:

```bash
cd pypseudo_instrumentation
poetry install
```

### Test Collection Errors

If pytest can't collect tests after instrumentation, check:
1. Python path issues (try setting `PYTHONPATH` appropriately)
2. Import errors in test files
3. Compatibility with your pytest plugins

## Contributing

Contributions are welcome! Please feel free to open issues, submit pull requests, or suggest new features.

## License

This project is licensed under the MIT License - see the LICENSE file for details.