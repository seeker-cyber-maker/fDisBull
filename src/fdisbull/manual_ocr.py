"""Private, page-grounded PDF manual OCR and agent search for fDisBull.

The OCR output is source-derived *untrusted evidence*, not game behavior or
instructions to the agent. No network, LLM service, installer, or original game
execution. Requires optional PyMuPDF and a local Tesseract executable for scans.

Usage::
  python -m fdisbull.manual_ocr scan game-manual.pdf private-new-dir
  python -m fdisbull.manual_ocr search private-new-dir "save load"

Outputs preserve source and page identities and distinguish verbatim native/OCR
text from deterministic presentation reflow. They do not infer game semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FORMAT = "fdisbull-manual-ocr-1"
MAX_SOURCE = 100 * 1024 * 1024
MAX_PAGES = 500
MAX_RENDER_PIXELS = 14_000_000
STOP_WORDS = frozenset("the and with from this that for you are was were have has onto using into your a an or of to in on at be is it as by then when which".split())


class ManualOCRRefused(ValueError):
    """Input, OCR capability, layout or publication safety precondition failed."""


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise ManualOCRRefused(msg)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pages(selection: str | None, total: int) -> list[int]:
    """One-based pages, sorted and unique. Refuse out-of-bounds ranges."""
    if selection is None:
        return list(range(1, total + 1))
    out: set[int] = set()
    for token in selection.split(","):
        token = token.strip()
        require(bool(re.fullmatch(r"\d+(?:-\d+)?", token)), "invalid page range")
        pair = [int(x) for x in token.split("-")]
        lo, hi = (pair[0], pair[0]) if len(pair) == 1 else pair
        require(1 <= lo <= hi <= total, "page selection outside PDF")
        require(hi - lo < MAX_PAGES, "excessive page range")
        out.update(range(lo, hi + 1))
    require(bool(out), "empty page selection")
    return sorted(out)


def _prose(text: str) -> str:
    """Conservative line reflow, NOT an LLM correction or inferred rewrite."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = re.split(r"\n\s*\n", text.strip())
    result = []
    for para in paras:
        lines = [re.sub(r"\s+", " ", line).strip() for line in para.split("\n") if line.strip()]
        if not lines:
            continue
        buffer = lines[0]
        for line in lines[1:]:
            # Rejoin a soft, line-end hyphen only if the next word starts in
            # lower case. Keep ALL original OCR text separately for audit.
            if buffer.endswith("-") and line[:1].islower():
                buffer = buffer[:-1] + line
            else:
                buffer += " " + line
        result.append(buffer)
    return "\n\n".join(result)


def _tesseract_tsv(png: bytes, lang: str, psm: int, timeout: int) -> tuple[str, float | None, int, int, bool]:
    require(bool(re.fullmatch(r"[A-Za-z0-9_+]+", lang)), "invalid OCR language")
    require(psm in (3, 4, 6, 11), "unsupported page segmentation mode")
    require(1 <= timeout <= 120, "invalid per-page timeout")
    require(shutil.which("tesseract") is not None, "Tesseract executable unavailable (scan is not text-backed)")
    try:
        finished = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm), "tsv"],
            input=png, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ManualOCRRefused("OCR timed out; page not accepted") from exc
    require(finished.returncode == 0,
            "OCR failed: " + finished.stderr.decode("utf-8", "replace")[:260])
    try:
        tsv = finished.stdout.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise ManualOCRRefused("invalid OCR UTF-8") from exc
    lines = tsv.splitlines()
    require(bool(lines), "OCR returned no TSV header")
    columns = lines[0].split("\t")
    require(columns == ["level", "page_num", "block_num", "par_num", "line_num",
                        "word_num", "left", "top", "width", "height", "conf", "text"],
            "unexpected OCR word-record schema")
    rows=[]
    for line in lines[1:]:
        if not line.strip():
            continue
        fields=line.split("\t", 11)
        require(len(fields)==12, "malformed OCR TSV row")
        # The OCR text field may *begin* with a literal double quote. csv.DictReader
        # interprets that as CSV quoting and swallows subsequent TSV rows into
        # the word text. Tesseract TSV is unquoted: split columns literally.
        rows.append(dict(zip(columns,fields)))
    line_groups: dict[tuple[str,str,str,str], list[str]] = {}
    confidence = []
    low = 0
    blocks: dict[str, list[tuple[int,int,int,int]]] = {}
    page_width = int(rows[0].get("width", "0")) if rows else 0
    for row in rows:
        token = (row.get("text") or "").strip()
        if not token:
            continue
        key = tuple(row.get(n,"0") for n in ("page_num", "block_num", "par_num", "line_num"))
        line_groups.setdefault(key, []).append(token)
        try:
            box = tuple(int(row.get(k,"0")) for k in ("left","top","width","height"))
            blocks.setdefault(key[1],[]).append(box)
        except ValueError:
            pass
        try:
            c = float(row.get("conf", "-1"))
        except ValueError:
            c = -1
        if c >= 0:
            confidence.append(c)
            low += c < 60
    # TSV row sequence and block+paragraph breaks preserve Tesseract's reading order.
    parts = []
    prev = None
    for (p, block, par, line), words in line_groups.items():
        if prev is not None:
            parts.append("\n\n" if (p, block, par) != prev[:3] else "\n")
        parts.append(" ".join(words))
        prev = (p, block, par, line)
    text = "".join(parts)
    avg = round(sum(confidence)/len(confidence), 2) if confidence else None
    # The OCR engine can assign 90%+ confidence to individual words while
    # interleaving two columns. Detect clearly overlapping text columns and
    # require visual review, instead of equating word confidence with prose order.
    extents=[]
    for boxlist in blocks.values():
        if len(boxlist) < 15:
            continue
        x0=min(b[0] for b in boxlist);y0=min(b[1] for b in boxlist)
        x1=max(b[0]+b[2] for b in boxlist);y1=max(b[1]+b[3] for b in boxlist)
        extents.append((x0,y0,x1,y1))
    parallel_columns=False
    for i,(ax0,ay0,ax1,ay1) in enumerate(extents):
        if parallel_columns: break
        if page_width and ax1-ax0 > 0.55*page_width: continue
        for bx0,by0,bx1,by1 in extents[i+1:]:
            if page_width and bx1-bx0 > 0.55*page_width: continue
            overlap=min(ay1,by1)-max(ay0,by0)
            if overlap > 60 and (ax1 + 8 < bx0 or bx1 + 8 < ax0):
                parallel_columns=True
                break
    return text, avg, len(confidence), low, parallel_columns


