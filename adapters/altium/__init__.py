"""
Altium Designer adapter
Imports/exports data between Altium and canonical IR
"""

from .importer import AltiumImporter
from .exporter import AltiumExporter

__all__ = ['AltiumImporter', 'AltiumExporter']
