#!/usr/bin/env python3
"""読み物の級分けレポートを index.html（単一ファイル）に書く。data.json は analyze.py が作る。
  python3 build.py [--offline]   # 公開中かどうかは本番URLへ HEAD して決める（--offline なら原稿の draft を使う）
"""
import json, html, sys, urllib.request, concurrent.futures, pathlib
import analyze

HERE = pathlib.Path(__file__).parent          # _src（GitHub Pages の Jekyll は _ 始まりを配信しない）
OUT = HERE.parent                              # 公開物（index.html / data.json）の置き場
BASE = "https://www.animesenseijp.com/library/"
JNAME = {"ok": "級どおり", "up": "1つ上に見える", "down": "1つ下に見える"}
JMARK = {"ok": "●", "up": "▲", "down": "▼"}
AX = analyze.AXIS_NAME
AX["g4"] = "N4以上の文法の種類数"
esc = html.escape


def live(slug):
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + slug + "/", method="HEAD"), timeout=15)
        return r.status == 200
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None


def f1(v): return "—" if v is None else f"{v:.1f}"
def pct(v): return "—" if v is None else f"{round(v * 100)}%"


def band_text(lv):
    n = analyze.N_OF[lv]
    if lv in ("N2", "N1"): return "N2以上"
    return f"N{n - 0.5:g}〜N{n + 0.5:g}"


def neq_word(v):
    return "絵本級" if v >= 5.995 else f"N{v:.1f}相当"


def nb(t):  # 数字と単位の途中で折れないように束ねる
    return f'<span class="nb">{esc(t)}</span>'


def reason(b):
    """→ (本文HTML, 目安HTML)。数字と単位は nowrap の塊にする"""
    lv, j = b["level"], b["j"]
    v2 = analyze.V2_TEXT[lv]
    dirw = "難しい" if j == "up" else "易しい"
    s1 = f"tadoku に当てると {nb('N%.2f 相当' % b['neq'])}で、{lv} の帯（{nb(band_text(lv))}）より{dirw}側です。"
    offs = [a for a, x in b["axes"].items() if x["j"] == j]
    fmt = {"mean": lambda v: f"{v:.1f}字", "p90": lambda v: f"{v:g}字", "kt": lambda v: f"{v:g}字", "g4": lambda v: f"{v:g}種"}
    if offs:
        s2 = "帯を外れた指標は " + "、".join(f"{nb(AX[a])} {nb(fmt[a](b['axes'][a]['value']))}（{nb(neq_word(b['axes'][a]['neq']))}）" for a in offs) + "。"
    else:
        s2 = "どの指標も単独では帯の内側で、4つを合わせると外に出ました。"
    s3 = f"目安は平均文長 {nb(v2['mean'])}・P90 {nb(v2['p90'])}。この本は {nb('%.1f字' % b['mean'])}・{nb('%d字' % b['p90'])}です。"
    return s1 + s2, s3


