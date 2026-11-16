"""check_foreign_ea — decide what a third-party MT5 binary can actually touch, before it goes near a live account.

Why this exists: a vendor's `.ex5` is a compiled artifact. You cannot read its logic, but its embedded
strings DO reveal what it is able to do — DLL imports, URLs it can reach, files it opens, whether it needs
permissions outside the terminal's sandbox. That is enough to decide "install on demo", "install never", or
"install, and here is what to watch".

Usage:  python3 tools/checks/check_foreign_ea.py <path-to-file>
Exit:   0 clean / informational, 1 findings present, 2 unreadable or not an MT5 artifact.
"""
import hashlib
import os
import re
import string
import sys

# (what it means, pattern, severity)  — keep this list boring and explainable, not clever
SIGNALS = [
    ("opens a network connection itself (exfiltration or a licence check to the vendor)",
     r"(InternetOpenUrl|WinHttp|URLDownloadToFile|cURL|HttpSendRequest|wininet|ws[s]?://)", "high"),
    ("names an http(s) URL or a bare domain inside the binary",
     r"https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "high"),
    ("loads a DLL by name (outside MQL5's own imports, this is how code escapes the terminal)",
     r"\.dll\b", "high"),
    ("installs a hook or reads keystrokes (this is credential theft, not trading)",
     r"(SetWindowsHookEx|GetAsyncKeyState|GetKeyState|KbD|CreateRemoteThread|VirtualAllocEx)", "critical"),
    ("reads credential stores or browser/SQLite files",
     r"(logins\.db|Login Data|key3\.db|\.sqlite|Credentials|Password\.db|accounts\.dat)", "critical"),
    ("writes outside the MQL5 sandbox or drops files for later",
     r"(WriteFile|FileDelete|FILE_BIN|TEMP|\\\\AppData\\\\|\\\\Users\\\\|ProgramData|CurrentVersion\\\\Run)", "high"),
    ("pokes the registry (persistence, or disabling the terminal's own safety dialogs)",
     r"(RegSetValue|RegCreateKey|reg add|HKCU|HKLM)", "high"),
    ("spawns processes",
     r"(ShellExecute|CreateProcess|WinExec|system\()", "high"),
    ("touches account/login data through the terminal rather than through trade calls",
     r"(AccountInfoString|MQLInfoString|AccountBalance|Login\.dat)", "medium"),
]

MAGIC_HINTS = (b"MetaQuotes", b"MQL5", b"EX5", b"Expert Advisor", b"OnTick", b"trade_send")


def strings_from(raw, minlen=5):
    out, cur = [], []
    printable = set(string.printable) - set("\r\n\x0b\x0c")
    for ch in raw.decode("latin-1", "replace"):
        if ch in printable:
            cur.append(ch)
        else:
            if len(cur) >= minlen:
                out.append("".join(cur))
            cur = []
    if len(cur) >= minlen:
        out.append("".join(cur))
    return out


def scan(path):
    raw = open(path, "rb").read()
    blob = strings_from(raw)
    text = "\n".join(blob)
    looks_like_mt5 = any(m in raw or m.decode("latin-1").lower() in text.lower()
                         for m in MAGIC_HINTS) or path.lower().endswith((".ex5", ".mq5", "mqh"))
    findings = []
    for what, pat, sev in SIGNALS:
        hits = re.findall(pat, text, re.I)
        if hits:
            uniq = sorted({h if isinstance(h, str) else str(h) for h in hits})[:6]
            findings.append((sev, what, uniq))
    return raw, text, looks_like_mt5, findings


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    if not os.path.isfile(path):
        print("unreadable: %s" % path)
        return 2
    raw, text, mt5, findings = scan(path)
    print("file      : %s" % path)
    print("size      : %d B" % len(raw))
    print("sha256    : %s" % hashlib.sha256(raw).hexdigest())
    print("strings   : %d runs of >=5 printable chars" % len(text.splitlines()))
    print("mt5-ish   : %s   (source file = readable, review the logic line by line; a compiled .ex5 = opaque)"
          % ("yes" if mt5 else "NO — this is not an MT5 artifact"))
    order = {"critical": 0, "high": 1, "medium": 2}
    for sev, what, hits in sorted(findings, key=lambda f: order.get(f[0], 9)):
        print("  [%-8s] %s" % (sev.upper(), what))
        print("             matched: %s" % ", ".join(h[:60] for h in hits))
    if not findings:
        print("  no risky-capability strings found — on a COMPILED binary that only means they are not "
              "plainly visible; it is not proof of innocence")
    hard = [f for f in findings if f[0] in ("critical", "high")]
    print("\nVERDICT: %s" % ("%d finding(s) — do not attach to an account with money in it" % len(hard)
                             if hard else "nothing that would change my answer either way — still run it on "
                                          "demo first, with the risk clamps in front"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
