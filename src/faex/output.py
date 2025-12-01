"""Output formatters for faex analysis results."""

import json
from abc import ABC, abstractmethod

from rich.console import Console
from rich.table import Table

from faex.models import AnalysisResult, EndpointInfo


class OutputFormatter(ABC):
    """Base class for output formatters."""

    @abstractmethod
    def format(self, result: AnalysisResult, verbose: bool = False) -> str:
        """Format the analysis result."""
        pass


class TextFormatter(OutputFormatter):
    """Plain text output formatter."""

    def format(self, result: AnalysisResult, verbose: bool = False) -> str:
        lines: list[str] = []

        if not result.endpoints:
            return "No FastAPI endpoints found."

        endpoints_with_issues = result.endpoints_with_issues

        if not endpoints_with_issues:
            if verbose:
                lines.append(f"Analyzed {len(result.endpoints)} endpoints.")
            lines.append("No undeclared exceptions found.")
            return "\n".join(lines)

        for endpoint in endpoints_with_issues:
            lines.append(self._format_endpoint(endpoint, verbose))

        # Summary
        lines.append("")
        total = result.total_undeclared
        ep_count = len(endpoints_with_issues)
        lines.append(
            f"Found {total} undeclared exception{'s' if total != 1 else ''} "
            f"in {ep_count} endpoint{'s' if ep_count != 1 else ''}."
        )

        return "\n".join(lines)

    def _format_endpoint(self, endpoint: EndpointInfo, verbose: bool) -> str:
        lines: list[str] = []

        # Header
        location = f"{endpoint.file}:{endpoint.line}"
        header = f"{location} - {endpoint.function_name}"
        if endpoint.path:
            header = f"{location} - {endpoint.method} {endpoint.path} ({endpoint.function_name})"
        lines.append(header)

        # Undeclared exceptions
        lines.append("  Undeclared exceptions:")
        for exc in endpoint.undeclared_exceptions:
            if exc.in_function:
                lines.append(
                    f"    - {exc.exception_class} "
                    f"(raised in {exc.in_function} at {exc.file}:{exc.line})"
                )
            else:
                lines.append(f"    - {exc.exception_class} (raised at line {exc.line})")

        if verbose and endpoint.declared_exceptions:
            lines.append("  Declared exceptions:")
            for exc in endpoint.declared_exceptions:
                lines.append(f"    - {exc}")

        lines.append("")
        return "\n".join(lines)


class JsonFormatter(OutputFormatter):
    """JSON output formatter."""

    def format(self, result: AnalysisResult, verbose: bool = False) -> str:
        data = {
            "summary": {
                "total_endpoints": len(result.endpoints),
                "endpoints_with_issues": len(result.endpoints_with_issues),
                "total_undeclared": result.total_undeclared,
            },
            "endpoints": [],
            "errors": result.errors,
        }

        for endpoint in result.endpoints:
            if not verbose and not endpoint.undeclared_exceptions:
                continue

            ep_data = {
                "file": str(endpoint.file),
                "line": endpoint.line,
                "function": endpoint.function_name,
                "method": endpoint.method,
                "path": endpoint.path,
                "declared_exceptions": endpoint.declared_exceptions,
                "undeclared_exceptions": [
                    {
                        "class": exc.exception_class,
                        "file": str(exc.file),
                        "line": exc.line,
                        "in_function": exc.in_function,
                    }
                    for exc in endpoint.undeclared_exceptions
                ],
            }
            data["endpoints"].append(ep_data)

        return json.dumps(data, indent=2)


class GithubFormatter(OutputFormatter):
    """GitHub Actions annotation format."""

    def format(self, result: AnalysisResult, verbose: bool = False) -> str:
        lines: list[str] = []

        for endpoint in result.endpoints_with_issues:
            for exc in endpoint.undeclared_exceptions:
                # GitHub Actions workflow command format
                if exc.in_function:
                    message = (
                        f"Undeclared exception '{exc.exception_class}' "
                        f"raised in {exc.in_function}"
                    )
                else:
                    message = f"Undeclared exception '{exc.exception_class}'"

                lines.append(
                    f"::error file={endpoint.file},line={endpoint.line},"
                    f"title=Undeclared Exception::{message}"
                )

        return "\n".join(lines)


class RichFormatter:
    """Rich console output formatter."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def print(self, result: AnalysisResult, verbose: bool = False) -> None:
        """Print the analysis result using rich formatting."""
        if not result.endpoints:
            self.console.print("[yellow]No FastAPI endpoints found.[/yellow]")
            return

        endpoints_with_issues = result.endpoints_with_issues

        if not endpoints_with_issues:
            if verbose:
                self.console.print(f"[dim]Analyzed {len(result.endpoints)} endpoints.[/dim]")
            self.console.print("[green]✓ No undeclared exceptions found.[/green]")
            return

        for endpoint in endpoints_with_issues:
            self._print_endpoint(endpoint, verbose)

        # Summary table
        self.console.print()
        table = Table(show_header=False, box=None)
        table.add_row(
            "[bold red]Summary:[/bold red]",
            f"{result.total_undeclared} undeclared exception(s) "
            f"in {len(endpoints_with_issues)} endpoint(s)",
        )
        self.console.print(table)

    def _print_endpoint(self, endpoint: EndpointInfo, verbose: bool) -> None:
        # Header
        location = f"[cyan]{endpoint.file}[/cyan]:[yellow]{endpoint.line}[/yellow]"
        if endpoint.path:
            self.console.print(
                f"\n{location} - [bold]{endpoint.method}[/bold] {endpoint.path} "
                f"([dim]{endpoint.function_name}[/dim])"
            )
        else:
            self.console.print(f"\n{location} - [bold]{endpoint.function_name}[/bold]")

        # Undeclared exceptions
        self.console.print("  [red]Undeclared exceptions:[/red]")
        for exc in endpoint.undeclared_exceptions:
            if exc.in_function:
                self.console.print(
                    f"    [red]•[/red] {exc.exception_class} "
                    f"[dim](raised in {exc.in_function} at {exc.file}:{exc.line})[/dim]"
                )
            else:
                self.console.print(
                    f"    [red]•[/red] {exc.exception_class} "
                    f"[dim](raised at line {exc.line})[/dim]"
                )

        if verbose and endpoint.declared_exceptions:
            self.console.print("  [green]Declared exceptions:[/green]")
            for exc in endpoint.declared_exceptions:
                self.console.print(f"    [green]•[/green] {exc}")


def get_formatter(format_name: str) -> OutputFormatter:
    """Get a formatter by name."""
    formatters: dict[str, type[OutputFormatter]] = {
        "text": TextFormatter,
        "json": JsonFormatter,
        "github": GithubFormatter,
    }
    formatter_class = formatters.get(format_name, TextFormatter)
    return formatter_class()
