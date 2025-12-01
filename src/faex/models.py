"""Data models for faex analysis results."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExceptionLocation:
    """Location where an exception is raised."""

    file: Path
    line: int
    column: int
    exception_class: str
    in_function: str | None = None

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}"
        if self.in_function:
            return f"{self.exception_class} (raised in {self.in_function} at {loc})"
        return f"{self.exception_class} (raised at line {self.line})"


@dataclass
class EndpointInfo:
    """Information about a FastAPI endpoint."""

    file: Path
    line: int
    function_name: str
    method: str  # GET, POST, PUT, DELETE, etc.
    path: str | None = None
    declared_exceptions: list[str] = field(default_factory=list)
    detected_exceptions: list[ExceptionLocation] = field(default_factory=list)

    @property
    def undeclared_exceptions(self) -> list[ExceptionLocation]:
        """Get exceptions that are raised but not declared."""
        declared_set = set(self.declared_exceptions)
        return [exc for exc in self.detected_exceptions if exc.exception_class not in declared_set]

    @property
    def unused_declarations(self) -> list[str]:
        """Get exceptions that are declared but not raised."""
        detected_set = {exc.exception_class for exc in self.detected_exceptions}
        return [exc for exc in self.declared_exceptions if exc not in detected_set]


@dataclass
class AnalysisResult:
    """Result of analyzing a file or project."""

    endpoints: list[EndpointInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if any endpoint has undeclared exceptions."""
        return any(ep.undeclared_exceptions for ep in self.endpoints)

    @property
    def total_undeclared(self) -> int:
        """Total count of undeclared exceptions."""
        return sum(len(ep.undeclared_exceptions) for ep in self.endpoints)

    @property
    def endpoints_with_issues(self) -> list[EndpointInfo]:
        """Get endpoints that have undeclared exceptions."""
        return [ep for ep in self.endpoints if ep.undeclared_exceptions]
