import os
import subprocess
import hashlib
import glob
import json
from datetime import datetime

# Cấu hình đường dẫn
DEB_DIR = "debs"         # Thư mục chứa các file .deb của bạn
PACKAGES_FILE = "Packages"
RELEASE_FILE = "Release"
JSON_FILE = "Tabs/Tweak.json"


def get_file_hash(filepath):
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    md5 = hashlib.md5()

    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
            sha512.update(chunk)
            md5.update(chunk)

    return md5.hexdigest(), sha256.hexdigest(), sha512.hexdigest(), os.path.getsize(filepath)


def format_file_size(filepath):
    """Đọc dung lượng file .deb và định dạng ra chuỗi dễ đọc (VD: 1.25 MB, 450.0 KB)."""
    if not filepath or not os.path.exists(filepath):
        return ""
    size_bytes = os.path.getsize(filepath)
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def generate_packages():
    if not os.path.exists(DEB_DIR):
        os.makedirs(DEB_DIR)
        print(f"[-] Đã tạo thư mục '{DEB_DIR}'. Hãy đưa các file .deb vào đây.")
        return False

    deb_files = glob.glob(os.path.join(DEB_DIR, "*.deb"))
    if not deb_files:
        print("[-] Không tìm thấy file .deb nào trong thư mục debs/")
        return False

    packages_content = ""

    print("[+] Đang quét và trích xuất thông tin các file .deb...")
    for deb in deb_files:
        # Sử dụng dpkg-deb để lấy thông tin control
        try:
            control_data = subprocess.check_output(["dpkg-deb", "-f", deb]).decode("utf-8")
        except Exception as e:
            print(f"[!] Lỗi đọc control từ {deb}: {e}")
            continue

        filename = os.path.basename(deb)
        md5, sha256, sha512, size = get_file_hash(deb)

        # Bổ sung các thông số đường dẫn và checksum vào metadata của package
        pkg_block = (
            control_data.strip()
            + f"\nFilename: {DEB_DIR}/{filename}\nSize: {size}\nMD5sum: {md5}\nSHA256: {sha256}\n\n"
        )
        packages_content += pkg_block

    # Ghi tệp Packages
    with open(PACKAGES_FILE, "w", encoding="utf-8") as f:
        f.write(packages_content)
    print(f"[✔] Đã tạo thành công tệp {PACKAGES_FILE}")

    # Nén tệp Packages (Sileo và Zebra rất ưa chuộng .bz2 / .zst)
    subprocess.run(f"bzip2 -fk {PACKAGES_FILE}", shell=True)
    subprocess.run(f"zstd -f {PACKAGES_FILE} -o {PACKAGES_FILE}.zst", shell=True)
    print("[✔] Đã nén Packages thành công (.bz2, .zst)")

    return True


def update_release():
    if not os.path.exists(PACKAGES_FILE):
        return

    # Tính toán checksum cho các tệp Packages và các định dạng nén
    files_to_hash = [PACKAGES_FILE, f"{PACKAGES_FILE}.bz2", f"{PACKAGES_FILE}.zst"]

    md5_lines = []
    sha256_lines = []
    sha512_lines = []

    for file in files_to_hash:
        if os.path.exists(file):
            md5, sha256, sha512, size = get_file_hash(file)
            rel_path = file
            md5_lines.append(f" {md5} {size} {rel_path}")
            sha256_lines.append(f" {sha256} {size} {rel_path}")
            sha512_lines.append(f" {sha512} {size} {rel_path}")

    # Đọc cấu hình Release cơ bản hoặc tạo mới
    release_header = """Origin: KPazz Repository
Label: KPazz Store
Suite: stable
Version: 1.0
Codename: ios
Architectures: iphoneos-arm iphoneos-arm64
Components: main
Description: Kho lưu trữ tweak và ứng dụng iOS cá nhân của KPazz.
"""

    release_content = (
        release_header
        + "MD5Sum:\n"
        + "\n".join(md5_lines)
        + "\nSHA256:\n"
        + "\n".join(sha256_lines)
        + "\nSHA512:\n"
        + "\n".join(sha512_lines)
        + "\n"
    )

    with open(RELEASE_FILE, "w", encoding="utf-8") as f:
        f.write(release_content)
    print(f"[✔] Đã cập nhật xong tệp {RELEASE_FILE}")


