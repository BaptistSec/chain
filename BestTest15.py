import sys, os, tempfile, importlib.util
Here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["x"]
tmp = tempfile.mkdtemp()
os.environ["CHAIN_BEST_FILE"] = os.path.join(tmp, "best.txt")
Spec = importlib.util.spec_from_file_location("chain", os.path.join(Here, "ChainDemo.py"))
E = importlib.util.module_from_spec(Spec); Spec.loader.exec_module(E)
Fails = []
def Check(ok, text):
    print(("ok   " if ok else "FAIL ") + text)
    if not ok: Fails.append(text)
P = os.environ["CHAIN_BEST_FILE"]
Check(E.RecordBest(500) == (500, True, True), "first score is a new best, returned and saved")
Check(E.RecordBest(300) == (500, False, False), "lower score is not new and does not overwrite")
Check(open(P).read().strip() == "500", "file keeps 500 after the lower score")
Check(E.RecordBest(500) == (500, False, False), "equal score is not a new best")
Check(E.RecordBest(900) == (900, True, True) and open(P).read().strip() == "900", "higher score replaces the file")
open(P, "wb").write(b"\xff\xfe\x00junk")
Check(E.RecordBest(40) == (40, True, True), "binary garbage (bytes FF FE) is treated as no best, no exception")
open(P, "w").write("not a number")
Check(E.RecordBest(41) == (41, True, True), "text garbage is treated as no best")
open(P, "w").write("9" * 5000)
Check(E.RecordBest(42) == (42, True, True), "oversized file is rejected as no best")
open(P, "w").write("77\n")
Check(E.RecordBest(10) == (77, False, False), "valid stored best is read")
os.environ["CHAIN_BEST_FILE"] = os.path.join(tmp, "missing-dir", "best.txt")
Check(E.RecordBest(70) == (70, True, False), "unwritable location: no exception, saved is False")
Check("Not saved" in "\n".join(E.BestLines(70, True, False)) and "Saved to" not in "\n".join(E.BestLines(70, True, False)), "unsaved wording does not claim a file")
victim = os.path.join(tmp, "unrelated.txt"); open(victim, "w").write("keep me\n")
link = os.path.join(tmp, "linkbest.txt"); os.symlink(victim, link)
os.environ["CHAIN_BEST_FILE"] = link
Check(E.RecordBest(123) == (123, True, False), "symlink destination is refused: not saved")
Check(open(victim).read() == "keep me\n" and os.path.islink(link), "symlink target untouched and link intact")
pre = os.path.join(tmp, ".chainbest-" + str(os.getpid()) + ".tmp"); open(pre, "w").write("unrelated temp bytes\n")
os.environ["CHAIN_BEST_FILE"] = os.path.join(tmp, "preexisting.txt")
Check(E.RecordBest(31)[2] is True and open(pre).read() == "unrelated temp bytes\n", "a pre-existing file at the old predictable temp name is left alone")
os.environ["CHAIN_BEST_FILE"] = os.path.join(tmp, "x.txt")
real = E.os.open
def Fail(path, flags, mode=0o777, **kw):
    if os.path.basename(path).startswith(".chainbest-"):
        open(path, "w").write("collision bytes\n")
        raise FileExistsError("forced")
    return real(path, flags, mode)
E.os.open = Fail
Check(E.RecordBest(55)[2] is False, "forced exclusive-create failure reports not saved")
leftover = [n for n in os.listdir(tmp) if n.startswith(".chainbest-") and n != os.path.basename(pre)]
Check(len(leftover) == 1 and open(os.path.join(tmp, leftover[0])).read() == "collision bytes\n", "failed exclusive create does not delete the file it collided with")
E.os.open = real
for n in leftover: os.unlink(os.path.join(tmp, n))
os.unlink(pre)
hv = os.path.join(tmp, "hardvictim.txt"); open(hv, "w").write("hard bytes\n")
hl = os.path.join(tmp, "hardbest.txt"); os.link(hv, hl)
os.environ["CHAIN_BEST_FILE"] = hl
Check(E.RecordBest(222)[0] == 222 and open(hv).read() == "hard bytes\n", "hard-linked best file: unrelated inode bytes preserved")
Check(open(hl).read().strip() == "222" and os.stat(hl).st_nlink == 1, "hard-linked best file replaced by a fresh single-link file")
folder = os.path.join(tmp, "adir"); os.mkdir(folder)
os.environ["CHAIN_BEST_FILE"] = folder
Check(E.RecordBest(5) == (5, True, False), "directory destination is refused")
os.environ["CHAIN_BEST_FILE"] = os.path.join(tmp, "ok.txt")
E.RecordBest(8)
Check(not [n for n in os.listdir(tmp) if n.startswith(".chainbest")], "no temp file left behind")
Check("the file named by CHAIN_BEST_FILE" in "\n".join(E.BestLines(8, True, True)), "override wording names the override, not the default location")
del os.environ["CHAIN_BEST_FILE"]
Check("ChainBest.txt next to the game" in "\n".join(E.BestLines(8, True, True)), "default wording names ChainBest.txt")
os.environ["CHAIN_BEST_FILE"] = os.path.join(tmp, "pty.txt")
src = open(os.path.join(Here, "PtyDrive15.py")).read().split('if __name__ == "__main__":')[0]
src = src.replace('return re.sub(rb"\\x1b\\[[0-9;?]*[A-Za-z]", b"\\n", buf).decode("utf8", "replace")', 'return buf')
exec(src)
code = "CH15R-30001-9.10.10-xr-34.30.5x.2r.31/22.9x.38x.7.0r.18.3.3.34.36.11/17x.30.11.10x.33r.38r"
b = Drive(["--resume", code], ["w", "w", "n", "w"]).decode("utf8", "replace")
Check("RUN COMPLETE" in b and "Local best across completed runs" in b and "Saved to" in b, "first complete run shows personal best and says new best")
Check(os.path.exists(os.environ["CHAIN_BEST_FILE"]) and int(open(os.environ["CHAIN_BEST_FILE"]).read().strip()) > 0, "file written with the run total")
b = Drive(["--resume", code], ["w", "w", "n", "w"]).decode("utf8", "replace")
Check("Local best across completed runs" in b and "(new)" not in b and "Saved to" not in b, "same run again shows personal best without new-best wording")
sys.exit(1 if Fails else 0)
