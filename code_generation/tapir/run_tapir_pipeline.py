import sys
import pathlib

project_root = pathlib.Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import time
import importlib
import argparse
import re
from code_generation.tapir.paths import tapir_paths
from multiconn_archicad.constants import SUPPORTED_TAPIR_VERSION


CONSTANTS_FILE = getattr(tapir_paths, "CONSTANTS_FILE", project_root / "src" / "multiconn_archicad" / "constants.py")


# Sequence of modules to execute
STEPS = [
    ("Schema Generator", "code_generation.tapir.model_generators.01_schema_generator"),
    ("Code Generator", "code_generation.tapir.model_generators.02_generate_dicts_and_models"),
    ("Model Cleaner (Pydantic)", "code_generation.tapir.model_generators.03_model_cleaner"),
    ("Model Splitter (Pydantic)", "code_generation.tapir.model_generators.04_split_models"),
    ("Model Cleaner (TypedDicts)", "code_generation.tapir.model_generators.06_typed_dict_cleaner"),
    ("Model Splitter (TypedDicts)", "code_generation.tapir.model_generators.07_split_typed_dicts"),
    ("Generate Model Tests", "code_generation.tapir.model_generators.08_generate_model_tests"),
    ("Ruff Formatting Pipeline", "code_generation.tapir.model_generators.09_run_formatter"),
    ("Generation Audit", "code_generation.tapir.generation_audit"),
]


def run_pipeline() -> None:
    tapir_version = resolve_and_sync_tapir_version()
    update_readme_badge(tapir_version)

    print("==================================================")
    print("🔥 Starting Master Tapir Generation Pipeline 🔥")
    print(f"📌 Target Tapir Version: {tapir_version}")
    print("==================================================")

    pipeline_start = time.time()
    run_pipeline_steps()
    total_elapsed = time.time() - pipeline_start

    print("\n==================================================")
    print(f"🎉 Pipeline Complete! Total execution time: {total_elapsed:.2f}s")
    print("==================================================")


def resolve_and_sync_tapir_version() -> str:
    """
    Parses CLI argument --tapir-version.
    - If passed: Updates SUPPORTED_TAPIR_VERSION in constants.py.
    - If omitted: Reads current SUPPORTED_TAPIR_VERSION from constants.py.
    """
    parser = argparse.ArgumentParser(description="Tapir API Code Generation Pipeline")
    parser.add_argument(
        "--tapir-version",
        type=str,
        default=None,
        help="Optional: New Tapir version to pin against (e.g. '1.5.8'). Defaults to constants.py."
    )
    args, _ = parser.parse_known_args()

    if args.tapir_version:
        version = args.tapir_version.strip()
        update_constants_file(version)
        print(f"📌 Updated constants.py to Tapir version: {version}")
        return version

    print(f"📌 Using existing Tapir version from constants.py: {SUPPORTED_TAPIR_VERSION}")
    return SUPPORTED_TAPIR_VERSION


def update_constants_file(version: str) -> None:
    """Writes the new version directly into constants.py."""
    if not CONSTANTS_FILE.exists():
        raise FileNotFoundError(f"Could not find constants.py at: {CONSTANTS_FILE}")

    content = CONSTANTS_FILE.read_text(encoding="utf-8")

    # Matches: SUPPORTED_TAPIR_VERSION = "..."
    pattern = r'(SUPPORTED_TAPIR_VERSION\s*=\s*["\'])([^"\']+)(["\'])'
    new_content = re.sub(pattern, rf'\g<1>{version}\g<3>', content)

    if content != new_content:
        CONSTANTS_FILE.write_text(new_content, encoding="utf-8")
        print(f"📝 Synced {CONSTANTS_FILE.name} with version {version}")


def update_readme_badge(version: str) -> None:
    """Automatically updates the Tapir version badge in the README."""
    readme_path = tapir_paths.PROJECT_ROOT / "README.md"
    if not readme_path.exists():
        return

    content = readme_path.read_text(encoding="utf-8")

    # Matches: https://img.shields.io/badge/Tapir_Add--On-1.5.8-blue
    pattern = r"(https://img\.shields\.io/badge/Tapir_Add--On-)([^-]+)(-blue)"
    new_content = re.sub(pattern, rf"\g<1>{version}\g<3>", content)

    if content != new_content:
        readme_path.write_text(new_content, encoding="utf-8")
        print(f"📝 Automatically updated README.md badge to {version}")


def run_pipeline_steps() -> None:
    for step_name, module_path in STEPS:
        print(f"\n🚀 Running: {step_name}")
        print("-" * 50)

        step_start = time.time()
        try:
            module = importlib.import_module(module_path)

            if hasattr(module, "main"):
                module.main()

            elapsed = time.time() - step_start
            print(f"✅ {step_name} completed in {elapsed:.2f}s.")

        except Exception as e:
            print(f"❌ Error executing {step_name} at module {module_path}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
