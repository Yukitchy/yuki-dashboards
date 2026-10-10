#!/usr/bin/env python3
"""読み物の級分けレポートの採点（機械判定のみ）。全項目✅で終了コード0。
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 check.py [--url http://localhost:8765/index.html] [--published] [--shots DIR]
--published を付けると、公開URL・図鑑トップのカード・既存ページ不変も見る（push 後に実行）。
"""
import sys, re, json, math, pathlib, subprocess, urllib.request, difflib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent
ROOT = OUT.parent                                   # ~/dashboard-zukan
SEO = pathlib.Path.home() / "affiliate-kit/factory/seo"
LIB = pathlib.Path.home() / "workspace/lesson-booking-plan/site/src/content/library"
PUB = "https://yukitchy.github.io/yuki-dashboards/library-levels/"
BASE = "https://www.animesenseijp.com/library/"
BASE_COMMIT = "649d988"                              # 図鑑トップに触る前の最後のコミット
args = sys.argv[1:]
URL = args[args.index("--url") + 1] if "--url" in args else "http://localhost:8765/index.html"
PUBLISHED = "--published" in args
SHOTS = pathlib.Path(args[args.index("--shots") + 1]) if "--shots" in args else None

D = json.load(open(OUT / "data.json"))
B = D["books"]
HTML = (OUT / "index.html").read_text(encoding="utf-8")
R = []   # (id, 名前, ok, 証拠)


def rec(i, name, ok, ev):
    R.append((i, name, ok, ev))


def head(url):
    import time
    code = None
    for _ in range(4):
        try:
            code = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 (Macintosh) check"}), timeout=20).status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            code = str(e)[:40]
        if code in (200, 404): return code
        time.sleep(2)        # 403 や一時エラーは間をおいて取り直す
    return code


# ---- 独立の再計算（analyze.py / metrics.py を使わない） ----
KANA = re.compile(r"[ぁ-んァ-ヶー一-鿿々]")
KJ = re.compile(r"[一-鿿々]")
POL = re.compile(r"(です|ます|ました|でした|ません|ましょう|でしょう|ください)[かねよ]*$")


def raw_metrics(path):
    t = path.read_text(encoding="utf-8")
    body = re.match(r"^---\n.*?\n---\n(.*)$", t, re.S).group(1)
    story = re.split(r"\n## (?:Questions|Words in this story)", body)[0]
    ss = [s for s in (re.sub(r"[」』）\s]+$", "", x) for x in re.split(r"[。！？!?\n]", story)) if re.search(r"[ぁ-んァ-ヶ一-鿿]", s)]
    ln = sorted(len(KANA.findall(s)) for s in ss)
    return {"chars": sum(ln), "sentences": len(ln), "mean": sum(ln) / len(ln), "p90": ln[min(len(ln) - 1, int(len(ln) * .9))],
            "kr": len(KJ.findall(story)) / sum(ln), "kt": len(set(KJ.findall(story))), "pol": sum(bool(POL.search(s)) for s in ss) / len(ss)}


T = json.load(open(SEO / "tadoku_profile.json"))["levels"]
KS = ["start", "0", "1", "2", "3", "4"]
Y = {"mean": [T[k]["sent_mean"][1] for k in KS], "p90": [T[k]["sent_p90"][1] for k in KS], "kt": [T[k]["kanji_types"][1] for k in KS],
     "g4": [sum(T[k][f"gram_types_{x}"][1] for x in ("N4", "N3", "N2", "N1")) for k in KS]}


def lval(v, ys):
    xs = [-1, 0, 1, 2, 3, 4]
    if v <= ys[0]: return -1.0
    if v >= ys[-1]: return 4.0
    for i in range(5):
        if ys[i] <= v <= ys[i + 1]: return xs[i] + (v - ys[i]) / (ys[i + 1] - ys[i]) if ys[i + 1] != ys[i] else xs[i]


