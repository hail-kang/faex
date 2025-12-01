# faex

**FastAPI Exception Validator** - A static analysis tool that validates exception declarations in FastAPI router endpoints.

## Overview

`faex` analyzes your FastAPI codebase to ensure all explicitly raised exceptions in endpoint handlers are properly declared in the router decorator's `exceptions` parameter. This helps maintain accurate API documentation and ensures clients are aware of all possible error responses.

## Problem Statement

In FastAPI, you can declare expected exceptions in router decorators:

```python
@router.get(
    "/summary",
    response_model=make_success_response_type(
        code=0, data_model=list[InfluencerSummaryElement], prefix="InfSummaryInfo"
    ),
    exceptions=[UnauthorizedException],
)
async def get_summary():
    if not user.is_authenticated:
        raise UnauthorizedException()  # Declared in exceptions=[]
    if not user.has_permission:
        raise ForbiddenException()     # Missing from exceptions=[]!
    return get_data()
```

Without tooling, it's easy to:
- Forget to declare exceptions when adding new error handling
- Leave stale exception declarations after refactoring
- Miss exceptions raised by called functions

`faex` solves this by statically analyzing your code and reporting discrepancies.

## Features

- **Static Analysis**: Analyzes Python AST to detect `raise` statements
- **Transitive Detection**: Follows function calls to detect exceptions raised in dependencies
- **FastAPI Integration**: Understands FastAPI router decorators and their `exceptions` parameter
- **CLI Tool**: Easy-to-use command-line interface
- **CI/CD Ready**: Exit codes suitable for automated pipelines
- **Configurable**: Customize analysis depth, ignored exceptions, and more

## Installation

```bash
# Using pip
pip install faex

# Using uv
uv add faex

# Using pipx (recommended for CLI usage)
pipx install faex
```

## Quick Start

```bash
# Analyze a single file
faex check app/routers/users.py

# Analyze a directory
faex check app/routers/

# Analyze entire project
faex check .

# Show detailed report
faex check app/ --verbose

# Output as JSON
faex check app/ --format json
```

## Usage

### Basic Commands

```bash
# Check for undeclared exceptions
faex check <path>

# List all detected exceptions in endpoints
faex list <path>

# Generate exception declarations
faex suggest <path>
```

### Options

```bash
faex check <path> [OPTIONS]

Options:
  --depth INT          Maximum call depth for transitive analysis (default: 3)
  --ignore CLASS       Exception classes to ignore (can be repeated)
  --format FORMAT      Output format: text, json, github (default: text)
  --strict             Fail on any undeclared exception
  --config FILE        Path to configuration file
  -v, --verbose        Show detailed analysis
  -q, --quiet          Only show errors
  --help               Show this message and exit
```

### Configuration File

Create a `faex.toml` or `pyproject.toml` with `[tool.faex]` section:

```toml
[tool.faex]
# Maximum depth for following function calls
depth = 3

# Exception classes to ignore globally
ignore = [
    "HTTPException",  # Generic FastAPI exception
    "ValidationError",  # Pydantic validation
]

# Paths to exclude from analysis
exclude = [
    "tests/",
    "**/test_*.py",
]

# Custom exception base classes to track
exception_bases = [
    "app.exceptions.BaseAPIException",
]
```

## Example Output

```
$ faex check app/routers/

app/routers/users.py:45 - get_user_profile
  Undeclared exceptions:
    - NotFoundException (raised at line 52)
    - ForbiddenException (raised in get_user_data at app/services/users.py:23)

app/routers/orders.py:78 - create_order
  Undeclared exceptions:
    - PaymentFailedException (raised in process_payment at app/services/payment.py:45)
    - InventoryException (raised in check_inventory at app/services/inventory.py:12)

Found 4 undeclared exceptions in 2 endpoints.
```

## How It Works

1. **Parse**: Parses Python files using AST to find FastAPI router decorators
2. **Extract**: Extracts declared exceptions from the `exceptions` parameter
3. **Analyze**: Analyzes endpoint function bodies for `raise` statements
4. **Trace**: Follows function calls to detect transitively raised exceptions
5. **Compare**: Compares declared vs. detected exceptions
6. **Report**: Reports discrepancies with file locations and call traces

## Integration

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/hail-kang/faex
    rev: v0.1.0
    hooks:
      - id: faex
        args: [check, --strict]
```

### GitHub Actions

```yaml
# .github/workflows/lint.yml
- name: Check FastAPI Exceptions
  run: |
    pip install faex
    faex check app/ --format github
```

### CI Exit Codes

- `0`: No issues found
- `1`: Undeclared exceptions found
- `2`: Configuration or parsing error

## Development

```bash
# Clone the repository
git clone https://github.com/hail-kang/faex.git
cd faex

# Create virtual environment and install dependencies
uv sync

# Run tests
uv run pytest

# Run type checking
uv run pyright

# Run linting
uv run ruff check .

# Run formatter
uv run ruff format .
```

## Requirements

- Python 3.10+
- FastAPI (for the projects being analyzed)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## Roadmap

- [ ] Support for `HTTPException` status code tracking
- [ ] Exception inheritance analysis
- [ ] Auto-fix capability to add missing declarations
- [ ] IDE plugins (VS Code, PyCharm)
- [ ] Support for other frameworks (Starlette, Litestar)
