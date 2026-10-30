import os
import subprocess
import hashlib
import glob

# Cấu hình đường dẫn
DEB_DIR = "debs"         # Thư mục chứa các file .deb của bạn
PACKAGES_FILE = "Packages"
RELEASE_FILE = "Release"

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
        pkg_block = control_data.strip() + f"\nFilename: {DEB_DIR}/{filename}\nSize: {size}\nMD5sum: {md5}\nSHA256: {sha256}\n\n"
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

    release_content = release_header + "MD5Sum:\n" + "\n".join(md5_lines) + "\nSHA256:\n" + "\n".join(sha256_lines) + "\nSHA512:\n" + "\n".join(sha512_lines) + "\n"

    with open(RELEASE_FILE, "w", encoding="utf-8") as f:
        f.write(release_content)
    print(f"[✔] Đã cập nhật xong tệp {RELEASE_FILE}")

if __name__ == "__main__":
    if generate_packages():
        update_release()
        print("[🎉] Hoàn tất toàn bộ gói repo cho Sileo & Zebra!")
