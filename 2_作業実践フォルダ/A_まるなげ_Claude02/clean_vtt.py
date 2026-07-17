import re, sys

lines = open("koBLOf-53_g.ja.vtt", encoding="utf-8").read().splitlines()
segments = {}  # 10-min bucket -> list of text
cur_time = 0.0
last = ""
def to_sec(ts):
    h,m,s = ts.split(":")
    return int(h)*3600+int(m)*60+float(s)

i=0
buf = {}
order = []
for line in lines:
    m = re.match(r"(\d\d:\d\d:\d\d\.\d\d\d) --> (\d\d:\d\d:\d\d\.\d\d\d)", line)
    if m:
        cur_time = to_sec(m.group(1))
        continue
    if not line.strip():
        continue
    if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
        continue
    # remove inline timing tags
    txt = re.sub(r"<\d\d:\d\d:\d\d\.\d\d\d>", "", line)
    txt = re.sub(r"</?c>", "", txt)
    txt = re.sub(r"\[[^\]]*\]", "", txt)
    txt = txt.strip()
    if not txt:
        continue
    bucket = int(cur_time//600)
    if bucket not in buf:
        buf[bucket]=[]
        order.append(bucket)
    if txt != last and (not buf[bucket] or buf[bucket][-1]!=txt):
        buf[bucket].append(txt)
        last = txt

out=[]
for b in sorted(buf):
    out.append(f"\n===== SEGMENT {b:02d} ({b*10}:00-{(b+1)*10}:00) =====")
    # dedupe consecutive within
    prev=""
    for t in buf[b]:
        if t!=prev:
            out.append(t)
            prev=t
open("cleaned.txt","w",encoding="utf-8").write("\n".join(out))
print("buckets:", sorted(buf))
print("chars:", sum(len(x) for x in out))