def main():
    off = "--offline" in sys.argv
    D = analyze.analyze()
    books = D["books"]
    by = {b["slug"]: b for b in books}
    if not off:
        with concurrent.futures.ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda b: live(b["slug"]), books))
        for b, r in zip(books, res):
            b["live"] = (not b["draft"]) if r is None else r
    else:
        for b in books: b["live"] = not b["draft"]
    D["n_live"] = sum(b["live"] for b in books)
    json.dump(D, open(OUT / "data.json", "w"), ensure_ascii=False, indent=1)

    def title_html(b, cls=""):
        t = esc(b["title"])
        return f'<a class="tt {cls}" href="{BASE}{b["slug"]}/" target="_blank" rel="noopener">{t}</a>' if b["live"] else f'<span class="tt {cls}">{t}</span>'

    c = D["counts"]
    kpi = (
        f'<div class="kpi"><b class="big">{c["ok"]}</b><span class="kl">冊が級どおり</span></div>'
        f'<div class="kpi up"><b class="big">{c["up"]}</b><span class="kl">冊が1つ上に見える</span></div>'
        f'<div class="kpi down"><b class="big">{c["down"]}</b><span class="kl">冊が1つ下に見える</span></div>'
    )

    nxt = ""
    for i, s in enumerate(D["next3"], 1):
        b = by[s]; s12, s3 = reason(b)
        nxt += (f'<li id="n{i}"><span class="rkn">{i}</span><div class="nb-body">'
                f'<h3><span class="lv">{b["level"]}</span> {title_html(b)} <span class="j {b["j"]}">{JMARK[b["j"]]} {JNAME[b["j"]]}</span></h3>'
                f'<p>{s12}</p><p class="dim">{s3}</p></div></li>')

    rows = ""
    for l in D["levels"]:
        lv = l["level"]; tl = l["tadoku_levels"]
        tname = "対応級なし" if not tl else ("L" + "〜".join(tl))
        outs = "、".join(esc(by[s]["title"]) + f'（{JMARK[by[s]["j"]]}）' for s in l["outliers"]) or "なし"
        draft = f'（未公開 {l["n"] - sum(by[b["slug"]]["live"] for b in books if b["level"] == lv)}）'
        rows += (f'<tr><th scope="row"><span class="lv">{lv}</span><small>tadoku {tname}</small></th>'
                 f'<td data-l="冊数" class="num">{l["n"]}</td>'
                 f'<td data-l="平均文長" class="num">{l["mean"]:.1f}<small>目安 {esc(l["v2"]["mean"])}</small></td>'
                 f'<td data-l="文長P90" class="num">{l["p90"]:.1f}<small>目安 {esc(l["v2"]["p90"])}</small></td>'
                 f'<td data-l="漢字割合" class="num">{pct(l["kanji_ratio"])}<small>目安 {esc(l["v2"]["kanji"])}</small></td>'
                 f'<td data-l="です・ます文" class="num">{pct(l["polite"])}<small>目安 {esc(l["v2"]["polite"])}</small></td>'
                 f'<td data-l="N換算の平均" class="num">{l["neq"]:.2f}</td>'
                 f'<td data-l="判定の内訳" class="jn"><span class="ok" title="級どおり">●{l["ok"]}</span><span class="up" title="1つ上に見える">▲{l["up"]}</span><span class="down" title="1つ下に見える">▼{l["down"]}</span></td>'
                 f'<td data-l="外れ値" class="out">{outs}</td></tr>')

    trs = ""
    order = sorted(books, key=lambda b: (analyze.ORDER.index(b["level"]), 0 if b["j"] != "ok" else 1, -b["dev"] if b["j"] != "ok" else -b["neq"]))
    for b in order:
        ax = b["axes"]
        def cell(a, txt, label):
            cls = "" if ax[a]["j"] == "ok" else f' off-{ax[a]["j"]}'
            return f'<td class="num{cls}" data-l="{label}" title="{AX[a]} → N{ax[a]["neq"]:.2f} 相当">{txt}</td>'
        status = "" if b["live"] else '<span class="dr">未公開</span>'
        trs += (f'<tr class="bk{"" if b["j"] == "ok" else " fl"}" id="b-{b["slug"]}" data-lv="{b["level"]}" data-j="{b["j"]}">'
                f'<td class="c-lv"><span class="lv">{b["level"]}</span></td>'
                f'<td class="c-t"><span class="lv lvm">{b["level"]}</span>{title_html(b)}</td>'
                f'<td class="c-j"><span class="j {b["j"]}">{JMARK[b["j"]]} {JNAME[b["j"]]}</span>{status}</td>'
                f'<td class="num" data-l="N換算">{b["neq"]:.2f}</td>'
                f'<td class="num" data-l="字数">{b["chars"]}</td>'
                + cell("mean", f1(b["mean"]), "平均文長") + cell("p90", str(b["p90"]), "文長P90")
                + f'<td class="num" data-l="漢字割合">{pct(b["kanji_ratio"])}</td><td class="num" data-l="です・ます">{pct(b["polite"])}</td>'
                + cell("kt", str(b["kanji_types"]), "異なり漢字") + cell("g4", str(b["gram_n4plus"]), "N4+文法")
                + f'<td class="num" data-l="自級の文法">{b["gram_own"]}</td><td class="num" data-l="v2警告">{b["v2_n"]}</td></tr>')
        if b["j"] != "ok":
            s12, s3 = reason(b)
            trs += f'<tr class="why" data-lv="{b["level"]}" data-j="{b["j"]}"><td colspan="13">{s12}</td></tr>'

    M = D["method"]; keys = M["tadoku_keys"]
    names = {"start": "start", "0": "L0", "1": "L1", "2": "L2", "3": "L3", "4": "L4"}
    anch = "".join(
        f'<tr><th scope="row">{AX[a]}</th>' + "".join(f'<td class="num">{round(M["tadoku_medians"][a][k], 1):g}</td>' for k in keys) + "</tr>"
        for a in ("mean", "p90", "kt", "g4"))
    anch_head = "".join(f'<th scope="col">{names[k]}<small>{M["tadoku_n_books"][k]}冊</small></th>' for k in keys)

    n_live, n_all = D["n_live"], D["n_books"]
    page = TEMPLATE
    for k, v in {
        "KPI": kpi, "NEXT3": nxt, "LEVELROWS": rows, "BOOKROWS": trs, "ANCH": anch, "ANCHHEAD": anch_head,
        "NALL": str(n_all), "NLIVE": str(n_live), "NDRAFT": str(n_all - n_live), "DATE": D["generated"],
        "DATA": json.dumps(D, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(f"@@{k}@@", v)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print("wrote index.html", len(page), "bytes; live", n_live, "/", n_all, "counts", c)


TEMPLATE = (pathlib.Path(__file__).parent / "template.html").read_text(encoding="utf-8")
if __name__ == "__main__":
    main()
