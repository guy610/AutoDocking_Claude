"""
AutoDock Pipeline – Iterative peptide hit optimization via AutoDock Vina.

Stages:
  0. Input preparation & initial docking
  1. Side-chain optimization
  2. Backbone optimization
  3. Sequence minimization (size reduction)

License note: this pipeline calls RDKit (BSD) and AutoDock Vina (Apache-2.0)
as external dependencies. No GPL-only code is embedded or modified.
"""

__version__ = "0.1.0"