def update_tweak_json():
    if not os.path.exists("Tabs"):
        os.makedirs("Tabs")

    deb_files = glob.glob(os.path.join(DEB_DIR, "*.deb"))

    # Bản đồ dung lượng theo đường dẫn tương đối (VD: "debs/abc.deb") và tên file
    deb_size_by_path = {}
    deb_size_by_name = {}
    for deb in deb_files:
        norm_path = deb.replace("\\", "/")
        human_size = format_file_size(deb)
        deb_size_by_path[norm_path] = human_size
        deb_size_by_name[os.path.basename(deb)] = human_size

    # Đọc cấu trúc JSON hiện tại (nếu có) để giữ nguyên các cấu hình section, sliderConfig và item có sẵn
    repo_data = {
        "sectionTitle": "Tweak jailbreak ios",
        "sectionSubtitle": "Tweak Tinh chỉnh cài trên Sileo, Zebra,.. cho iPhone & iPad Jailbreak",
        "Card": "Nhỏ",
        "autoslide": "Yes",
        "NumberSlot": "1",
        "sliderConfig": {},
        "items": []
    }

    existing_items_by_link = {}
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                repo_data.update(loaded)
                for item in loaded.get("items", []):
                    link = (item.get("downloadLink") or item.get("buttonUrl") or "").replace("\\", "/")
                    if link:
                        existing_items_by_link[link] = item
            elif isinstance(loaded, list):
                for item in loaded:
                    link = (item.get("downloadLink") or item.get("buttonUrl") or "").replace("\\", "/")
                    if link:
                        existing_items_by_link[link] = item
        except Exception as e:
            print(f"[!] Không thể đọc {JSON_FILE}, sẽ tạo mới: {e}")

    updated_items = []
    seen_links = set()

    # Quét các file .deb hiện có để cập nhật hoặc thêm mới vào items
    for deb in deb_files:
        norm_link = deb.replace("\\", "/")
        seen_links.add(norm_link)
        human_size = deb_size_by_path.get(norm_link, "")

        try:
            control_raw = subprocess.check_output(["dpkg-deb", "-f", deb]).decode("utf-8")
        except Exception as e:
            print(f"[!] Lỗi đọc control từ {deb}: {e}")
            continue

        control = {}
        for line in control_raw.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                control[key.strip()] = val.strip()

        pkg_name = control.get("Package", "")
        name = control.get("Name", pkg_name)
        version = control.get("Version", "1.0.0")
        dev = control.get("Author", control.get("Maintainer", "Unknown"))
        category = control.get("Section", "Tweaks")
        depends = control.get("Depends", "iOS 14.0 trở lên")
        description_lines = [line.strip() for line in control.get("Description", "").splitlines() if line.strip()]
        description = "\n".join(description_lines) if description_lines else "Không có mô tả."

        file_mtime = os.path.getmtime(deb)
        publish_date = datetime.fromtimestamp(file_mtime).strftime("%d/%m/%Y")

        old_item = existing_items_by_link.get(norm_link, {})
        img = old_item.get("img", "./Art/imgicon.png")
        icon = old_item.get("icon", img)
        banner = old_item.get("banner", "./Art/imgbanner.png")

        full_description = f"{description}\n\nYêu cầu hệ thống: {depends}" if depends else description
        highlight_title = f"Phiên bản {version} - Cập nhật mới"
        changelog = "\n".join(f"• {line}" for line in description_lines) if description_lines else f"• {description}"

        screenshots = old_item.get("screenshots", [banner])
        gallery = old_item.get("gallery", [banner])
        highlights = old_item.get("highlights")
        if not highlights:
            highlights = [{"text": line, "img": banner} for line in (description_lines or [description])]

        tweak_item = {
            "name": name,
            "appName": old_item.get("appName", name),
            "tag": old_item.get("tag", "TWEAK CHO IPHONE & IPAD JAILBREAK"),
            "title": old_item.get("title", name),
            "version": version,
            "dev": dev,
            "author": old_item.get("author", dev),
            "category": category,
            "genre": old_item.get("genre", category),
            "systemRequirements": depends,
            "img": img,
            "icon": icon,
            "iconAlt": old_item.get("iconAlt", f"Icon {name}"),
            "banner": banner,
            "bannerAlt": old_item.get("bannerAlt", name),
            "publishDate": publish_date,
            "releaseDate": old_item.get("releaseDate", publish_date),
            "fileFormat": "DEB",
            "fileSize": human_size,
            "size": human_size,
            "isApp": old_item.get("isApp", True),
            "noDownload": old_item.get("noDownload", False),
            "downloadLink": norm_link,
            "buttonUrl": norm_link,
            "downloadPickerTitle": old_item.get("downloadPickerTitle", "Chọn link tải"),
            "downloadPickerSubtitle": old_item.get("downloadPickerSubtitle", "Chọn 1 trong các link tải bên dưới"),
            "downloadOptionPrefix": old_item.get("downloadOptionPrefix", "Link tải"),
            "useVersionInPicker": old_item.get("useVersionInPicker", False),
            "downloads": old_item.get("downloads", [
                {
                    "label": "Link tải 1",
                    "note": f"Gói DEB (v{version})",
                    "url": norm_link
                }
            ]),
            "video": old_item.get("video", ""),
            "videoUrl": old_item.get("videoUrl", ""),
            "gif": old_item.get("gif", ""),
            "description": description,
            "fullDescription": full_description,
            "highlightTitle": highlight_title,
            "changelog": changelog,
            "screenshots": screenshots,
            "gallery": gallery,
            "highlights": highlights
        }
        updated_items.append(tweak_item)

    # Giữ lại các item cũ nếu file .deb của chúng chưa có trong thư mục debs/, và cập nhật size nếu tìm thấy file theo tên
    for link, old_item in existing_items_by_link.items():
        if link in seen_links:
            continue
        item_copy = dict(old_item)
        matched_size = deb_size_by_path.get(link) or deb_size_by_name.get(os.path.basename(link))
        if matched_size:
            item_copy["fileSize"] = matched_size
            item_copy["size"] = matched_size
        elif "size" not in item_copy:
            item_copy["size"] = item_copy.get("fileSize", "")
        updated_items.append(item_copy)

    repo_data["items"] = updated_items

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(repo_data, f, ensure_ascii=False, indent=2)
    print(f"[✔] Đã tự động cập nhật {JSON_FILE} thành công!")


if __name__ == "__main__":
    if generate_packages():
        update_release()
        update_tweak_json()
        print("[🎉] Hoàn tất toàn bộ gói repo cho Sileo & Zebra!")
