"""Bounded-context modules (ADR 0001).

Each module is a package with four layers: domain, application, infrastructure, api.
Boundaries are enforced by import-linter contracts in the root pyproject.toml.
"""
