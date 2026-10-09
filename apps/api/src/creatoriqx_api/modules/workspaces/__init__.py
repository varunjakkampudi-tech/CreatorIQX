"""Workspaces bounded context: tenants, memberships and first-login bootstrap (P0-053).

This is the reference module for the hexagonal layout (ADR 0001): ``domain``
holds pure rules, ``application`` orchestrates through ports, ``infrastructure``
implements the ports with SQLAlchemy, and ``api`` exposes routes (added in P0-054).
"""