def page_record(page: Any, number: int, *, lang: str="eng", dpi: int=300,
                psm: int=3, timeout: int=30, min_native_chars: int=45) -> dict[str, Any]:
    source = page.get_text("text", sort=True)
    if len(source.strip()) >= min_native_chars:
        method = "native-text"
        raw, conf, words, low = source, None, len(re.findall(r"\b\w+\b", source)), 0
        raster_sha = None
        columns = False
    else:
        require(144 <= dpi <= 450, "DPI outside 144..450")
        zoom = dpi/72.0
        width, height = page.rect.width*zoom, page.rect.height*zoom
        require(width*height <= MAX_RENDER_PIXELS, "rendering exceeds bounded pixel count")
        import fitz
        img = page.get_pixmap(matrix=fitz.Matrix(zoom,zoom), alpha=False)
        png = img.tobytes("png")
        raster_sha = hashlib.sha256(png).hexdigest()
        raw, conf, words, low, columns = _tesseract_tsv(png, lang, psm, timeout)
        method = "tesseract-ocr"
    prose = _prose(raw)
    # A high lexical confidence cannot certify layout order, spelling or meaning.
    review = (words < 15 or columns or (conf is not None and conf < 76))
    return {"pdf_page": number, "method": method, "raw_text": raw,
            "readable_text": prose, "word_count": words,
            "mean_word_confidence": conf, "low_confidence_words": low,
            "review_recommended": review,
            "possible_parallel_columns": columns, "raster_sha256": raster_sha}


def _private_destination(out: Path) -> None:
    require(not out.exists() and not out.is_symlink(), "output directory already exists")
    require(out.parent.is_dir(), "output parent does not exist")
    # PDFs and their OCR text can be licensed originals. Do not save under Git.
    for ancestor in [out.parent, *out.parent.parents]:
        require(not (ancestor / ".git").exists(), "OCR output must stay outside Git repositories")