def nval(L):
    pts = [(-1, 6), (.5, 5), (1.5, 4), (3, 3), (4, 2)]
    for (a, b), (c, e) in zip(pts, pts[1:]):
        if a <= L <= c: return b + (e - b) * (L - a) / (c - a)
    return 6.0 if L < -1 else 2.0


def verdict(label, n):
    k = {"N5": 5, "N4": 4, "N3": 3, "N2": 2, "N1": 1}[label]
    if label in ("N2", "N1"): return ("down", n - 2.5) if n > 2.5 else ("ok", 0)
    return ("up", k - .5 - n) if n < k - .5 else ("down", n - k - .5) if n > k + .5 else ("ok", 0)


# 1 DATA-70
need = ["chars", "sentences", "mean", "p90", "kanji_ratio", "kanji_types", "polite", "gram_own", "gram_above", "level", "j", "neq", "title", "slug"]
bad = [(b["slug"], k) for b in B for k in need if b.get(k) is None or (isinstance(b[k], float) and not math.isfinite(b[k]))]
rec(1, "data.json に70冊・必須14項目・欠損なし", len(B) == 70 and not bad and len({b["slug"] for b in B}) == 70, f"{len(B)}冊 欠損{len(bad)}")

# 2 TOOL-MATCH（library_check.py をCLIで実行して照合）
files = sorted(str(p) for p in LIB.glob("*.md"))
cp = subprocess.run(["python3", str(SEO / "library_check.py"), *files], capture_output=True, text=True, cwd=str(SEO))
per, cur = {}, None
for line in cp.stdout.splitlines():
    m = re.match(r"(?:OK|NG) (\S+)\.md \((\d+)字\)", line)
    if m: cur = m.group(1); per[cur] = [int(m.group(2)), 0]
    elif cur and line.strip().startswith("? v2 "): per[cur][1] += 1
mis = [b["slug"] for b in B if b["slug"] not in per or per[b["slug"]] != [b["chars"], b["v2_n"]]]
rec(2, "library_check.py のCLI出力（字数とv2警告本数）が全冊一致", not mis and len(per) == 70, f"CLI {len(per)}冊 v2警告計{sum(v[1] for v in per.values())}件 / data {sum(b['v2_n'] for b in B)}件 不一致{len(mis)}")

# 8a 独立再計算（指標とN換算）
dm, dn = [], []
for b in B:
    m = raw_metrics(LIB / f"{b['slug']}.md")
    if abs(m["mean"] - b["mean"]) > .006 or m["p90"] != b["p90"] or abs(m["kr"] - b["kanji_ratio"]) > .0006 or m["kt"] != b["kanji_types"] or abs(m["pol"] - b["polite"]) > .0006 or m["chars"] != b["chars"]:
        dm.append(b["slug"])
    L = (lval(b["mean"], Y["mean"]) + lval(b["p90"], Y["p90"]) + lval(b["kanji_types"], Y["kt"]) + lval(b["gram_n4plus"], Y["g4"])) / 4
    n = nval(L); j, dev = verdict(b["level"], n)
    if abs(n - b["neq"]) > .002 or j != b["j"] or abs(dev - b["dev"]) > .002: dn.append(b["slug"])
rec(3, "字数・文長・P90・漢字割合・漢字種・です/ます率・N換算・判定を別実装で再計算して全冊一致", not dm and not dn, f"指標不一致{len(dm)} N換算/判定不一致{len(dn)}")

# 4 JUDGE-3
cnt = {j: sum(b["j"] == j for b in B) for j in ("ok", "up", "down")}
kp = re.findall(r'<div class="kpi[^"]*"><b class="big">(\d+)</b>', HTML)
rec(4, "判定は3値のみで合計70、冒頭の集計表示がデータと一致", sum(cnt.values()) == 70 and [int(x) for x in kp] == [cnt["ok"], cnt["up"], cnt["down"]], f"data {cnt} / 画面 {kp}")

