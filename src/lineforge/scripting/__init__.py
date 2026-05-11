"""atlc2 ``.txt`` script-file interpreter.

The atlc2 manual describes a small language used to drive the GUI from a text
file. Commands like ``twinlead``, ``coaxial``, ``solve``, ``sweep``, etc. set
edit-box values and trigger solves. lineforge implements a subset matching the
documented commands, with output files matching atlc2's naming
(``<name> Inductances.txt``, ``<name> Capacitances.txt``, etc.).
"""

from __future__ import annotations

from lineforge.scripting.atlc2_script import ScriptError, ScriptInterpreter, run_script_file

__all__ = ["ScriptError", "ScriptInterpreter", "run_script_file"]
