import sys
sys.argv = ["x"]
src = open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "PtyDrive12.py")).read().split('if __name__ == "__main__":')[0]
src = src.replace('return re.sub(rb"\\x1b\\[[0-9;?]*[A-Za-z]", b"\\n", buf).decode("utf8", "replace")', 'return buf')
exec(src)
Fails = []
code = "CH12R-30001-8.9.10-sr-6.6.1.32.5x.6.4r.34.34/25.9.36.10x.35r/25.28.21x.34r.1r.36s.0"
b = Drive(["--resume", code], ["w", "w", "n", "w"])
i = b.find(b"RUN COMPLETE"); j = b.find(b"\x1b[H", i)
if not (i > 0 and b"\x1b[J" in b[i:(j if j > 0 else None)][-30:]):
    Fails.append("run complete screen does not erase below")
k = Keys(30001)[0]
b = Drive(["--run", "30001"], k[:k.index("n") + 1] + ["w", "w"])
i = b.find(b"Pick one upgrade"); j = b.find(b"\x1b[H", i)
if not (i > 0 and b"\x1b[J" in b[i:(j if j > 0 else None)][-30:]):
    Fails.append("draft screen does not erase below")
print("FAIL " + "; ".join(Fails) if Fails else "ok erase-below on complete and draft screens")
sys.exit(1 if Fails else 0)