# 5 NEXT3
fl = sorted([b for b in B if b["j"] != "ok"], key=lambda b: (-b["dev"], b["draft"]))[:3]
nx = re.findall(r'<li id="n\d"><span class="rkn">\d</span><div class="nb-body"><h3><span class="lv">(N\d)</span> (?:<a[^>]*>)?<?s?[^>]*?>?([^<]+)', HTML)
nx_titles = re.findall(r'<li id="n\d">.*?<h3><span class="lv">N\d</span> (?:<a [^>]*>([^<]+)</a>|<span class="tt ">([^<]+)</span>)', HTML)
nx_titles = [a or b for a, b in nx_titles]
okp = all(re.search(r"<p>tadoku に当てると .+?</p><p class=\"dim\">目安は", seg) for seg in re.findall(r'<li id="n\d">.*?</li>', HTML))
rec(5, "次に直す3冊がちょうど3冊で、はみ出し距離の順に再計算した3冊と一致し、各冊に理由と目安がある", len(nx_titles) == 3 and nx_titles == [b["title"] for b in fl] and okp, f"画面 {nx_titles} / 再計算 {[b['title'] for b in fl]}")

# 7 SUMMARY
sm = re.findall(r'<tr><th scope="row"><span class="lv">(N\d)</span><small>[^<]*</small></th><td[^>]*>(\d+)</td><td[^>]*>([\d.]+)<small>[^<]*</small></td><td[^>]*>([\d.]+)<small>[^<]*</small></td><td[^>]*>(\d+)%<small>[^<]*</small></td><td[^>]*>(\d+)%<small>[^<]*</small></td><td[^>]*>([\d.]+)</td><td[^>]*>.*?●(\d+).*?▲(\d+).*?▼(\d+)', HTML)
bad7 = []
for row in sm:
    lv = row[0]; bs = [b for b in B if b["level"] == lv]
    av = lambda k: sum(b[k] for b in bs) / len(bs)
    exp = [str(len(bs)), f"{av('mean'):.1f}", f"{av('p90'):.1f}", str(round(av("kanji_ratio") * 100)), str(round(av("polite") * 100)), f"{av('neq'):.2f}",
           str(sum(b["j"] == "ok" for b in bs)), str(sum(b["j"] == "up" for b in bs)), str(sum(b["j"] == "down" for b in bs))]
    if list(row[1:]) != exp: bad7.append((lv, row[1:], exp))
rec(6, "級別要約5行の平均・P90・漢字割合・です/ます・N換算・判定内訳が全冊から再計算した値と一致", len(sm) == 5 and not bad7, f"{len(sm)}行 不一致{bad7[:1]}")

# 9 NO-FAKE / 10 COPY
text = re.sub(r"<script.*?</script>|<style.*?</style>", "", HTML, flags=re.S)
vis = re.sub(r"<[^>]+>", " ", text)
fake = re.findall(r"\b(NaN|undefined|None|null|Infinity)\b", vis)
rec(7, "画面に NaN・undefined・None・null・Infinity の文字が0", not fake, f"{len(fake)}件")
dash = re.findall(r"[—–]", vis)
emoji = re.findall(r"[\U0001F000-\U0001FAFF☀-➿⭐⭕]", vis)
midd = vis.count("·")
heads = re.findall(r"<h[123][^>]*>(.*?)</h[123]>", text, re.S)
hp = [re.sub(r"<[^>]+>", "", h) for h in heads if re.search(r"[、。]", re.sub(r"<[^>]+>", "", h))]
hbr = [h for h in heads if "<br" in h]
banned = re.findall(r"スクロール|Scroll|^\s*0\d\s*/", vis, re.M)
rec(8, "ダッシュ・絵文字・中黒・見出しの読点句点・見出しの<br>・禁止語がすべて0", not (dash or emoji or midd or hp or hbr or banned), f"dash{len(dash)} emoji{len(emoji)} 中黒{midd} 見出し句読点{len(hp)} br{len(hbr)} 禁止語{len(banned)}")

