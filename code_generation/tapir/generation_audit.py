import argparse
import ast
import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from code_generation.tapir.paths import tapir_paths


@dataclass(frozen=True)
class Finding:
    rule: str
    location: str
    message: str


ALLOWED_NUMBERED_NAMES: set[str] = set()

GENERATED_PYTHON_FILES = (
    tapir_paths.RAW_PYDANTIC_MODELS,
    tapir_paths.CLEANED_PYDANTIC_MODELS,
    tapir_paths.RAW_TYPED_DICTS,
    tapir_paths.CLEANED_TYPED_DICTS,
    tapir_paths.FINAL_PYDANTIC_TYPES,
    tapir_paths.FINAL_PYDANTIC_COMMANDS,
    tapir_paths.FINAL_TYPED_DICT_TYPES,
    tapir_paths.FINAL_TYPED_DICT_COMMANDS,
    tapir_paths.FINAL_LITERAL_COMMANDS,
    tapir_paths.GENERATED_TESTS_OUTPUT,
)

PUBLIC_MODEL_FILES = (
    tapir_paths.FINAL_PYDANTIC_TYPES,
    tapir_paths.FINAL_PYDANTIC_COMMANDS,
    tapir_paths.FINAL_TYPED_DICT_TYPES,
    tapir_paths.FINAL_TYPED_DICT_COMMANDS,
)


def _walk_json(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, f"{path}[{index}]")


def _is_python_identifier(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


def audit_schema_names(schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    definitions = schema.get("$defs", {})

    for name in definitions:
        if not _is_python_identifier(name) or not name[:1].isupper():
            findings.append(
                Finding(
                    "invalid-schema-name",
                    f"$.$defs.{name}",
                    f"Definition name '{name}' is not valid PascalCase Python.",
                )
            )

    for path, value in _walk_json(schema):
        if not isinstance(value, dict) or value.get("type") != "object" or "properties" not in value:
            continue
        properties = value["properties"]
        if not isinstance(properties, dict):
            findings.append(Finding("invalid-properties", path, "Schema 'properties' must be an object."))
            continue
        for name in properties:
            if not _is_python_identifier(name):
                findings.append(
                    Finding(
                        "invalid-schema-name",
                        f"{path}.properties.{name}",
                        f"Property name '{name}' is not valid Python.",
                    )
                )

    return findings


def _resolve_json_pointer(document: Any, ref: str) -> bool:
    current = document
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def audit_local_refs(schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for path, value in _walk_json(schema):
        if not isinstance(value, dict) or not isinstance(value.get("$ref"), str):
            continue
        ref = value["$ref"]
        if ref.startswith("#/") and not _resolve_json_pointer(schema, ref):
            findings.append(Finding("unresolved-ref", path, f"Local reference does not resolve: {ref}"))
    return findings


def _public_definition_names(path: Path, tree: ast.Module) -> Iterable[tuple[str, int]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            yield node.name, node.lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "TypeAlias":
                yield node.target.id, node.lineno


def audit_python_files(paths: Iterable[Path]) -> tuple[list[Finding], dict[Path, ast.Module]]:
    findings: list[Finding] = []
    trees: dict[Path, ast.Module] = {}
    for path in paths:
        if not path.exists():
            findings.append(Finding("missing-generated-file", str(path), "Expected generated Python file is missing."))
            continue
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            location = f"{path}:{error.lineno or 1}"
            findings.append(Finding("invalid-generated-python", location, error.msg))
    return findings, trees


def audit_generated_names(trees: dict[Path, ast.Module]) -> list[Finding]:
    locations: dict[str, list[str]] = {}
    for path in PUBLIC_MODEL_FILES:
        tree = trees.get(path)
        if tree is None:
            continue
        for name, line in _public_definition_names(path, tree):
            locations.setdefault(name, []).append(f"{path}:{line}")

    findings: list[Finding] = []
    for name, name_locations in sorted(locations.items()):
        reasons = []
        if re.search(r"\d+$", name) and name not in ALLOWED_NUMBERED_NAMES:
            reasons.append("ends in a generator-style numeric suffix")
        if name.endswith("Datum"):
            reasons.append("uses the generator singularization 'Datum'")
        if reasons:
            findings.append(
                Finding("unstable-generated-name", ", ".join(name_locations), f"{name}: {'; '.join(reasons)}.")
            )
    return findings


def run_audit() -> list[Finding]:
    try:
        schema = json.loads(tapir_paths.MASTER_SCHEMA_OUTPUT.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [Finding("missing-master-schema", str(tapir_paths.MASTER_SCHEMA_OUTPUT), "Master schema is missing.")]
    except json.JSONDecodeError as error:
        return [Finding("invalid-master-schema", str(tapir_paths.MASTER_SCHEMA_OUTPUT), str(error))]

    findings = audit_schema_names(schema)
    findings.extend(audit_local_refs(schema))
    python_findings, trees = audit_python_files(GENERATED_PYTHON_FILES)
    findings.extend(python_findings)
    findings.extend(audit_generated_names(trees))
    return findings


def main(strict: bool = False) -> None:
    print("--- Auditing generated Tapir models ---")
    findings = run_audit()
    if not findings:
        print("Generation audit passed.")
        return

    for finding in findings:
        print(f"ERROR {finding.rule}: {finding.location}\n  {finding.message}")
    print(f"Generation audit found {len(findings)} issue(s).")
    if strict:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit generated Tapir schemas and Python models.")
    parser.add_argument("--strict", action="store_true", help="Exit with an error when findings are reported.")
    main(strict=parser.parse_args().strict)
