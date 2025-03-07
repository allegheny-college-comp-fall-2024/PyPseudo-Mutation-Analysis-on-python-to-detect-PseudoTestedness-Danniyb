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
   git clone hgit@github.com:allegheny-college-comp-fall-2024/PyPseudo-Mutation-Analysis-on-python-to-detect-PseudoTestedness-Danniyb.git
   cd pypseudo
   ```

2. Install the main PyPseudo tool:
   ```bash
   pip install -e .
   ```

3. Install the instrumentation support package:
   ```bash
   cd pypseudo_instrumentation
   pip install -e .
   cd ..
   ```

## Usage

PyPseudo has several operation modes:

### 1. Instrument a Project

First, instrument the project with mutations:

```bash
# Instrument with XMT (Extreme Mutation Testing)
python -m cli.main --instrument --xmt --project-path=/path/to/project --mutant-file=config/mutants.json

# Instrument with SDL (Statement Deletion)
python -m cli.main --instrument --sdl --project-path=/path/to/project --mutant-file=config/mutants.json

# Instrument with both XMT and SDL
python -m cli.main --instrument --xmt --sdl --project-path=/path/to/project --mutant-file=config/mutants.json
```

### 2. Run Tests with Mutations

After instrumentation, run tests with mutations enabled:

```bash
# Run with XMT mutations
python -m cli.main --run --xmt --project-path=/path/to/project --mutant-file=config/mutants.json

# Run with SDL mutations
python -m cli.main --run --sdl --project-path=/path/to/project --mutant-file=config/mutants.json

# Run with both XMT and SDL
python -m cli.main --run --xmt --sdl --project-path=/path/to/project --mutant-file=config/mutants.json
```

### 3. Run All Mutations Efficiently

To run all mutations grouped by test coverage (more efficient):

```bash
python -m cli.main --run-all-mutations --project-path=/path/to/project --mutant-file=config/mutants.json
```

This optimized mode:
1. Collects test coverage information first
2. Groups mutations by which tests cover them
3. Runs each test with all its covered mutations at once
4. Generates a comprehensive report

### 4. List Available Mutations

To see all mutations available in a project:

```bash
python -m cli.main --list-mutations --project-path=/path/to/project --mutant-file=config/mutants.json
```

### 5. Run with Specific Mutation

To test with a specific mutation:

```bash
python -m cli.main --run --enable-mutations --single-mutant=xmt_add_1 --project-path=/path/to/project --mutant-file=config/mutants.json
```

### 6. Restore Project

To restore a project to its original state:

```bash
python -m cli.main --restore --project-path=/path/to/project --mutant-file=config/mutants.json
```

## Command Line Options

```
--instrument         Instrument code with mutations
--run                Run mutation testing
--restore            Restore code to original state
--list-mutations     List all available mutation points
--run-all-mutations  Run optimized mutation testing by test coverage

--project-path PATH  Path to the project to analyze
--mutant-file FILE   Path to the mutation configuration file
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

Example:
```python
# Original function
def add(a, b):
    result = a + b
    return result

# XMT mutation
def add(a, b):
    if is_mutant_enabled('xmt_add_1'):
        print('XMT: Removing body of function add')
        return 0  # Default return value
    result = a + b
    return result
```

### Statement Deletion (SDL)

Removes individual statements to identify statements that are executed but not verified by tests.

Example:
```python
# Original code
if condition:
    do_something()
    log_action()  # This might be pseudo-tested

# SDL mutation
if condition:
    do_something()
    if is_mutant_enabled('sdl_if_1'):
        print('SDL: Skipping statement')
        pass
    else:
        log_action()
```

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

## Interpreting Results

After running PyPseudo, you'll get a report showing:

- **Killed Mutations**: Code that is properly tested (tests fail when it's mutated)
- **Survived Mutations**: Pseudo-tested code (tests pass even when it's mutated)

Focus on fixing the pseudo-tested code by:
1. Adding assertions that verify its behavior
2. Creating new tests that specifically verify it
3. Removing truly unused code

## Limitations

PyPseudo may face challenges with:
- Complex Python libraries that use metaclasses (use `--safe-mode`)
- Projects with custom test runners
- Code with extensive metaprogramming
- Projects that heavily rely on C extensions

## Troubleshooting

### Module Not Found Errors

If you see `ModuleNotFoundError: No module named 'pypseudo_instrumentation'`:

```bash
cd pypseudo_instrumentation
pip install -e .
```

### Metaclass Conflicts

If you encounter "metaclass conflicts" with complex libraries:

```bash
python -m cli.main --instrument --xmt --safe-mode --project-path=/path/to/project --mutant-file=config/mutants.json
```

### Test Collection Errors

If pytest can't collect tests after instrumentation, check:
1. Python path issues (try `export PYTHONPATH=/path/to/project_pypseudo_work`)
2. Import errors in test files
3. Compatibility with your pytest plugins

## Contributing

Contributions are welcome! Please feel free to open issues, submit pull requests, or suggest new features.

## License

This project is licensed under the MIT License - see the LICENSE file for details.