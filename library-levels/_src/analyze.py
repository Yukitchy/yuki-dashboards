#!/usr/bin/env python3
"""読み物の級分け判定。metrics.py の指標を tadoku の級別中央値で N 換算し、現級との差で判定する。標準ライブラリのみ。
  python3 analyze.py   → data.json を書く（build.py が読む）
物差し: 平均文長・文長P90・異なり漢字数・N4以上の文法の種類数 の4指標を、tadoku(start,L0..L4)の中央値に線形補間して
L 値にし、4つの平均を N 換算（L0.5=N5 / L1.5=N4 / L3=N3 / L4=N2）。四捨五入した N が現級より難しければ up、易しければ down。
"""
import json, pathlib, datetime
import metrics

HERE = pathlib.Path(__file__).parent          # _src（GitHub Pages の Jekyll は _ 始まりを配信しない）
OUT = HERE.parent                              # 公開物（index.html / data.json）の置き場
SEO = pathlib.Path.home() / "affiliate-kit/factory/seo"
T = json.load(open(SEO / "tadoku_profile.json"))["levels"]
LV_KEYS = ["start", "0", "1", "2", "3", "4"]
XS = [-1, 0, 1, 2, 3, 4]                        # start を L=-1 に置く
N_OF = {"N5": 5, "N4": 4, "N3": 3, "N2": 2, "N1": 1}
ORDER = ["N5", "N4", "N3", "N2", "N1"]
# tadoku L → N 換算の折れ線（TADOKU_PROFILE.md: N5≈L0-1, N4≈L1-2, N3≈L3, N2≈L4）。start は N6（絵本級）
PTS = [(-1, 6.0), (0.5, 5.0), (1.5, 4.0), (3.0, 3.0), (4.0, 2.0)]
# 自級にあたる tadoku 級（指標パネルの目印用）
MAPPED = {"N5": ["0", "1"], "N4": ["1", "2"], "N3": ["3"], "N2": ["4"], "N1": []}
# LIBRARY.md 物差し v2 の目安（表示用）
V2_TEXT = {
    "N5": {"mean": "11〜13字", "p90": "18字以内", "kanji": "約20%", "polite": "約70%以上"},
    "N4": {"mean": "14〜16字", "p90": "27字以内", "kanji": "20〜25%", "polite": "約75%以上"},
    "N3": {"mean": "約21字", "p90": "33字以内", "kanji": "約25%", "polite": "約80%以上"},
    "N2": {"mean": "約25字", "p90": "42字以内", "kanji": "26〜28%", "polite": "なし"},
    "N1": {"mean": "26字以上", "p90": "42字以上", "kanji": "なし", "polite": "なし"}  # N1 は TADOKU_PROFILE.md の運用案（平均26以上・P90 42以上）,
}


def med(k, m):
    return T[k][m][1]


def g4(k):  # tadoku の級別中央値の和（N4+N3+N2+N1 の文法の種類数）
    return sum(med(k, f"gram_types_{x}") for x in ("N4", "N3", "N2", "N1"))


AXES = {  # 指標名: (book のキー, tadoku 各級の中央値)
    "mean": ("mean", [med(k, "sent_mean") for k in LV_KEYS]),
    "p90": ("p90", [med(k, "sent_p90") for k in LV_KEYS]),
    "kt": ("kanji_types", [med(k, "kanji_types") for k in LV_KEYS]),
    "g4": ("gram_n4plus", [g4(k) for k in LV_KEYS]),
}
AXIS_NAME = {"mean": "平均文長", "p90": "文長P90", "kt": "異なり漢字数", "g4": "N4以上の文法の種類数"}


def to_l(v, ys):
    if v <= ys[0]: return float(XS[0])
    if v >= ys[-1]: return float(XS[-1])
    for i in range(len(ys) - 1):
        if ys[i] <= v <= ys[i + 1]:
            return XS[i] if ys[i + 1] == ys[i] else XS[i] + (v - ys[i]) / (ys[i + 1] - ys[i])


def l_to_n(L):
    if L <= PTS[0][0]: return PTS[0][1]
    if L >= PTS[-1][0]: return PTS[-1][1]
    for (a, b), (c, e) in zip(PTS, PTS[1:]):
        if a <= L <= c: return b + (e - b) * (L - a) / (c - a)


