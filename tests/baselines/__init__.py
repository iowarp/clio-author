"""Gated baseline harness: compares clio-author against reference impls / real PDFs.

Every test here is marked ``baseline`` (and/or ``live``) and is deselected by
the default ``addopts``. They skip -- never fail -- when fixtures, optional
dependencies, or network access are unavailable.
"""