# 17 FAVICON
fav = re.search(r'<link rel="icon" type="image/png" sizes="32x32" href="([^"]+)"', HTML)
fok = bool(fav) and not fav.group(1).startswith("data:") and (OUT / fav.group(1)).exists() and "apple-touch-icon.png" in HTML
rec(9, "ファビコンはPNGファイル参照（data URIでない）で、32pxと180pxのファイルが存在", fok, f"{fav.group(1) if fav else None}")

# ---- ブラウザ計測 ----
JS_LINES = r"""
(sel)=>{const out=[];
 for(const el of document.querySelectorAll(sel)){
  if(!el.getClientRects().length) continue;
  const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let n,chars=[],ni=0;
  while(n=w.nextNode()){const t=n.textContent;for(let i=0;i<t.length;i++){if(/\s/.test(t[i]))continue;const r=document.createRange();r.setStart(n,i);r.setEnd(n,i+1);const q=r.getClientRects()[0];if(q&&q.width>0)chars.push([t[i],q.top,q.left,ni])}ni++}
  if(!chars.length) continue;
  const lines=[];let cur=[chars[0]];
  for(let i=1;i<chars.length;i++){if(Math.abs(chars[i][1]-cur[cur.length-1][1])>4&&chars[i][2]<cur[cur.length-1][2]-2){lines.push(cur);cur=[chars[i]]}else cur.push(chars[i])}
  lines.push(cur);
  const txt=(el.textContent||'').trim().slice(0,24);
  if(lines.length>1){
   const last=lines[lines.length-1];
   if(last.length<=2) out.push('孤立行 '+txt+' → '+last.map(c=>c[0]).join(''));
   for(let i=0;i<lines.length-1;i++){const a=lines[i][lines[i].length-1][0],b=lines[i+1][0][0];
     if(lines[i][lines[i].length-1][3]===lines[i+1][0][3]&&/[0-9A-Za-z.%+]/.test(a)&&/[0-9A-Za-z.%字種冊]/.test(b)) out.push('語中折れ '+txt+' '+a+'|'+b);
     if(/[、。，．）」』!?]/.test(b)) out.push('行頭禁則 '+txt+' |'+b)}
  }
 }
 return out}
"""
JS_MEASURE = r"""
()=>{const W=innerWidth,res={W,sw:document.documentElement.scrollWidth,over:[],small:[],fams:[],colors:[],lvcolor:[]};
 const fam=new Set(),col=new Set();
 document.querySelectorAll('body *').forEach(e=>{
  if(['SCRIPT','STYLE','NOSCRIPT'].includes(e.tagName))return;
  const r=e.getBoundingClientRect(),cs=getComputedStyle(e);
  if(cs.display==='none'||cs.visibility==='hidden'||!e.getClientRects().length)return;
  if(r.width>0&&r.right>W+1)res.over.push(e.tagName+'.'+e.className+' '+Math.round(r.right));
  const hasText=[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
  if(hasText){fam.add(cs.fontFamily.split(',')[0].replace(/"/g,'').trim());if(parseFloat(cs.fontSize)<13)res.small.push(e.tagName+'.'+e.className+' '+cs.fontSize+' '+e.textContent.trim().slice(0,12));
   col.add(cs.color)}
  col.add(cs.backgroundColor);col.add(cs.borderTopColor);col.add(cs.borderBottomColor);
  if(e.classList.contains('lv')&&(cs.backgroundColor!=='rgb(10, 10, 10)'))res.lvcolor.push(cs.backgroundColor);
 });
 res.fams=[...fam];
 res.colors=[...col].filter(c=>c&&c!=='rgba(0, 0, 0, 0)').map(c=>c.match(/\d+(\.\d+)?/g).slice(0,3).map(Number)).filter(c=>Math.max(...c)-Math.min(...c)>6).map(c=>c.join(','));
 res.colors=[...new Set(res.colors)];
 return res}
"""
JS_DOTS = r"""
()=>{const o={};
 for(const [id,sel] of [['main','#chart-main'],...[...document.querySelectorAll('.panel .chart')].map(e=>['p-'+e.id,'#'+e.id])]){
  const host=document.querySelector(sel),hr=host.getBoundingClientRect();
  const dots=[...host.querySelectorAll('.dot')].map(d=>{const r=d.getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2,d:r.width,s:d.dataset.s,lv:d.dataset.lv}});
  let ov=0,out=0;
  for(const d of dots){if(d.x<hr.left||d.x>hr.right||d.y<hr.top||d.y>hr.bottom)out++}
  for(let i=0;i<dots.length;i++)for(let j=i+1;j<dots.length;j++){if(Math.hypot(dots[i].x-dots[j].x,dots[i].y-dots[j].y)<(dots[i].d+dots[j].d)/2-0.5)ov++}
  o[id]={n:dots.length,rows:host.querySelectorAll('.row').length,ov,out,rowsLv:[...host.querySelectorAll('.row .rl')].map(e=>e.textContent.slice(0,2))}}
 return o}
"""
LINE_SEL = "h1,h2,h3,.lead,.sub,.kl,.meta,.legend span,.next p,.next h3,a.tt,.j,.dr,.cnt,.why td,.sum th,.sum td,.rl,.note,.axis span,.panel p,.method li,.method p,.chip,.back,.fi a,.jn,.bks .c-t"
ALLOWED = {"196,43,28", "29,78,216", "255,138,122", "157,184,255"}   # 赤(上)・青(下)・ツールチップ内の同色の明るい版


