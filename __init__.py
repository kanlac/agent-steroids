"""Agent Steroids repository marker for Hermes installs.

This file intentionally does not define a root Hermes plugin.  It prevents the
Hermes installer from warning about a repository without Python plugin files;
actual selectable Hermes plugins are discovered from the root-level shim
directories: ``steroids/`` and ``chrome/``.
"""
