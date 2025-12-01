"""Analyzer for detecting exceptions in FastAPI endpoints with transitive analysis."""

import ast
from pathlib import Path

from faex.models import AnalysisResult, EndpointInfo, ExceptionLocation
from faex.parser import HTTP_METHODS


class FunctionRegistry:
    """Registry of function definitions for transitive analysis."""

    def __init__(self) -> None:
        self._functions: dict[str, tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        self._parsed_files: dict[Path, ast.AST] = {}

    def register_file(self, file_path: Path) -> None:
        """Parse and register all functions from a file."""
        if file_path in self._parsed_files:
            return

        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
            self._parsed_files[file_path] = tree

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Use simple name for now; could be improved with module-qualified names
                    self._functions[node.name] = (file_path, node)
        except (SyntaxError, UnicodeDecodeError):
            pass

    def get_function(
        self, name: str
    ) -> tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef] | None:
        """Get a function definition by name."""
        return self._functions.get(name)


class EndpointAnalyzer:
    """Analyzes FastAPI endpoints for exception declarations."""

    def __init__(self, max_depth: int = 3, ignore_exceptions: set[str] | None = None) -> None:
        self.max_depth = max_depth
        self.ignore_exceptions = ignore_exceptions or set()
        self._registry = FunctionRegistry()
        self._call_cache: dict[str, list[ExceptionLocation]] = {}

    def analyze_path(self, path: Path) -> AnalysisResult:
        """Analyze a file or directory for FastAPI endpoints."""
        result = AnalysisResult()

        if path.is_file():
            self._analyze_file(path, result)
        elif path.is_dir():
            for py_file in path.rglob("*.py"):
                self._analyze_file(py_file, result)

        return result

    def _analyze_file(self, file_path: Path, result: AnalysisResult) -> None:
        """Analyze a single Python file."""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            result.errors.append(f"Syntax error in {file_path}: {e}")
            return
        except UnicodeDecodeError as e:
            result.errors.append(f"Encoding error in {file_path}: {e}")
            return

        # Register functions for transitive analysis
        self._registry.register_file(file_path)

        # Find and analyze endpoints
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                endpoint = self._check_for_endpoint(node, file_path, source)
                if endpoint:
                    # Detect exceptions in the endpoint
                    exceptions = self._analyze_function(file_path, node, depth=0)
                    endpoint.detected_exceptions = [
                        exc
                        for exc in exceptions
                        if exc.exception_class not in self.ignore_exceptions
                    ]
                    result.endpoints.append(endpoint)

    def _check_for_endpoint(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        source: str,
    ) -> EndpointInfo | None:
        """Check if a function is a FastAPI endpoint and extract its info."""
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            method = self._get_http_method(decorator.func)
            if not method:
                continue

            # Extract path
            path: str | None = None
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = str(decorator.args[0].value)

            # Extract declared exceptions
            declared = self._extract_declared_exceptions(decorator)

            return EndpointInfo(
                file=file_path,
                line=node.lineno,
                function_name=node.name,
                method=method.upper(),
                path=path,
                declared_exceptions=declared,
            )

        return None

    def _get_http_method(self, node: ast.expr) -> str | None:
        """Extract HTTP method from decorator."""
        if isinstance(node, ast.Attribute) and node.attr in HTTP_METHODS:
            return node.attr
        if isinstance(node, ast.Name) and node.id in HTTP_METHODS:
            return node.id
        return None

    def _extract_declared_exceptions(self, decorator: ast.Call) -> list[str]:
        """Extract declared exceptions from decorator's exceptions parameter."""
        for keyword in decorator.keywords:
            if keyword.arg == "exceptions":
                return self._parse_exception_list(keyword.value)
        return []

    def _parse_exception_list(self, node: ast.expr) -> list[str]:
        """Parse a list of exception classes."""
        exceptions: list[str] = []
        if isinstance(node, ast.List):
            for element in node.elts:
                name = self._get_name(element)
                if name:
                    exceptions.append(name)
        return exceptions

    def _get_name(self, node: ast.expr) -> str | None:
        """Get name from a Name or Attribute node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = []
            current: ast.expr = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    def _analyze_function(
        self,
        file_path: Path,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        depth: int,
        visited: set[str] | None = None,
    ) -> list[ExceptionLocation]:
        """Analyze a function for raised exceptions, including transitive calls."""
        if visited is None:
            visited = set()

        if func.name in visited:
            return []
        visited.add(func.name)

        exceptions: list[ExceptionLocation] = []

        for node in ast.walk(func):
            # Direct raise statements
            if isinstance(node, ast.Raise) and node.exc:
                exc_name = self._get_raised_exception(node.exc)
                if exc_name:
                    exceptions.append(
                        ExceptionLocation(
                            file=file_path,
                            line=node.lineno,
                            column=node.col_offset,
                            exception_class=exc_name,
                            in_function=None,  # Direct raise in endpoint
                        )
                    )

            # Function calls - transitive analysis
            if isinstance(node, ast.Call) and depth < self.max_depth:
                call_name = self._get_call_name(node)
                if call_name and call_name not in visited:
                    transitive = self._analyze_called_function(
                        call_name, depth + 1, visited.copy()
                    )
                    exceptions.extend(transitive)

        return exceptions

    def _get_raised_exception(self, node: ast.expr) -> str | None:
        """Get exception class name from raise expression."""
        if isinstance(node, ast.Call):
            return self._get_name(node.func)
        return self._get_name(node)

    def _get_call_name(self, call: ast.Call) -> str | None:
        """Get the function name from a call node."""
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            # For method calls like obj.method(), just get method name
            return call.func.attr
        return None

    def _analyze_called_function(
        self, func_name: str, depth: int, visited: set[str]
    ) -> list[ExceptionLocation]:
        """Analyze a called function for exceptions."""
        # Check cache
        cache_key = f"{func_name}:{depth}"
        if cache_key in self._call_cache:
            return self._call_cache[cache_key]

        result = self._registry.get_function(func_name)
        if not result:
            return []

        file_path, func_node = result
        exceptions = self._analyze_function(file_path, func_node, depth, visited)

        # Update in_function for transitive exceptions
        for exc in exceptions:
            if exc.in_function is None:
                exc.in_function = func_name

        self._call_cache[cache_key] = exceptions
        return exceptions


def analyze(
    path: Path,
    max_depth: int = 3,
    ignore_exceptions: set[str] | None = None,
) -> AnalysisResult:
    """Analyze a path for FastAPI endpoint exception issues."""
    analyzer = EndpointAnalyzer(max_depth=max_depth, ignore_exceptions=ignore_exceptions)
    return analyzer.analyze_path(path)
