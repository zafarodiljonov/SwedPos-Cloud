"""
Compiles locale/*/LC_MESSAGES/django.po into django.mo without GNU gettext (Windows and the Django Europe host have
no msgfmt). The compiled .mo files are committed, so the server needs nothing extra.

    python tools/compile_messages.py
"""
import ast
import struct
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def read_po(path: Path) -> dict[str, str]:
    messages, msgid, msgstr, section = {}, None, None, None

    def flush():
        if msgid is not None and msgstr is not None:
            messages[msgid] = msgstr

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            msgid, msgstr, section = ast.literal_eval(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, section = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"'):
            part = ast.literal_eval(line)
            if section == "id":
                msgid += part
            else:
                msgstr += part
    flush()
    return messages


def write_mo(messages: dict[str, str], path: Path):
    """The standard GNU .mo layout (as Python's Tools/i18n/msgfmt.py writes it)."""
    keys = sorted(messages)
    ids = b"".join(k.encode("utf-8") + b"\0" for k in keys)
    strs = b"".join(messages[k].encode("utf-8") + b"\0" for k in keys)
    offsets, id_pos, str_pos = [], 0, 0
    for k in keys:
        kb, vb = k.encode("utf-8"), messages[k].encode("utf-8")
        offsets.append((len(kb), id_pos, len(vb), str_pos))
        id_pos += len(kb) + 1
        str_pos += len(vb) + 1
    count = len(keys)
    key_start = 7 * 4 + count * 16
    value_start = key_start + len(ids)
    table = []
    for klen, kpos, vlen, vpos in offsets:
        table += [klen, key_start + kpos]
    for klen, kpos, vlen, vpos in offsets:
        table += [vlen, value_start + vpos]
    header = struct.pack("Iiiiiii", 0x950412DE, 0, count, 7 * 4, 7 * 4 + count * 8, 0, 0)
    path.write_bytes(header + struct.pack(f"{len(table)}i", *table) + ids + strs)


def main():
    for po in sorted((BASE_DIR / "locale").glob("*/LC_MESSAGES/django.po")):
        messages = read_po(po)
        write_mo(messages, po.with_suffix(".mo"))
        print(f"{po.relative_to(BASE_DIR)}: {len(messages)} messages")


if __name__ == "__main__":
    main()
