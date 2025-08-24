#!/usr/bin/env python3
"""
Test runner script for BridgeLambdas project.
Provides easy ways to run different types of tests with various options.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(command)}")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run(command, check=True, capture_output=False)
        print(f"\n✅ {description} completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} failed with exit code {e.returncode}")
        return False
    except KeyboardInterrupt:
        print(f"\n⏹️  {description} interrupted by user")
        return False


def run_unit_tests(verbose=False, coverage=False, specific_test=None):
    """Run unit tests."""
    command = ["python3", "-m", "pytest"]
    
    if specific_test:
        command.append(specific_test)
    else:
        command.append("tests/")
    
    if verbose:
        command.append("-v")
    
    if coverage:
        command.extend(["--cov=lambdas", "--cov-report=html", "--cov-report=term-missing"])
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, "Unit Tests")


def run_integration_tests(verbose=False):
    """Run integration tests."""
    command = ["python3", "-m", "pytest", "tests/", "-m", "integration"]
    
    if verbose:
        command.append("-v")
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, "Integration Tests")


def run_websocket_tests(verbose=False):
    """Run WebSocket-related tests."""
    command = ["python3", "-m", "pytest", "tests/", "-m", "websocket"]
    
    if verbose:
        command.append("-v")
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, "WebSocket Tests")


def run_database_tests(verbose=False):
    """Run database-related tests."""
    command = ["python3", "-m", "pytest", "tests/", "-m", "database"]
    
    if verbose:
        command.append("-v")
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, "Database Tests")


def run_auth_tests(verbose=False):
    """Run authentication-related tests."""
    command = ["python3", "-m", "pytest", "tests/", "-m", "auth"]
    
    if verbose:
        command.append("-v")
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, "Authentication Tests")


def run_specific_test_file(test_file, verbose=False):
    """Run a specific test file."""
    if not os.path.exists(test_file):
        print(f"❌ Test file not found: {test_file}")
        return False
    
    command = ["python3", "-m", "pytest", test_file]
    
    if verbose:
        command.append("-v")
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, f"Specific Test: {test_file}")


def run_all_tests(verbose=False, coverage=False):
    """Run all tests."""
    command = ["python3", "-m", "pytest", "tests/"]
    
    if verbose:
        command.append("-v")
    
    if coverage:
        command.extend(["--cov=lambdas", "--cov-report=html", "--cov-report=term-missing"])
    
    command.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    return run_command(command, "All Tests")


def install_test_dependencies():
    """Install test dependencies."""
    command = ["pip", "install", "-r", "requirements.txt"]
    return run_command(command, "Installing Test Dependencies")


def show_test_coverage():
    """Show test coverage report."""
    command = ["python3", "-m", "pytest", "--cov=lambdas", "--cov-report=html", "--cov-report=term-missing", "tests/"]
    return run_command(command, "Test Coverage Report")


def lint_code():
    """Run code linting."""
    command = ["python3", "-m", "flake8", "lambdas/", "tests/"]
    return run_command(command, "Code Linting")


def format_code():
    """Format code using black."""
    command = ["python3", "-m", "black", "lambdas/", "tests/"]
    return run_command(command, "Code Formatting")


def main():
    """Main function to parse arguments and run tests."""
    parser = argparse.ArgumentParser(
        description="Test runner for BridgeLambdas project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_tests.py                    # Run all tests
  python3 run_tests.py --unit             # Run only unit tests
  python3 run_tests.py --websocket       # Run WebSocket tests
  python3 run_tests.py --coverage        # Run tests with coverage
  python3 run_tests.py --verbose         # Run tests with verbose output
  python3 run_tests.py --file tests/test_db_utils.py  # Run specific test file
  python3 run_tests.py --install         # Install test dependencies
  python3 run_tests.py --lint            # Run code linting
  python3 run_tests.py --format          # Format code
        """
    )
    
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--websocket", action="store_true", help="Run WebSocket tests only")
    parser.add_argument("--database", action="store_true", help="Run database tests only")
    parser.add_argument("--auth", action="store_true", help="Run authentication tests only")
    parser.add_argument("--all", action="store_true", help="Run all tests (default)")
    parser.add_argument("--coverage", action="store_true", help="Run tests with coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--file", type=str, help="Run specific test file")
    parser.add_argument("--install", action="store_true", help="Install test dependencies")
    parser.add_argument("--lint", action="store_true", help="Run code linting")
    parser.add_argument("--format", action="store_true", help="Format code")
    parser.add_argument("--coverage-only", action="store_true", help="Show coverage report only")
    
    args = parser.parse_args()
    
    # Check if we're in the right directory
    if not os.path.exists("tests/") or not os.path.exists("lambdas/"):
        print("❌ Error: Please run this script from the project root directory")
        print("   (where 'tests/' and 'lambdas/' directories are located)")
        sys.exit(1)
    
    success = True
    
    # Handle different test types
    if args.install:
        success = install_test_dependencies()
    elif args.lint:
        success = lint_code()
    elif args.format:
        success = format_code()
    elif args.coverage_only:
        success = show_test_coverage()
    elif args.file:
        success = run_specific_test_file(args.file, args.verbose)
    elif args.unit:
        success = run_unit_tests(args.verbose, args.coverage)
    elif args.integration:
        success = run_integration_tests(args.verbose)
    elif args.websocket:
        success = run_websocket_tests(args.verbose)
    elif args.database:
        success = run_database_tests(args.verbose)
    elif args.auth:
        success = run_auth_tests(args.verbose)
    else:
        # Default: run all tests
        success = run_all_tests(args.verbose, args.coverage)
    
    if success:
        print("\n🎉 All operations completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Some operations failed. Check the output above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