def browser():
    VP = [("pc1280", {"viewport": {"width": 1280, "height": 900}}), ("pc1024", {"viewport": {"width": 1024, "height": 800}}),
          ("sp390", None), ("sp320", {"viewport": {"width": 320, "height": 640}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True})]
    info = {}
    with sync_playwright() as p:
        br = p.webkit.launch()
        for name, opt in VP:
            if name == "sp390": opt = {**p.devices["iPhone 14"]}
            if name == "sp320": opt = {**p.devices["iPhone 14"], **opt}
            ctx = br.new_context(**opt, locale="ja-JP")
            pg = ctx.new_page(); errs = []
            pg.on("console", lambda m, e=errs: e.append(f"{m.type}: {m.text}") if m.type in ("error",) else None)
            pg.on("pageerror", lambda x, e=errs: e.append(f"pageerror: {x}"))
            pg.on("requestfailed", lambda r, e=errs: e.append(f"reqfail: {r.url}"))
            pg.goto(URL, wait_until="networkidle", timeout=90000); pg.wait_for_timeout(900)
            info[name] = {"m": pg.evaluate(JS_MEASURE), "dots": pg.evaluate(JS_DOTS), "lines": pg.evaluate(JS_LINES, LINE_SEL), "errs": errs}
            # ツールチップと絞り込みの動作
            if name in ("pc1280", "sp390"):
                pg.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                pg.locator('#chart-main .dot.rk').first.scroll_into_view_if_needed()
                pg.locator('#chart-main .dot.rk').first.click(); pg.wait_for_timeout(300)
                info[name]["tip"] = pg.evaluate("(()=>{const t=document.getElementById('tip');const r=t.getBoundingClientRect();return {hidden:t.hidden,inview:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,text:t.innerText.slice(0,60)}})()")
                pg.locator('#f-j .chip[data-v="up"]').click(); pg.wait_for_timeout(200)
                info[name]["filter_up"] = pg.evaluate("[...document.querySelectorAll('#books tr.bk')].filter(t=>!t.hidden&&getComputedStyle(t).display!=='none').length")
                pg.locator('#f-j .chip[data-v="all"]').click()
                pg.locator('#f-lv .chip[data-v="N3"]').click(); pg.wait_for_timeout(200)
                info[name]["filter_n3"] = pg.evaluate("[...document.querySelectorAll('#books tr.bk')].filter(t=>!t.hidden&&getComputedStyle(t).display!=='none').length")
                pg.locator('#f-lv .chip[data-v="all"]').click()
            if SHOTS and name in ("pc1280", "sp390"):
                SHOTS.mkdir(parents=True, exist_ok=True)
                tag = "pc" if name.startswith("pc") else "sp"
                pg.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                pg.screenshot(path=str(SHOTS / f"{tag}-top.png"))
                pg.screenshot(path=str(SHOTS / f"{tag}-full.png"), full_page=True)
            ctx.close()
        br.close()
    return info


