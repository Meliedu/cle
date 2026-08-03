"""Offline operator scripts.

A real package, deliberately. Without ``__init__.py`` this directory is still
importable two ways -- as bare top-level modules when it is on ``sys.path``,
and as ``scripts.x`` via implicit namespace packaging when ``backend/`` is --
and the two produce *separate copies* of every module. Two copies means two
``ExtractError`` classes, so an ``except ExtractError`` in one style silently
fails to catch the other's exception, and ``isinstance`` checks across the
boundary quietly return False.

Making it a package collapses that to one import path. Entry points put
``backend/`` on ``sys.path`` and everything here imports ``scripts.<module>``.
"""
