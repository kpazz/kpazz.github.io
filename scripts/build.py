#!/usr/bin/env python3
"""Build the APT repo into _site/ (or the folder given as the first argument).

  debs/*.deb                      -> pool/, indexed in Packages(.gz/.bz2/.xz/.zst) + Release
  static/                         -> copied as is; "__BASE__" in .html/.json becomes BASE_URL
  static/depictions/<package>/    -> Depiction / SileoDepiction / Icon / Header fields of that package;
                                     "__VERSION__" in its files becomes the newest version in debs/,
                                     "__CHANGELOG__" in sileo.json becomes changelog.md (as a JSON string)
  static/depictions/<package>/description-<version>.txt -> written over that version's whole Description
                                     (line 1 = summary); other versions keep their own control text
  AUTHOR / MAINTAINER in repo.conf  -> written over the deb's own Author / Maintainer

Signing: when the GPG_KEY_ID environment variable is set (key already imported), writes InRelease and
Release.gpg. Sileo and Zebra accept an unsigned repo, so this is optional.

Needs only Python 3. dpkg-deb is used as a fallback for control.tar.zst when the zstd module is missing.
"""
import bz2, gzip, hashlib, io, json, lzma, os, re, shutil, subprocess, sys, tarfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "_site"


def read_conf():
    conf = {}
    for line in (ROOT / "repo.conf").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    if not conf["BASE_URL"].endswith("/"):
        conf["BASE_URL"] += "/"
    return conf


def ar_members(data):
    if data[:8] != b"!<arch>\n":
        raise ValueError("not a .deb (ar) file")
    pos = 8
    while pos + 60 <= len(data):
        name = data[pos:pos + 16].decode().strip().rstrip("/")
        size = int(data[pos + 48:pos + 58].decode().strip())
        yield name, data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size & 1)


def decompress(name, blob):
    if name.endswith(".gz"):
        return gzip.decompress(blob)
    if name.endswith(".xz"):
        return lzma.decompress(blob)
    if name.endswith(".zst"):
        try:
            from compression import zstd  # Python 3.14+
        except ImportError:
            return None
        return zstd.decompress(blob)
    return blob


def read_control(deb):
    data = deb.read_bytes()
    for name, blob in ar_members(data):
        if name.startswith("control.tar"):
            raw = decompress(name, blob)
            if raw is not None:
                with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                    for m in tar.getmembers():
                        if m.name in ("control", "./control"):
                            return tar.extractfile(m).read().decode("utf-8")
            return subprocess.run(["dpkg-deb", "-f", str(deb)], check=True,
                                  capture_output=True, text=True).stdout
    raise ValueError(f"{deb.name}: no control.tar")


def parse_control(text):
    """Ordered list of [field, value]; continuation lines stay in the value."""
    fields = []
    for line in text.replace("\r", "").splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and fields:
            fields[-1][1] += "\n" + line
        else:
            k, v = line.split(":", 1)
            fields.append([k.strip(), v.strip()])
    return fields


def version_key(v):
    parts = re.split(r"([0-9]+)", v)
    return [(0, int(p)) if p.isdigit() else (1, p.replace("~", "\x00")) for p in parts if p]


def auto_translate_to_vietnamese(text):
    """Tự động dịch các thuật ngữ/câu mô tả tiếng Anh thông dụng sang tiếng Việt."""
    if not text:
        return text
    
    dictionary = {
        "new Debian package": "Gói Debian mới",
        "takes CarPlay beyond what Apple allows": "đưa CarPlay vượt ra ngoài giới hạn của Apple",
        "more freedom, more features and everything you need on the road": "tự do hơn, nhiều tính năng hơn và mọi thứ bạn cần trên đường đi",
        "in one package": "trong một gói duy nhất",
        "iPhone apps without CarPlay": "Ứng dụng iPhone không hỗ trợ CarPlay",
        "such as YouTube or TikTok": "như YouTube hoặc TikTok",
        "on the car screen": "trên màn hình ô tô",
        "Built in": "Tích hợp sẵn",
        "no CarBridge needed": "không cần dùng CarBridge",
        "Current speed and the posted limit": "Tốc độ hiện tại và giới hạn tốc độ",
        "On the CarPlay screen": "Trên màn hình CarPlay",
        "Over-speed warning with light effects and sound": "Cảnh báo quá tốc độ kèm hiệu ứng ánh sáng và âm thanh",
        "Your own video every time CarPlay connects": "Video cá nhân của bạn mỗi khi kết nối CarPlay",
        "Sound through the car speakers": "Phát âm thanh qua loa ô tô",
        "tap to skip": "chạm để bỏ qua"
    }

    translated = text
    for en, vi in dictionary.items():
        translated = re.sub(re.escape(en), vi, translated, flags=re.IGNORECASE)
    
    return translated


