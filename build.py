"""Package the game using only Python's standard library."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent
    output = root / "artifacts" / "go4d.zip"
    output.parent.mkdir(exist_ok=True)
    files = [root / name for name in ("README.md", "app.py", "engine.py", "ai.py", "build.py", "开始游戏.command", ".gitignore")]
    for folder in ("static", "tests", "docs"):
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts)
    for path in files:
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"打包文件缺失或为空：{path.name}")
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("go4d") / path.relative_to(root))
    with ZipFile(output) as archive:
        damaged = archive.testzip()
        if damaged is not None:
            raise SystemExit(f"压缩包验证失败：{damaged}")
    print(f"已生成：{output}")
    print(f"文件数：{len(files)}；大小：{output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