I = browser()
pc, sp, s320, p1024 = I["pc1280"], I["sp390"], I["sp320"], I["pc1024"]

# 6 OVERVIEW
ov_ok, ov_ev = True, []
for k in ("pc1280", "sp390", "sp320"):
    d = I[k]["dots"]; m = d["main"]
    good = m["n"] == 70 and m["rows"] == 5 and m["ov"] == 0 and m["out"] == 0 and m["rowsLv"] == ["N5", "N4", "N3", "N2", "N1"]
    pn = [v for kk, v in d.items() if kk != "main"]
    good = good and len(pn) == 6 and all(v["n"] == 70 and v["ov"] == 0 and v["out"] == 0 for v in pn)
    ov_ok &= good; ov_ev.append(f"{k}: 散布70点 重なり{m['ov']} 域外{m['out']} / パネル{len(pn)}枚 重なり計{sum(v['ov'] for v in pn)}")
rec(10, "1画面の散布図に70点・N5〜N1の5行、点の重なり0・描画域外0（6パネルも同じ）", ov_ok, " | ".join(ov_ev))
rec(11, "点を押すとツールチップが出て画面内に収まる／判定の絞り込みがデータの冊数と一致",
    all(I[k]["tip"]["hidden"] is False and I[k]["tip"]["inview"] for k in ("pc1280", "sp390")) and all(I[k]["filter_up"] == cnt["up"] + 0 * 1 and I[k]["filter_n3"] == 14 for k in ("pc1280", "sp390")),
    f"tip {pc['tip']['inview']}/{sp['tip']['inview']} 絞り込み 上={pc['filter_up']}/{sp['filter_up']}(期待{cnt['up']}) N3={pc['filter_n3']}/{sp['filter_n3']}(期待14)")

# 12 TYPE / 13 NOSCROLLX / 14 ORPHAN / 15 COLOR
small = {k: I[k]["m"]["small"] for k in I}
fams = set().union(*[set(I[k]["m"]["fams"]) for k in I])
rec(12, "全テキスト13px以上（PC・スマホ4幅）・フォントは2系統以内・丸ゴシック指定なし", not any(small.values()) and len(fams) <= 2 and "Rounded" not in HTML and "Maru" not in HTML, f"12px未満{sum(len(v) for v in small.values())}件 フォント{sorted(fams)}")
rec(13, "横スクロールなし（1280・1024・390・320幅で scrollWidth ≤ 画面幅、はみ出す要素0）", all(I[k]["m"]["sw"] <= I[k]["m"]["W"] and not I[k]["m"]["over"] for k in I), " / ".join(f"{k}:{I[k]['m']['sw']}≤{I[k]['m']['W']} over{len(I[k]['m']['over'])}" for k in I))
lines = {k: I[k]["lines"] for k in I}
rec(14, "見出し・書名・要約・説明文に語中折れ・数字と単位の分断・1〜2字の孤立行・行頭禁則が0（4幅）", not any(lines.values()), f"{sum(len(v) for v in lines.values())}件 例:{next((v[:2] for v in lines.values() if v), [])}")
cols = set().union(*[set(I[k]["m"]["colors"]) for k in I]); lvc = [x for k in I for x in I[k]["m"]["lvcolor"]]
rec(15, "色は判定の赤と青の2色だけ（他は無彩色）で、級のラベルには色がない", cols <= ALLOWED and not lvc, f"有彩色{sorted(cols)} 級ラベルの色付き{len(lvc)}")
rec(16, "実測: コンソールエラー0・失敗リクエスト0（PC・スマホ全幅）", not any(I[k]["errs"] for k in I), f"{[(k, I[k]['errs'][:1]) for k in I if I[k]['errs']] or 'なし'}")