def main():
    conf = read_conf()
    base = conf["BASE_URL"]
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)
    (OUT / "pool").mkdir()

    stanzas, newest, pkg_firmware, pkg_author, pkg_name, pkg_edition, pkg_description = [], {}, {}, {}, {}, {}, {}
    for deb in sorted((ROOT / "debs").glob("*.deb")):
        fields = parse_control(read_control(deb))
        info = dict(fields)
        pkg, ver = info["Package"], info["Version"]
        target = f"pool/{pkg}_{ver}_{info.get('Architecture', 'all')}.deb"
        shutil.copyfile(deb, OUT / target)
        blob = deb.read_bytes()

        # --- TỰ ĐỘNG ĐỌC PHIÊN BẢN FIRMWARE TỪ DEPENDS ---
        depends_val = info.get("Depends", "")
        fw_match = re.search(r"firmware\s*\(\s*(\>\=|\=|\<\=)?\s*([0-9\.]+)\s*\)", depends_val, re.IGNORECASE)
        if fw_match:
            op = fw_match.group(1) or ""
            fw_ver = fw_match.group(2)
            if ">=" in op or op == "":
                pkg_firmware[pkg] = f"{fw_ver} trở lên"
            else:
                pkg_firmware[pkg] = fw_ver
        else:
            loose_match = re.search(r"([0-9]+\.[0-9]+)", depends_val)
            if loose_match and ("ios" in depends_val.lower() or "firmware" in depends_val.lower()):
                pkg_firmware[pkg] = f"{loose_match.group(1)} trở lên"
            else:
                pkg_firmware[pkg] = "Không giới hạn"

        # --- NHẬN DIỆN PHÂN LOẠI: VIỆT HÓA HOẶC QUỐC TẾ ---
        combined_meta = (deb.name + " " + pkg + " " + info.get("Description", "")).lower()
        if "-vn" in combined_meta or "_vn" in combined_meta or "việt hóa" in combined_meta:
            edition_text = "Việt Hóa"
            edition_label = "[Việt Hóa]"
        else:
            edition_text = "Quốc Tế"
            edition_label = "[Quốc Tế]"
        pkg_edition[pkg] = edition_text

        # --- TỰ ĐỘNG DỊCH VÀ CHÈN NHÃN VÀO DESCRIPTION ---
        raw_desc = info.get("Description", "")
        translated_desc = auto_translate_to_vietnamese(raw_desc)
        pkg_description[pkg] = translated_desc

        for f in fields:
            if f[0] == "Description":
                desc_lines = translated_desc.splitlines()
                if desc_lines and not desc_lines[0].startswith("["):
                    desc_lines[0] = f"{edition_label} {desc_lines[0]}"
                f[1] = "\n".join(desc_lines)

        # --- TỰ ĐỘNG ĐỌC TÊN TÁC GIẢ VÀ TÊN TWEAK ---
        author_val = info.get("Author") or info.get("Maintainer") or "Unknown"
        clean_author = re.sub(r"<.*?>", "", author_val).strip()
        pkg_author[pkg] = clean_author if clean_author else author_val
        pkg_name[pkg] = info.get("Name", pkg)

        for key, field in (("AUTHOR", "Author"), ("MAINTAINER", "Maintainer")):
            if conf.get(key):
                fields = [f for f in fields if f[0] != field] + [[field, conf[key]]]

        dep = ROOT / "static" / "depictions" / pkg
        desc = dep / f"description-{ver}.txt"
        if desc.exists():
            text = desc.read_text(encoding="utf-8").strip("\n").split("\n")
            for f in fields:
                if f[0] == "Description":
                    f[1] = "\n".join([text[0]] + [" " + (l if l.strip() else ".") for l in text[1:]])
        if dep.is_dir():
            drop = {"Depiction", "SileoDepiction", "Header"}
            if (dep / "icon.png").exists():
                drop.add("Icon")
            fields = [f for f in fields if f[0] not in drop]
            fields.append(["Depiction", f"{base}depictions/{pkg}/"])
            if (dep / "sileo.json").exists():
                fields.append(["SileoDepiction", f"{base}depictions/{pkg}/sileo.json"])
            if (dep / "icon.png").exists():
                fields.append(["Icon", f"{base}depictions/{pkg}/icon.png"])
            if (dep / "header.png").exists():
                fields.append(["Header", f"{base}depictions/{pkg}/header.png"])
        fields += [["Filename", target], ["Size", str(len(blob))],
                   ["MD5sum", hashlib.md5(blob).hexdigest()],
                   ["SHA1", hashlib.sha1(blob).hexdigest()],
                   ["SHA256", hashlib.sha256(blob).hexdigest()]]
        stanzas.append("\n".join(f"{k}: {v}" for k, v in fields))
        if pkg not in newest or version_key(ver) > version_key(newest[pkg]):
            newest[pkg] = ver
        print(f"  {pkg} {ver}  <- {deb.name}")

    # --- THỜI GIAN CHUẨN MÚI GIỜ VIỆT NAM (UTC+7) ---
    tz_vn = timezone(timedelta(hours=7))
    current_date = datetime.now(tz_vn).strftime("%d/%m/%Y")
    current_time = datetime.now(tz_vn).strftime("%H:%M")

    # Templates
    for f in list(OUT.rglob("*.html")) + list(OUT.rglob("*.json")):
        text = f.read_text(encoding="utf-8").replace("__BASE__", base)
        rel = f.relative_to(OUT).parts
        if len(rel) >= 3 and rel[0] == "depictions":
            pkg = rel[1]
            text = text.replace("__VERSION__", newest.get(pkg, "-"))
            text = text.replace("__DEPENDS__", pkg_firmware.get(pkg, "Không giới hạn"))
            text = text.replace("__AUTHOR__", pkg_author.get(pkg, "Unknown"))
            text = text.replace("__NAME__", pkg_name.get(pkg, pkg))
            text = text.replace("__EDITION__", pkg_edition.get(pkg, "Quốc Tế"))
            text = text.replace("__DESCRIPTION__", pkg_description.get(pkg, ""))
            text = text.replace("__DATE__", current_date)
            text = text.replace("__TIME__", current_time)
            log = OUT / "depictions" / pkg / "changelog.md"
            if "__CHANGELOG__" in text:
                md = log.read_text(encoding="utf-8") if log.exists() else "No changes listed."
                text = text.replace('"__CHANGELOG__"', json.dumps(md, ensure_ascii=False))
        if f.suffix == ".json":
            json.loads(text)
        f.write_text(text, encoding="utf-8", newline="\n")

    packages = ("\n\n".join(stanzas) + "\n").encode() if stanzas else b""
    (OUT / "Packages").write_bytes(packages)
    (OUT / "Packages.gz").write_bytes(gzip.compress(packages, 9, mtime=0))
    (OUT / "Packages.bz2").write_bytes(bz2.compress(packages, 9))
    (OUT / "Packages.xz").write_bytes(lzma.compress(packages, preset=9))
    index = ["Packages", "Packages.gz", "Packages.bz2", "Packages.xz"]
    if shutil.which("zstd"):
        subprocess.run(["zstd", "-q", "-19", "-f", str(OUT / "Packages")], check=True)
        index.append("Packages.zst")

    release = [
        f"Origin: {conf['ORIGIN']}", f"Label: {conf['LABEL']}", f"Suite: {conf['SUITE']}",
        "Version: 1.0", f"Codename: {conf['CODENAME']}",
        f"Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S UTC')}",
        f"Architectures: {conf['Architectures'] if 'Architectures' in conf else conf['ARCHITECTURES']}", f"Components: {conf['COMPONENTS']}",
        f"Description: {conf['DESCRIPTION']}",
    ]
    for algo, title in (("md5", "MD5Sum"), ("sha1", "SHA1"), ("sha256", "SHA256"), ("sha512", "SHA512")):
        release.append(f"{title}:")
        for name in index:
            b = (OUT / name).read_bytes()
            release.append(f" {hashlib.new(algo, b).hexdigest()} {len(b):>16} {name}")
    (OUT / "Release").write_text("\n".join(release) + "\n", encoding="utf-8", newline="\n")

    key = os.environ.get("GPG_KEY_ID")
    if key:
        gpg = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback", "-u", key]
        if os.environ.get("GPG_PASSPHRASE"):
            gpg += ["--passphrase", os.environ["GPG_PASSPHRASE"]]
        subprocess.run(gpg + ["--clearsign", "-o", str(OUT / "InRelease"), str(OUT / "Release")], check=True)
        subprocess.run(gpg + ["-abs", "-o", str(OUT / "Release.gpg"), str(OUT / "Release")], check=True)
        print("  signed Release with", key)

    print(f"Built {len(stanzas)} package(s) into {OUT} for {base}")


if __name__ == "__main__":
    main()
