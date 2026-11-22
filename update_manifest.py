import json
from pathlib import Path


def find_tabs_dir(root: Path) -> Path:
    for name in ("Tabs", "tabs"):
        candidate = root / name
        if candidate.is_dir():
            return candidate
    # Nếu chưa có thư mục thì tạo mặc định Tabs/
    default_dir = root / "Tabs"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


def main() -> None:
    root = Path(__file__).resolve().parent
    tabs_dir = find_tabs_dir(root)

    html_files = sorted(
        (
            p.name
            for p in tabs_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() == ".html"
            and p.name.lower() != "index.html"
        ),
        key=lambda s: s.lower(),
    )

    manifest_path = tabs_dir / "manifest.json"
    manifest_data = {"files": html_files}

    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Đã cập nhật {manifest_path.relative_to(root)} ({len(html_files)} tệp): {html_files}")


if __name__ == "__main__":
    main()

