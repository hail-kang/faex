"""Command-line interface for faex."""

import sys
from pathlib import Path

import click
from rich.console import Console

from faex import __version__
from faex.analyzer import analyze
from faex.output import RichFormatter, get_formatter

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="faex")
def main() -> None:
    """FastAPI Exception Validator - Validate exception declarations in FastAPI endpoints."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--depth", default=3, help="Maximum call depth for transitive analysis.")
@click.option("--ignore", multiple=True, help="Exception classes to ignore.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "github"]),
    default="text",
    help="Output format.",
)
@click.option("--strict", is_flag=True, help="Fail on any undeclared exception.")
@click.option("--config", type=click.Path(exists=True), help="Path to configuration file.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed analysis.")
@click.option("-q", "--quiet", is_flag=True, help="Only show errors.")
def check(
    path: str,
    depth: int,
    ignore: tuple[str, ...],
    output_format: str,
    strict: bool,
    config: str | None,
    verbose: bool,
    quiet: bool,
) -> None:
    """Check for undeclared exceptions in FastAPI endpoints."""
    target_path = Path(path)
    ignore_set = set(ignore)

    # Run analysis
    result = analyze(target_path, max_depth=depth, ignore_exceptions=ignore_set)

    # Handle errors
    if result.errors and not quiet:
        for error in result.errors:
            console.print(f"[yellow]Warning:[/yellow] {error}")

    # Output results
    if output_format == "text" and sys.stdout.isatty():
        # Use rich output for interactive terminals
        formatter = RichFormatter(console)
        formatter.print(result, verbose=verbose)
    else:
        # Use plain text formatter
        formatter = get_formatter(output_format)
        output = formatter.format(result, verbose=verbose)
        if output and not quiet:
            click.echo(output)

    # Exit code
    if result.has_issues:
        sys.exit(1)
    sys.exit(0)


@main.command("list")
@click.argument("path", type=click.Path(exists=True))
@click.option("--depth", default=3, help="Maximum call depth for transitive analysis.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed information.")
def list_exceptions(path: str, depth: int, verbose: bool) -> None:
    """List all detected exceptions in endpoints."""
    target_path = Path(path)

    result = analyze(target_path, max_depth=depth)

    if not result.endpoints:
        console.print("[yellow]No FastAPI endpoints found.[/yellow]")
        return

    for endpoint in result.endpoints:
        # Header
        location = f"[cyan]{endpoint.file}[/cyan]:[yellow]{endpoint.line}[/yellow]"
        if endpoint.path:
            console.print(
                f"\n{location} - [bold]{endpoint.method}[/bold] {endpoint.path} "
                f"([dim]{endpoint.function_name}[/dim])"
            )
        else:
            console.print(f"\n{location} - [bold]{endpoint.function_name}[/bold]")

        # Declared
        if endpoint.declared_exceptions:
            console.print("  [green]Declared:[/green]")
            for exc in endpoint.declared_exceptions:
                console.print(f"    [green]✓[/green] {exc}")
        else:
            console.print("  [dim]Declared: (none)[/dim]")

        # Detected
        if endpoint.detected_exceptions:
            console.print("  [blue]Detected:[/blue]")
            for exc in endpoint.detected_exceptions:
                status = (
                    "[green]✓[/green]"
                    if exc.exception_class in endpoint.declared_exceptions
                    else "[red]✗[/red]"
                )
                if exc.in_function:
                    console.print(
                        f"    {status} {exc.exception_class} "
                        f"[dim](in {exc.in_function} at line {exc.line})[/dim]"
                    )
                else:
                    console.print(
                        f"    {status} {exc.exception_class} [dim](line {exc.line})[/dim]"
                    )
        else:
            console.print("  [dim]Detected: (none)[/dim]")

    # Summary
    console.print()
    console.print(f"[dim]Total endpoints: {len(result.endpoints)}[/dim]")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--depth", default=3, help="Maximum call depth for transitive analysis.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "diff"]),
    default="text",
    help="Output format.",
)
def suggest(path: str, depth: int, output_format: str) -> None:
    """Generate exception declarations for endpoints."""
    target_path = Path(path)

    result = analyze(target_path, max_depth=depth)

    if not result.endpoints_with_issues:
        console.print("[green]✓ All exceptions are properly declared.[/green]")
        return

    for endpoint in result.endpoints_with_issues:
        location = f"{endpoint.file}:{endpoint.line}"
        console.print(f"\n[cyan]{location}[/cyan] - [bold]{endpoint.function_name}[/bold]")

        # Generate suggested exceptions list
        all_exceptions = set(endpoint.declared_exceptions)
        for exc in endpoint.detected_exceptions:
            all_exceptions.add(exc.exception_class)

        sorted_exceptions = sorted(all_exceptions)

        if output_format == "diff":
            # Show diff-like output
            console.print("  [red]- exceptions=[{}][/red]".format(
                ", ".join(endpoint.declared_exceptions) if endpoint.declared_exceptions else ""
            ))
            console.print("  [green]+ exceptions=[{}][/green]".format(
                ", ".join(sorted_exceptions)
            ))
        else:
            # Show suggested code
            console.print("  [yellow]Suggested:[/yellow]")
            console.print(f"    exceptions=[{', '.join(sorted_exceptions)}]")

            # Show what's being added
            new_exceptions = [
                exc.exception_class
                for exc in endpoint.undeclared_exceptions
            ]
            if new_exceptions:
                console.print(f"  [dim]Adding: {', '.join(new_exceptions)}[/dim]")


if __name__ == "__main__":
    main()