# 3 LINKS（全冊の本番URLを確認）
bad_l = []
for b in B:
    code = head(BASE + b["slug"] + "/")
    row = re.search(rf'<tr class="bk[^"]*" id="b-{re.escape(b["slug"])}".*?</tr>', HTML)
    linked = bool(row and f'href="{BASE}{b["slug"]}/"' in row.group(0))
    badge = bool(row and "未公開" in row.group(0))
    if b["live"]:
        if not (code == 200 and linked and not badge): bad_l.append((b["slug"], code, "live"))
    else:
        if not (code == 404 and not linked and badge): bad_l.append((b["slug"], code, "draft"))
rows_n = len(re.findall(r'<tr class="bk', HTML))
rec(17, "全70行が揃い、公開中の行は本番URLへリンクして実際に200、未公開の行はリンクなし・バッジありで実際に404", rows_n == 70 and not bad_l, f"行{rows_n} 公開中{sum(b['live'] for b in B)} 未公開{sum(not b['live'] for b in B)} 不一致{bad_l[:2]}")

# 公開後のチェック
if PUBLISHED:
    pc_code = head(PUB); dj = head(PUB + "data.json"); fv = head(PUB + "favicon-32.png"); ap = head(PUB + "apple-touch-icon.png"); src = head(PUB + "_src/build.py")
    body = urllib.request.urlopen(PUB, timeout=30).read().decode("utf-8", "replace")
    rec(18, "公開URLが200で、本文に主要文言と70行がある（data.json・ファビコン200、_src は配信されない）", pc_code == 200 and "読み物の級分けレポート" in body and body.count('<tr class="bk') == 70 and dj == 200 and fv == 200 and ap == 200 and src == 404, f"{PUB} {pc_code} / data {dj} fav {fv} apple {ap} _src {src}")
    new = (ROOT / "index.html").read_text(encoding="utf-8")
    old = subprocess.run(["git", "show", f"{BASE_COMMIT}:index.html"], capture_output=True, text=True, cwd=ROOT).stdout
    dl = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    removed = [l for l in dl if l.startswith("-")]
    changed = subprocess.run(["git", "diff", "--name-only", BASE_COMMIT, "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.split()
    others = [f for f in changed if f != "index.html" and not f.startswith("library-levels/")]
    cards = len(re.findall(r'<(?:a|div) class="card"', new)); old_cards = len(re.findall(r'<(?:a|div) class="card"', old))
    idx = head("https://yukitchy.github.io/yuki-dashboards/")
    rec(19, "図鑑トップはカード1枚の追加だけ（既存カードは全部残る・削除行2以下）、options*.html など他は不変、トップは200", cards == old_cards + 1 and len(removed) <= 2 and not others and idx == 200, f"カード {old_cards}→{cards} 削除行{len(removed)} 他ファイル変更{others} トップ{idx}")
else:
    rec(18, "公開URL・図鑑トップ・既存ページ不変（--published で実施）", False, "未実施（push 後に --published で実行）")

# 出力
w = lambda s, n: s + " " * max(0, n - len(s))
print("| # | 項目 | 結果 | 証拠 |\n|---|---|---|---|")
for i, name, ok, ev in sorted(R, key=lambda r: r[0]):
    print(f"| {i} | {name} | {'✅' if ok else '❌'} | {ev} |")
n_ok = sum(r[2] for r in R)
print(f"\n{n_ok}/{len(R)} 項目✅")
sys.exit(0 if n_ok == len(R) else 1)
