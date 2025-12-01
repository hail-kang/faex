"""AST parser for FastAPI router decorators and exception detection."""

import ast
from pathlib import Path

from faex.models import EndpointInfo, ExceptionLocation

# FastAPI HTTP method decorators
HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "trace"})


class FastAPIVisitor(ast.NodeVisitor):
    """AST visitor that extracts FastAPI endpoint information."""

    def __init__(self, file_path: Path, source: str) -> None:
        self.file_path = file_path
        self.source = source
        self.endpoints: list[EndpointInfo] = []
        self._current_function: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Process a function definition to check for FastAPI decorators."""
        for decorator in node.decorator_list:
            endpoint_info = self._parse_router_decorator(decorator, node)
            if endpoint_info:
                self.endpoints.append(endpoint_info)
                break

        self.generic_visit(node)

    def _parse_router_decorator(
        self, decorator: ast.expr, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> EndpointInfo | None:
        """Parse a decorator to extract FastAPI router information."""
        # Handle @router.get(...) or @app.get(...)
        if not isinstance(decorator, ast.Call):
            return None

        call = decorator
        method = self._get_http_method(call.func)
        if not method:
            return None

        # Extract path from first positional argument
        path: str | None = None
        if call.args and isinstance(call.args[0], ast.Constant):
            path = str(call.args[0].value)

        # Extract declared exceptions
        declared_exceptions = self._extract_exceptions_param(call)

        return EndpointInfo(
            file=self.file_path,
            line=func.lineno,
            function_name=func.name,
            method=method.upper(),
            path=path,
            declared_exceptions=declared_exceptions,
        )

    def _get_http_method(self, node: ast.expr) -> str | None:
        """Extract HTTP method from decorator call."""
        # @router.get or @app.get
        if isinstance(node, ast.Attribute) and node.attr in HTTP_METHODS:
            return node.attr

        # @get (direct import, less common)
        if isinstance(node, ast.Name) and node.id in HTTP_METHODS:
            return node.id

        return None

    def _extract_exceptions_param(self, call: ast.Call) -> list[str]:
        """Extract exception classes from the exceptions= parameter."""
        for keyword in call.keywords:
            if keyword.arg == "exceptions":
                return self._parse_exception_list(keyword.value)
        return []

    def _parse_exception_list(self, node: ast.expr) -> list[str]:
        """Parse a list of exception classes."""
        exceptions: list[str] = []

        if isinstance(node, ast.List):
            for element in node.elts:
                exc_name = self._get_exception_name(element)
                if exc_name:
                    exceptions.append(exc_name)

        return exceptions

    def _get_exception_name(self, node: ast.expr) -> str | None:
        """Get the name of an exception class from an AST node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            # Handle module.ExceptionClass
            parts = []
            current: ast.expr = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None


class ExceptionVisitor(ast.NodeVisitor):
    """AST visitor that detects raised exceptions in a function."""

    def __init__(self, file_path: Path, source: str) -> None:
        self.file_path = file_path
        self.source = source
        self.exceptions: list[ExceptionLocation] = []
        self._current_function: str | None = None

    def visit_Raise(self, node: ast.Raise) -> None:
        """Process a raise statement."""
        if node.exc is None:
            # Bare raise (re-raise), skip
            self.generic_visit(node)
            return

        exc_name = self._get_raised_exception_name(node.exc)
        if exc_name:
            self.exceptions.append(
                ExceptionLocation(
                    file=self.file_path,
                    line=node.lineno,
                    column=node.col_offset,
                    exception_class=exc_name,
                    in_function=self._current_function,
                )
            )

        self.generic_visit(node)

    def _get_raised_exception_name(self, node: ast.expr) -> str | None:
        """Get the exception class name from a raise expression."""
        # raise ExceptionClass() or raise ExceptionClass
        if isinstance(node, ast.Call):
            return self._get_class_name(node.func)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._get_class_name(node)
        return None

    def _get_class_name(self, node: ast.expr) -> str | None:
        """Extract class name from a node."""
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


def parse_file(file_path: Path) -> tuple[list[EndpointInfo], list[ExceptionLocation]]:
    """Parse a Python file and extract endpoint and exception information."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    # Find endpoints
    endpoint_visitor = FastAPIVisitor(file_path, source)
    endpoint_visitor.visit(tree)

    # Find all raised exceptions
    exception_visitor = ExceptionVisitor(file_path, source)
    exception_visitor.visit(tree)

    return endpoint_visitor.endpoints, exception_visitor.exceptions


def extract_function_exceptions(
    file_path: Path, func_node: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[ExceptionLocation]:
    """Extract exceptions raised directly within a function body."""
    source = file_path.read_text(encoding="utf-8")
    visitor = ExceptionVisitor(file_path, source)
    visitor._current_function = func_node.name

    for node in ast.walk(func_node):
        if isinstance(node, ast.Raise):
            visitor.visit_Raise(node)

    return visitor.exceptions
