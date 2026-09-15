from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from .models import Scenario


_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def jsonpath_tokens(path: str) -> list[str | int]:
    if not path.startswith("$."):
        raise ValueError(f"unsupported JSONPath: {path}")
    return [int(index) if index else name for name, index in _TOKEN.findall(path[2:])]


def set_path(root: dict[str, Any], path: str, value: Any) -> None:
    tokens = jsonpath_tokens(path)
    current: Any = root
    for offset, token in enumerate(tokens):
        final = offset == len(tokens) - 1
        next_token = None if final else tokens[offset + 1]
        if isinstance(token, str):
            if final:
                current[token] = copy.deepcopy(value)
            else:
                desired = [] if isinstance(next_token, int) else {}
                if token not in current or not isinstance(current[token], type(desired)):
                    current[token] = desired
                current = current[token]
        else:
            while len(current) <= token:
                current.append(None)
            if final:
                current[token] = copy.deepcopy(value)
            else:
                desired = [] if isinstance(next_token, int) else {}
                if current[token] is None or not isinstance(current[token], type(desired)):
                    current[token] = desired
                current = current[token]


def delete_path(root: dict[str, Any], path: str) -> None:
    tokens = jsonpath_tokens(path)
    current: Any = root
    try:
        for token in tokens[:-1]:
            current = current[token]
        final = tokens[-1]
        if isinstance(final, int):
            if isinstance(current, list) and final < len(current):
                current.pop(final)
        elif isinstance(current, dict):
            current.pop(final, None)
    except (KeyError, IndexError, TypeError):
        return


class EvidenceProjection:
    """Compiles canonical atom masks into per-tool visible observations."""

    def __init__(self, scenario: Scenario, masked_atom_ids: frozenset[str]):
        known = {atom.id for atom in scenario.evidence}
        unknown = masked_atom_ids - known
        if unknown:
            raise ValueError(f"unknown masked evidence atoms: {sorted(unknown)}")
        self.scenario = scenario
        self.masked_atom_ids = masked_atom_ids
        self._tool_atoms = defaultdict(list)
        for atom in scenario.evidence:
            for exposure in atom.exposures:
                self._tool_atoms[exposure.tool].append((atom, exposure.path))

    def observe(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        argument_values = {
            str(value).casefold() for value in arguments.values() if isinstance(value, (str, int, float))
        }
        grouped: dict[str, list[Any]] = defaultdict(list)
        for atom, path in self._tool_atoms.get(tool_name, []):
            grouped[path].append(atom)

        selected: list[tuple[Any, str]] = []
        for path, atoms in grouped.items():
            matches = [
                atom
                for atom in atoms
                if any(value in atom.subject.casefold() for value in argument_values)
            ]
            if len(matches) == 1:
                selected.append((matches[0], path))
                continue
            distinct_values = {repr(atom.value) for atom in atoms}
            if len(distinct_values) <= 1:
                selected.append((atoms[0], path))
                continue
            if len(matches) != 1:
                raise ValueError(
                    f"tool {tool_name!r} path {path!r} is ambiguous for supplied arguments"
                )
            selected.append((matches[0], path))

        result: dict[str, Any] = {}
        for atom, path in selected:
            set_path(result, path, atom.value)
        hidden_paths = [
            path
            for atom, path in selected
            if atom.id in self.masked_atom_ids
        ]
        # Descending array indices prevent earlier removals from shifting later targets.
        def deletion_order(path: str) -> tuple[tuple[int, str], ...]:
            return tuple(
                (1, f"{token:012d}") if isinstance(token, int) else (0, token)
                for token in jsonpath_tokens(path)
            )

        for path in sorted(hidden_paths, key=deletion_order, reverse=True):
            delete_path(result, path)
        return result

    def hidden_exposures(self) -> dict[str, list[str]]:
        hidden: dict[str, list[str]] = defaultdict(list)
        for atom in self.scenario.evidence:
            if atom.id in self.masked_atom_ids:
                for exposure in atom.exposures:
                    hidden[exposure.tool].append(exposure.path)
        return {name: sorted(paths) for name, paths in sorted(hidden.items())}