def scan(path: str | Path, output: str | Path, *, pages: str | None = None,
         lang: str = "eng", dpi: int = 300, psm: int = 3, timeout: int = 30) -> dict[str,Any]:
    original = Path(path).expanduser()
    require(not original.is_symlink(), "source must not be a symlink")
    src = original.resolve(strict=True)
    out = Path(output).expanduser().absolute()
    require(src.is_file() and not src.is_symlink(), "input must be a regular PDF")
    require(0 < src.stat().st_size <= MAX_SOURCE, "input size outside safety bound")
    _private_destination(out)
    try:
        import fitz  # optional PDF rendering dependency
    except ImportError as exc:
        raise ManualOCRRefused("PyMuPDF is required for PDF page reading; install an approved local PDF backend") from exc
    try:
        pdf = fitz.open(src)
    except Exception as exc:
        raise ManualOCRRefused("PDF could not be opened") from exc
    with pdf:
        require(pdf.is_pdf and not pdf.needs_pass, "input must be a readable unencrypted PDF")
        require(1 <= len(pdf) <= MAX_PAGES, "PDF page count outside safety bound")
        total_pages = len(pdf)
        selected = parse_pages(pages, total_pages)
        before_stat = (src.stat().st_size, src.stat().st_mtime_ns, src.stat().st_ino)
        source_sha = sha256_file(src)
        started = time.monotonic()
        records = []
        for n in selected:
            record = page_record(pdf[n-1], n, lang=lang, dpi=dpi, psm=psm, timeout=timeout)
            records.append(record)
            print(f"[manual-ocr] page {n}/{total_pages}: {record['word_count']} words, method={record['method']}", file=sys.stderr, flush=True)
        after_stat = (src.stat().st_size, src.stat().st_mtime_ns, src.stat().st_ino)
        require(before_stat == after_stat and sha256_file(src) == source_sha,
                "PDF changed during OCR")
    engine_version = None
    if any(r['method'] == "tesseract-ocr" for r in records):
        engine_version = subprocess.run(["tesseract","--version"],capture_output=True,text=True,timeout=5).stdout.splitlines()[0]
    receipt = {
        "format": FORMAT, "source_basename": src.name, "source_sha256": source_sha,
        "pdf_pages": total_pages, "selected_pdf_pages": selected,
        "language":lang, "dpi":dpi, "psm":psm,
        "ocr_engine":engine_version,"elapsed_seconds":round(time.monotonic()-started, 3),
        "manual_edition_verified":False,"original_behavior_verified":False,
        "warnings":["OCR is imperfect source-derived evidence; verify disputed control names against the page image."],
        "pages": records
    }
    blocks = [
        "# " + src.stem + " (OCR transcription, not an authoritative game mechanics model)",
        "Source SHA-256: `"+source_sha+"`",
        "Each heading uses the **one-based PDF page number**. Printed book page numbers may differ.",
        "Text order, columns, tables and typography can be damaged by OCR. Consult the original scan for important assertions."
    ]
    for r in records:
        state = ("OCR confidence " + str(r['mean_word_confidence']) if r['mean_word_confidence'] is not None
                 else "native PDF text layer")
        if r['review_recommended']:
            state += "; review against page image"
        blocks.append(f"## PDF page {r['pdf_page']}\n\n*{state}*\n\n"+(r['readable_text'] or "[No readable text detected; inspect scan]"))
    # Create only after verification to avoid publishing misleading partial output.
    out.mkdir(mode=0o700)
    try:
        (out / "PRIVATE_CONTENT_DO_NOT_COMMIT.txt").write_text(
            "Private user-provided manual transcription. Do not publish full text, images or output receipts in repository.\n")
        (out / "manual.md").write_text("\n\n".join(blocks)+"\n",encoding="utf-8")
        (out / "pages.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        summary = {k:v for k,v in receipt.items() if k!="pages"}
        summary["page_summary"] = [{k:r[k] for k in ("pdf_page","method","word_count","mean_word_confidence","review_recommended","possible_parallel_columns")}
                                   for r in records]
        (out / "receipt.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(out)
        raise
    return {"source_sha256":source_sha,"output":str(out),"pages":len(records),
            "scanned":sum(r['method']=="tesseract-ocr" for r in records),
            "review_pages":[r['pdf_page'] for r in records if r['review_recommended']],
            "elapsed_seconds":receipt['elapsed_seconds']}



def merge_parts(inputs: list[str | Path], destination: str | Path) -> dict[str, Any]:
    """Join matching private page shards with no holes or repeated page numbers."""
    require(len(inputs) >= 2, "at least two private page shards required")
    out = Path(destination).expanduser().absolute()
    _private_destination(out)
    loaded=[]
    for src in inputs:
        folder=Path(src)
        require(folder.is_dir() and not folder.is_symlink(), "page shard is not a directory")
        receipt=json.loads((folder/"pages.json").read_text(encoding="utf-8"))
        require(receipt.get("format")==FORMAT and isinstance(receipt.get("pages"),list),"invalid shard receipt")
        loaded.append(receipt)
    expected_keys=("source_sha256","pdf_pages","language","dpi","psm","ocr_engine")
    base=loaded[0]
    for receipt in loaded[1:]:
        require(all(base[k]==receipt[k] for k in expected_keys),"mixed source, OCR engine or profile")
    pages={}
    for receipt in loaded:
        for page in receipt["pages"]:
            n=page["pdf_page"]
            require(n not in pages and 1<=n<=base["pdf_pages"],"duplicate/out-of-range page")
            pages[n]=page
    require(set(pages)==set(range(1,base["pdf_pages"]+1)),"page shards do not cover entire manual")
    joined=sorted(pages.values(),key=lambda x:x["pdf_page"])
    result={**base,
            "selected_pdf_pages":list(range(1,base["pdf_pages"]+1)),
            "pages":joined,"elapsed_seconds":round(sum(r["elapsed_seconds"] for r in loaded),3),
            "merged_part_count":len(loaded)}
    blocks=["# " + base["source_basename"] + " (OCR transcription, not a game mechanics model)",
            "Source SHA-256: `"+base["source_sha256"]+"`",
            "Each heading uses the one-based PDF page number. The original scan remains authoritative."]
    for page in joined:
        conf=("OCR confidence " + str(page["mean_word_confidence"]) if page["mean_word_confidence"] is not None
              else "native PDF text layer")
        if page["review_recommended"]: conf += "; verify against original page image"
        blocks.append(f"## PDF page {page['pdf_page']}\n\n*{conf}*\n\n" +
                      (page["readable_text"] or "[No readable text detected; inspect the scan]"))
    out.mkdir(mode=0o700)
    try:
        (out/"PRIVATE_CONTENT_DO_NOT_COMMIT.txt").write_text("Private OCR of user-provided manual. Keep outside Git.\n")
        (out/"manual.md").write_text("\n\n".join(blocks)+"\n",encoding="utf-8")
        (out/"pages.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        summary={k:v for k,v in result.items() if k!="pages"}
        summary["page_summary"]=[{k:p[k] for k in ("pdf_page","method","word_count","mean_word_confidence","review_recommended","possible_parallel_columns")} for p in joined]
        (out/"receipt.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(out)
        raise
    return {"source_sha256":base["source_sha256"],"pdf_pages":len(joined),
            "merged_part_count":len(loaded),"review_pages":[p["pdf_page"] for p in joined if p["review_recommended"]],
            "output":str(out)}


def search(output: str | Path, query: str, *, max_hits: int = 12) -> list[dict[str,Any]]:
    require(1<=max_hits<=100,"invalid hit limit")
    receipt_path=Path(output)/"pages.json"
    require(receipt_path.is_file(),"receipt unavailable")
    r=json.loads(receipt_path.read_text(encoding="utf-8"))
    require(r.get("format")==FORMAT,"unsupported receipt format")
    tokens=[t.casefold() for t in re.findall(r"[A-Za-z0-9]+",query) if t.casefold() not in STOP_WORDS]
    require(bool(tokens) and len(tokens)<=10,"provide 1..10 significant query terms")
    matches=[]
    for p in r["pages"]:
        text=p["readable_text"]
        indexed=re.sub(r"\s+"," ",text)
        lower=indexed.casefold()
        terms=[t for t in tokens if re.search(r"(?<!\w)"+re.escape(t)+r"(?!\w)", lower)]
        if not terms:
            continue
        at=min([lower.find(t) for t in terms if lower.find(t)>=0])
        clip=indexed[max(0,at-80):min(len(indexed),at+220)]
        matches.append({"pdf_page":p["pdf_page"],"score":len(terms),"matched_terms":terms,
                        "snippet":clip,"review_recommended":p["review_recommended"]})
    return sorted(matches,key=lambda x:(-x['score'],x['pdf_page']))[:max_hits]


def main(argv: list[str]|None=None) -> int:
    ap=argparse.ArgumentParser(description="Local, private PDF manual OCR and cited search")
    sub=ap.add_subparsers(dest="action",required=True)
    run=sub.add_parser("scan",help="transcribe original PDF pages to private Markdown and JSON")
    run.add_argument("pdf")
    run.add_argument("output",help="new directory OUTSIDE any Git checkout")
    run.add_argument("--pages",help="one-based pages e.g. 1-3,37")
    run.add_argument("--lang",default="eng")
    run.add_argument("--dpi",type=int,default=300)
    run.add_argument("--psm",type=int,default=3,choices=(3,4,6,11))
    run.add_argument("--timeout",type=int,default=30)
    combine=sub.add_parser("merge",help="assemble exact-source private page shards")
    combine.add_argument("output",help="new private directory")
    combine.add_argument("shards",nargs="+",help="two or more full-page private result directories")
    query=sub.add_parser("search",help="search a retained OCR receipt, returning page citations")
    query.add_argument("output")
    query.add_argument("query")
    query.add_argument("--max-hits",type=int,default=12)
    args=ap.parse_args(argv)
    try:
        if args.action=="scan":
            result=scan(args.pdf,args.output,pages=args.pages,lang=args.lang,dpi=args.dpi,psm=args.psm,timeout=args.timeout)
        elif args.action=="merge":
            result=merge_parts(args.shards,args.output)
        else:
            result=search(args.output,args.query,max_hits=args.max_hits)
    except (ManualOCRRefused,FileNotFoundError) as exc:
        print(json.dumps({"ok":False,"error":str(exc)}),file=sys.stderr)
        return 2
    print(json.dumps({"ok":True,"result":result},ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
