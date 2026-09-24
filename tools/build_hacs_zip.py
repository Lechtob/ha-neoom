"""Build a component-only archive; credentials and local reports cannot enter it."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    component = root / "custom_components" / "neoom"
    output = root / "dist" / "neoom.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(component.rglob("*")):
            if path.suffix in {".py", ".json"} and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(root))
    print(f"Created {output.name}")


if __name__ == "__main__":
    main()
