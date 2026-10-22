# OmniCar Repo

APT repo cho Sileo / Zebra, phát OmniCar (và các tweak khác). Chạy trên GitHub Pages, mỗi lần push lên `main`
GitHub Actions tự dựng lại `Packages` / `Release` và xuất bản.

URL người dùng thêm: **https://omnicarrepo.github.io/** (đổi trong `repo.conf`).

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `debs/` | Bỏ file `.deb` vào đây. Giữ vài bản cũ nếu muốn người dùng hạ cấp được. |
| `static/` | Chép nguyên lên web: trang chủ, `CydiaIcon.png`, `sileo-featured.json`, depiction. |
| `static/depictions/<package>/` | `sileo.json` (depiction gốc của Sileo), `index.html` (Zebra / trình duyệt), `icon.png`, `header.png`, `banner.png`, `changelog.md`, `description-<phiên bản>.txt` (chỉ sửa mô tả của đúng bản `.deb` đó; bản không có file này dùng mô tả trong `control` của nó). |
| `scripts/build.py` | Dựng repo vào `_site/` (chỉ cần Python 3). |
| `repo.conf` | URL gốc, Origin / Label / mô tả của repo. |

`build.py` tự thêm vào `Packages` các trường `Depiction`, `SileoDepiction`, `Icon`, `Header` trỏ về
`depictions/<package>/` (thay `Icon: file:///var/jb/...` trong control, vì đường đó chỉ có sau khi cài).
Trong depiction: `__BASE__` = URL gốc, `__VERSION__` = bản mới nhất trong `debs/`, `__CHANGELOG__` = `changelog.md`.

## Lần đầu

1. Repo GitHub: `OmniCarRepo/omnicarrepo.github.io`, **public**. Đúng tên này thì URL mới là `https://omnicarrepo.github.io/`; đổi tên repo thì URL đổi theo.
2. `git remote add origin git@github.com:OmniCarRepo/omnicarrepo.github.io.git && git push -u origin main`
3. GitHub > repo > **Settings > Pages > Source: GitHub Actions**. Chạy lại workflow **Publish repo** nếu lần đầu bị lỗi.
4. Mở `https://omnicarrepo.github.io/` trên iPhone > **Add to Sileo**.

## Phát hành bản mới

1. Lấy `.deb` từ GitHub Release của OmniCar (tag `v*`), hoặc từ artifact của CI.
2. Chép vào `debs/`, thêm mục mới ở đầu `static/depictions/com.anlai.omnicar/changelog.md`.
3. Commit + push. Khoảng 1 phút sau Sileo bấm làm mới là thấy bản mới.

Thử trên máy trước khi push: `python scripts/build.py` rồi xem `_site/Packages`.

## Tuỳ chọn

- **Ký Release**: tạo khoá GPG riêng cho repo, thêm secret `GPG_PRIVATE_KEY` (armored) và `GPG_PASSPHRASE`.
  Workflow tự ký `InRelease` + `Release.gpg`. Sileo / Zebra chạy được cả khi không ký.
- **Tên miền riêng** (`repo.<tên miền>`): tạo `static/CNAME` chứa tên miền, đổi `BASE_URL` trong `repo.conf`,
  trỏ DNS CNAME về `omnicarrepo.github.io`. Muốn đếm lượt tải thì đặt sau Cloudflare.
- **Nhánh beta**: tạo repo thứ hai (ví dụ `OmniCarRepo/beta`, URL `omnicarrepo.github.io/beta/`) dùng chung cấu trúc này.