def judge(label, neq):
    """→ (判定, 帯の外にはみ出した距離)。N2/N1 は tadoku の最上段(L4)より上が測れないので「N3以下に見えるか」だけ見る"""
    n = N_OF[label]
    if label in ("N2", "N1"):
        return ("down", neq - 2.5) if neq > 2.5 else ("ok", 0.0)
    if neq < n - 0.5: return "up", (n - 0.5) - neq
    if neq > n + 0.5: return "down", neq - (n + 0.5)
    return "ok", 0.0


def analyze():
    books = metrics.all_books()
    for b in books:
        ax = {}
        for a, (key, ys) in AXES.items():
            L = to_l(b[key], ys); n = l_to_n(L)
            j, d = judge(b["level"], n)
            ax[a] = {"value": b[key], "L": round(L, 3), "neq": round(n, 3), "j": j}
        Lm = sum(to_l(b[k], ys) for k, ys in AXES.values()) / 4
        neq = l_to_n(Lm); j, dev = judge(b["level"], neq)
        b.update({"axes": ax, "L": round(Lm, 3), "neq": round(neq, 3), "j": j, "dev": round(dev, 3),
                  "v2_n": len(b["v2_warn"]), "ok_url": not b["draft"]})
    # 次に直す3冊: 帯からのはみ出しが大きい順（同率は公開済みを先）
    flagged = sorted([b for b in books if b["j"] != "ok"], key=lambda b: (-b["dev"], b["draft"]))
    next3 = [b["slug"] for b in flagged[:3]]
    # 級別要約
    levels = []
    for lv in ORDER:
        bs = [b for b in books if b["level"] == lv]
        avg = lambda k: sum(b[k] for b in bs) / len(bs)
        levels.append({
            "level": lv, "n": len(bs), "n_draft": sum(b["draft"] for b in bs),
            "chars": round(avg("chars")), "mean": round(avg("mean"), 1), "p90": round(avg("p90"), 1),
            "kanji_ratio": round(avg("kanji_ratio"), 5), "polite": round(avg("polite"), 5),
            "kanji_types": round(avg("kanji_types")), "gram_own": round(avg("gram_own"), 1),
            "neq": round(avg("neq"), 2), "v2_n": sum(b["v2_n"] for b in bs),
            "ok": sum(b["j"] == "ok" for b in bs), "up": sum(b["j"] == "up" for b in bs), "down": sum(b["j"] == "down" for b in bs),
            "outliers": [b["slug"] for b in sorted(bs, key=lambda b: -b["dev"]) if b["j"] != "ok"][:3],
            "v2": V2_TEXT[lv],
            "tadoku_levels": MAPPED[lv],
        })
    anchors = {a: dict(zip(LV_KEYS, ys)) for a, (_, ys) in AXES.items()}
    ticks = {}  # 指標パネルの目印: 自級にあたる tadoku 級の中央値
    for pn, key in (("mean", "sent_mean"), ("p90", "sent_p90"), ("kanji_ratio", "kanji_ratio"), ("polite", "polite"), ("kt", "kanji_types")):
        ticks[pn] = {lv: [{"L": k, "v": med(k, key)} for k in MAPPED[lv]] for lv in ORDER}
    ticks["g4"] = {lv: [{"L": k, "v": g4(k)} for k in MAPPED[lv]] for lv in ORDER}
    out = {
        "generated": datetime.date.today().isoformat(),
        "n_books": len(books), "n_published": sum(not b["draft"] for b in books),
        "counts": {j: sum(b["j"] == j for b in books) for j in ("ok", "up", "down")},
        "next3": next3, "levels": levels, "books": books,
        "method": {"axes": AXIS_NAME, "tadoku_medians": anchors, "tadoku_keys": LV_KEYS, "l_to_n": PTS, "ticks": ticks,
                   "tadoku_n_books": {k: T[k]["n_books"] for k in LV_KEYS}},
    }
    (OUT / "data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = analyze()
    print(o["n_books"], o["counts"], "next3:", o["next3"])
