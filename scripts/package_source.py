"""Create a small, cross-platform source archive without local build artifacts."""
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from subsgen.branding import APP_VERSION


def main():
    files = [ROOT / name for name in ("README.md", "pyproject.toml", "SubsLab.spec", ".gitignore", ".gitattributes")]
    for directory, pattern in (("src/subsgen", "*.py"), ("tests", "*.py"), ("scripts", "*.py"),
                               ("scripts", "*.sh"), ("scripts", "*.ps1"), ("docs", "*.md"),
                               (".github/workflows", "*.yml"), ("packaging/windows", "*.iss"),
                               ("assets", "subslab.*")):
        files.extend((ROOT / directory).glob(pattern))
    output = ROOT / f"SubsLab-source-{APP_VERSION}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            path.resolve().relative_to(ROOT)
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Source archive validation failed")
        print(f"{output}\n{len(archive.namelist())} files · {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
