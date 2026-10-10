#!/usr/bin/env python3
"""読み物本棚の全冊指標を計算して stdout(JSON) か data.json に落とす。読み取り専用（原稿は書き換えない）。
計算は library_check.py の v2_warn と同じ式（文の分け方・字種・です/ます判定を流用）。標準ライブラリのみ。
  python3 metrics.py            # data.json 用の素の指標 list を出力
"""
import re, sys, json, pathlib
SEO = pathlib.Path.home() / "affiliate-kit/factory/seo"
sys.path.insert(0, str(SEO))
import library_lib as L          # 原稿の読み込み（読むだけ）
import library_check as C        # RANGE / V2 / POLITE / KANJI を流用

CAT = json.load(open(SEO / "grammar_catalog.json"))
SKIP = {"だ / です", "こと", "も", "でも", "それから", "まだ", "いつも", "にする", "られる", "ていた", "ように", "意向形 （いこうけい）", "と", "そして", "もう", "とき", "得ない（えない）"}  # grammar_build.py と同じ「ありふれた語」
ORDER = ["N5", "N4", "N3", "N2", "N1"]
KANA = re.compile(r"[ぁ-んァ-ヶー一-鿿々]")


def book(path):
    d = L.load(path)
    story, _ = L.split_body(d["body"])
    sents = [s for s in (re.sub(r"[」』）\s]+$", "", x) for x in re.split(r"[。！？!?\n]", story)) if re.search(r"[ぁ-んァ-ヶ一-鿿]", s)]
    lens = sorted(len(KANA.findall(s)) for s in sents)
    chars = sum(lens)
    kanji = C.KANJI.findall(story)
    pol = sum(bool(C.POLITE.search(s)) for s in sents) / len(sents)
    hits = [g for g in CAT if g.get("re") and re.search(g["re"], story)]
    lv = d["level"]; li = ORDER.index(lv)
    by = {k: sum(1 for g in hits if g["level"] == k) for k in ORDER}
    own = [g for g in hits if g["level"] == lv and g["jp"] not in SKIP]
    return {
        "slug": pathlib.Path(path).stem, "title": d["title"], "titleEn": d.get("titleEn", ""), "level": lv,
        "genre": d.get("genre", ""), "draft": d.get("draft") == "true" or d.get("draft") is True,
        "chars": chars, "sentences": len(lens), "mean": round(sum(lens) / len(lens), 2),
        "p90": lens[min(len(lens) - 1, int(len(lens) * .9))], "kanji_ratio": round(len(kanji) / chars, 4),
        "kanji_types": len(set(kanji)), "polite": round(pol, 4),
        "gram_by_level": by,                                   # 本文に当たった文法の種類数（級別・全件）
        "gram_own": len(own),                                  # 自級の文法（ありふれた語を除く）の種類数 = 狙い文法の候補数
        "gram_above": sum(by[k] for k in ORDER[li + 1:]),          # 自級より上の級の文法の種類数
        "gram_n4plus": sum(by[k] for k in ("N4", "N3", "N2", "N1")),
        "v2_warn": C.v2_warn(lv, story),                       # library_check.py の v2 警告（照合用）
    }


def all_books():
    return [book(p) for p in sorted(L.LIB.glob("*.md"))]


if __name__ == "__main__":
    json.dump(all_books(), sys.stdout, ensure_ascii=False, indent=1)
