#!/usr/bin/env python3
"""Zero-dependency submission .docx packager and tracking ledger CLI."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from xml.sax.saxutils import escape
import zipfile


ALLOWED_STATUSES = ("待审", "拒稿", "过稿保底", "分成起量")
PASSED_STATUSES = {"过稿保底", "分成起量"}
LEDGER_FIELDS = (
    "id",
    "date",
    "title",
    "genre",
    "hook_strategy",
    "han_count",
    "channel",
    "status",
    "notes",
)

HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x2EBF0, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x3134F),
    (0x31350, 0x323AF),
)
NUMBER_PATTERN = r"(?:[0-9]{1,3}|[零〇一二三四五六七八九十百千两]{1,8})"
CHAPTER_RE = re.compile(r"第" + NUMBER_PATTERN + r"章(?P<tail>.*)")
INDEX_RE = re.compile(r"[0-9]{1,3}(?P<tail>.*)")
MARKDOWN_PREFIX_RE = re.compile(r"#{1,6}[ \t]+")
INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOCUMENT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Calibri" w:eastAsia="宋体" w:hAnsi="Calibri"/>
        <w:sz w:val="24"/>
        <w:szCs w:val="24"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr>
        <w:spacing w:after="160" w:line="360" w:lineRule="auto"/>
      </w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:after="140" w:line="360" w:lineRule="auto"/>
      <w:ind w:firstLineChars="200" w:firstLine="480"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:eastAsia="宋体" w:hAnsi="Calibri"/>
      <w:sz w:val="24"/>
      <w:szCs w:val="24"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:before="120" w:after="240" w:line="360" w:lineRule="auto"/>
      <w:ind w:firstLine="0"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:eastAsia="微软雅黑" w:hAnsi="Calibri"/>
      <w:b/>
      <w:sz w:val="36"/>
      <w:szCs w:val="36"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:before="280" w:after="160" w:line="360" w:lineRule="auto"/>
      <w:ind w:firstLine="0"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:eastAsia="微软雅黑" w:hAnsi="Calibri"/>
      <w:b/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="MetaLine">
    <w:name w:val="MetaLine"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:spacing w:after="80" w:line="320" w:lineRule="auto"/>
      <w:ind w:firstLine="0"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:eastAsia="微软雅黑" w:hAnsi="Calibri"/>
      <w:sz w:val="21"/>
      <w:szCs w:val="21"/>
      <w:color w:val="333333"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="PaywallBanner">
    <w:name w:val="PaywallBanner"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:spacing w:before="240" w:after="240" w:line="360" w:lineRule="auto"/>
      <w:ind w:firstLine="0"/>
      <w:shd w:val="clear" w:color="auto" w:fill="FFF2F0"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="Calibri" w:eastAsia="微软雅黑" w:hAnsi="Calibri"/>
      <w:b/>
      <w:sz w:val="24"/>
      <w:szCs w:val="24"/>
      <w:color w:val="C00000"/>
    </w:rPr>
  </w:style>
</w:styles>
"""


def is_han(char: str) -> bool:
    cp = ord(char)
    return cp == 0x3007 or any(lo <= cp <= hi for lo, hi in HAN_RANGES)


def count_han(text: str) -> int:
    return sum(is_han(ch) for ch in text)


def is_chapter_header(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    text = MARKDOWN_PREFIX_RE.sub("", text, count=1)
    for pattern, kind in ((CHAPTER_RE, "chapter_label"), (INDEX_RE, "numeric_label")):
        match = pattern.fullmatch(text)
        if not match:
            continue
        tail = match.group("tail")
        if not tail:
            return True
        separators = "|｜:：" if kind == "chapter_label" else "|｜"
        stripped = tail.lstrip(" \t")
        if stripped[:1] in separators and stripped:
            title = stripped[1:].strip(" \t")
        elif kind == "chapter_label" and tail[:1] in " \t":
            title = tail.strip(" \t")
        else:
            continue
        if 1 <= len(title) <= 30 and all(
            is_han(c)
            or c in " \t-—·()（）"
            or "0" <= c <= "9"
            or "a" <= c <= "z"
            or "A" <= c <= "Z"
            for c in title
        ):
            return True
    return False


def sanitize_xml_text(text: str) -> str:
    """Strip XML 1.0 illegal control characters and escape markup entities."""
    cleaned = INVALID_XML_CHARS_RE.sub("", text)
    return escape(cleaned, {'"': "&quot;", "'": "&apos;"})


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip()
    return cleaned or "未命名稿件"


def build_docx(output_path: Path, paragraphs_spec: list[tuple[str, str]]) -> None:
    """Build a valid OOXML .docx archive using only the Python standard library."""
    style_map = {
        "title": "Title",
        "heading1": "Heading1",
        "chapter": "Heading1",
        "meta": "MetaLine",
        "paywall_banner": "PaywallBanner",
        "body": "Normal",
    }
    para_xml_parts: list[str] = []
    for kind, text in paragraphs_spec:
        style_id = style_map.get(kind, "Normal")
        escaped = sanitize_xml_text(text)
        para_xml_parts.append(
            f'<w:p><w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'
        )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
        "  <w:body>\n"
        + "\n".join(para_xml_parts)
        + '\n    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800"/></w:sectPr>\n'
        "  </w:body>\n"
        "</w:document>\n"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent, prefix=".docx-", suffix=".tmp", delete=False
        ) as tmp:
            tmp_name = tmp.name
        with zipfile.ZipFile(tmp_name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
            zf.writestr("_rels/.rels", RELS_XML)
            zf.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS_XML)
            zf.writestr("word/styles.xml", STYLES_XML)
            zf.writestr("word/document.xml", document_xml)
        os.replace(tmp_name, output_path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def parse_manuscript_chapters(raw_text: str) -> tuple[list[dict], int]:
    """Split manuscript into chapter blocks and compute total body Han count."""
    chapters: list[dict] = []
    current: dict | None = None
    body_han = 0

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if is_chapter_header(stripped):
            if current is not None:
                chapters.append(current)
            current = {"header": stripped, "lines": [], "han": 0}
        else:
            han = count_han(stripped)
            body_han += han
            if current is None:
                current = {"header": "", "lines": [], "han": 0}
            current["lines"].append(stripped)
            current["han"] += han

    if current is not None:
        chapters.append(current)
    return chapters, body_han


def cmd_package(args: argparse.Namespace) -> int:
    project_dir: Path = args.project_dir
    manuscript_path = project_dir / "manuscript.txt"
    meta_path = project_dir / "submission_meta.json"
    if not manuscript_path.is_file():
        raise FileNotFoundError(f"缺少正文文件: {manuscript_path}")
    if not meta_path.is_file():
        raise FileNotFoundError(f"缺少投稿元数据文件: {meta_path}")

    raw_text = manuscript_path.read_text(encoding="utf-8-sig")
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    chapters, computed_han = parse_manuscript_chapters(raw_text)

    lint_path = project_dir / "lint_report.json"
    body_han = computed_han
    if lint_path.is_file():
        try:
            lint_data = json.loads(lint_path.read_text(encoding="utf-8-sig"))
            body_han = int(lint_data.get("body_han_count") or computed_han)
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    picked_title = str(meta.get("picked_title") or "未命名短篇").strip()
    safe_title = sanitize_filename(picked_title)
    candidates = meta.get("title_candidates") or [picked_title]
    genre = str(meta.get("genre") or "女频世情/情绪流").strip()
    audience = str(meta.get("target_audience") or "三四线城市 30-40 岁女性").strip()
    pen_name = str(meta.get("author_pen_name") or "作者").strip()
    hook_text = str(meta.get("hook_text") or "").strip()
    synopsis = str(meta.get("editor_synopsis") or "").strip()
    paywall_ch = int(meta.get("paywall_chapter") or max(1, round(len(chapters) * 0.4)))

    out_dir = project_dir / "submission"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Pure manuscript .docx
    pure_spec: list[tuple[str, str]] = [("title", f"《{picked_title}》")]
    for ch in chapters:
        if ch["header"]:
            pure_spec.append(("chapter", ch["header"]))
        for ln in ch["lines"]:
            pure_spec.append(("body", ln))
    pure_docx = out_dir / f"《{safe_title}》_纯净正文版.docx"
    build_docx(pure_docx, pure_spec)

    # 2. Editor review .docx with synopsis, hook, and paywall marker
    editor_spec: list[tuple[str, str]] = [
        ("title", f"《{picked_title}》"),
        ("meta", f"备选书名：{' / '.join(str(c) for c in candidates)}"),
        ("meta", f"题材分类：{genre}｜目标受众：{audience}｜正文实测：{body_han} 汉字｜作者：{pen_name}"),
        ("heading1", "一、信息流投流导语（给读者）"),
    ]
    for ln in hook_text.splitlines():
        if ln.strip():
            editor_spec.append(("body", ln.strip()))

    editor_spec.append(("heading1", "二、故事梗概（含结局 · 供编辑审稿）"))
    for ln in synopsis.splitlines():
        if ln.strip():
            editor_spec.append(("body", ln.strip()))

    editor_spec.append(("heading1", "三、正文"))
    cum_han = 0
    for idx, ch in enumerate(chapters, 1):
        if ch["header"]:
            editor_spec.append(("chapter", ch["header"]))
        for ln in ch["lines"]:
            editor_spec.append(("body", ln))
        cum_han += ch["han"]
        if (args.mark_paywall or paywall_ch > 0) and idx == paywall_ch:
            pct = round((cum_han / body_han) * 100, 1) if body_han > 0 else 40.0
            editor_spec.append(
                (
                    "paywall_banner",
                    f"【★ 建议付费卡点位置（第 {idx} 章末，累计约 {pct}% / {cum_han} 汉字处）：此处切付费解锁 ★】",
                )
            )

    editor_docx = out_dir / f"《{safe_title}》_编辑审稿版(标卡点).docx"
    build_docx(editor_docx, editor_spec)

    # 3. QQ email pitch template
    email_path = out_dir / "email_pitch.txt"
    email_body = (
        f"邮件主题建议：【投稿】《{picked_title}》｜{genre}｜{body_han}字｜保底/分成均可\n"
        f"{'=' * 56}\n\n"
        f"编辑老师您好：\n\n"
        f"附件为您呈上小程序短篇完稿《{picked_title}》（全篇正文 {body_han} 汉字，已完成去 AI 味、对话节奏及第 {paywall_ch} 章 40% 付费卡点校验，Word 审稿版与纯净版已随附）。\n\n"
        f"【备选书名】{' / '.join(str(c) for c in candidates)}\n"
        f"【题材受众】{genre}｜面向 {audience}\n\n"
        f"【投流导语】\n{hook_text}\n\n"
        f"【全书梗概（含结局）】\n{synopsis}\n\n"
        f"如符合贵方当前收稿方向，欢迎随时联系沟通签约（保底/分成模式均可协商）。感谢审阅！\n\n"
        f"笔名：{pen_name}\n"
        f"日期：{dt.date.today().isoformat()}\n"
    )
    email_path.write_text(email_body, encoding="utf-8")

    result = {
        "status": "ok",
        "project_dir": str(project_dir),
        "body_han_count": body_han,
        "chapter_count": len(chapters),
        "paywall_chapter": paywall_ch,
        "outputs": {
            "editor_review_docx": str(editor_docx),
            "clean_manuscript_docx": str(pure_docx),
            "email_pitch_txt": str(email_path),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def read_ledger_rows(csv_path: Path) -> list[dict]:
    if not csv_path.is_file():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [{k: row.get(k, "") for k in LEDGER_FIELDS} for row in reader]


def write_ledger_files(ledger_dir: Path, rows: list[dict]) -> tuple[Path, Path]:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    csv_path = ledger_dir / "投稿台账.csv"
    md_path = ledger_dir / "投稿台账.md"

    tmp_csv = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=ledger_dir, prefix=".csv-", delete=False
        ) as tmp:
            tmp_csv = tmp.name
            writer = csv.DictWriter(tmp, fieldnames=LEDGER_FIELDS)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in LEDGER_FIELDS})
        os.replace(tmp_csv, csv_path)
    finally:
        if tmp_csv and os.path.exists(tmp_csv):
            os.unlink(tmp_csv)

    stats = compute_stats(rows)
    lines = [
        "# 小程序短篇投稿台账",
        "",
        f"- 总投递次数：**{stats['total_submissions']}**｜过稿数：**{stats['passed_count']}**｜总过稿率：**{stats['overall_pass_rate']:.1%}**",
        "",
        "| ID | 日期 | 书名 | 题材 | 导语策略 | 字数 | 渠道/编辑 | 状态 | 备注/反馈 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in rows:
        escaped_cells = [str(r.get(k, "")).replace("|", "｜").replace("\n", " ") for k in LEDGER_FIELDS]
        lines.append("| " + " | ".join(escaped_cells) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, md_path


def compute_stats(rows: list[dict]) -> dict:
    total = len(rows)
    passed = sum(1 for r in rows if r.get("status") in PASSED_STATUSES)
    rejected = sum(1 for r in rows if r.get("status") == "拒稿")
    pending = sum(1 for r in rows if r.get("status") == "待审")

    def group_by(key: str) -> dict:
        buckets: dict[str, dict] = {}
        for r in rows:
            val = r.get(key) or "未分类"
            b = buckets.setdefault(val, {"total": 0, "passed": 0, "pass_rate": 0.0})
            b["total"] += 1
            if r.get("status") in PASSED_STATUSES:
                b["passed"] += 1
        for b in buckets.values():
            b["pass_rate"] = round(b["passed"] / b["total"], 4) if b["total"] > 0 else 0.0
        return buckets

    return {
        "total_submissions": total,
        "passed_count": passed,
        "rejected_count": rejected,
        "pending_count": pending,
        "overall_pass_rate": round(passed / total, 4) if total > 0 else 0.0,
        "by_hook_strategy": group_by("hook_strategy"),
        "by_genre": group_by("genre"),
    }


def cmd_track(args: argparse.Namespace) -> int:
    ledger_dir: Path = args.ledger_dir
    csv_path = ledger_dir / "投稿台账.csv"

    if args.track_action == "init":
        rows = read_ledger_rows(csv_path)
        c_path, m_path = write_ledger_files(ledger_dir, rows)
        print(json.dumps({"status": "ok", "csv": str(c_path), "markdown": str(m_path), "rows": len(rows)}, ensure_ascii=False, indent=2))
        return 0

    if args.track_action == "add":
        if args.status not in ALLOWED_STATUSES:
            raise ValueError(f"非法状态 {args.status}，允许值: {ALLOWED_STATUSES}")
        rows = read_ledger_rows(csv_path)
        max_id = max((int(r["id"]) for r in rows if str(r.get("id", "")).isdigit()), default=0)
        new_row = {
            "id": str(max_id + 1),
            "date": dt.date.today().isoformat(),
            "title": args.title,
            "genre": args.genre,
            "hook_strategy": args.hook_strategy,
            "han_count": str(args.han_count),
            "channel": args.channel,
            "status": args.status,
            "notes": args.notes,
        }
        rows.append(new_row)
        c_path, m_path = write_ledger_files(ledger_dir, rows)
        print(json.dumps({"status": "ok", "added": new_row, "csv": str(c_path), "markdown": str(m_path)}, ensure_ascii=False, indent=2))
        return 0

    if args.track_action == "update":
        if args.status not in ALLOWED_STATUSES:
            raise ValueError(f"非法状态 {args.status}，允许值: {ALLOWED_STATUSES}")
        rows = read_ledger_rows(csv_path)
        updated = None
        for r in rows:
            if str(r.get("id")) == str(args.id):
                r["status"] = args.status
                if args.notes is not None:
                    r["notes"] = args.notes
                updated = r
                break
        if updated is None:
            raise KeyError(f"未找到 id={args.id} 的台账记录")
        c_path, m_path = write_ledger_files(ledger_dir, rows)
        print(json.dumps({"status": "ok", "updated": updated, "csv": str(c_path), "markdown": str(m_path)}, ensure_ascii=False, indent=2))
        return 0

    if args.track_action == "stats":
        rows = read_ledger_rows(csv_path)
        print(json.dumps({"status": "ok", "csv": str(csv_path), **compute_stats(rows)}, ensure_ascii=False, indent=2))
        return 0

    raise ValueError(f"未知 track 动作: {args.track_action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="投稿套件 .docx 打包与台账追踪工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_pkg = subparsers.add_parser("package", help="导出编辑审稿版/纯净版 .docx 及邮件自荐信")
    p_pkg.add_argument("--project-dir", type=Path, required=True, help="单篇小说项目目录")
    p_pkg.add_argument("--mark-paywall", action="store_true", help="在审稿版中标出付费卡点提示行")

    p_trk = subparsers.add_parser("track", help="管理投稿台账与复盘过稿率")
    trk_sub = p_trk.add_subparsers(dest="track_action", required=True)

    p_init = trk_sub.add_parser("init", help="初始化投稿台账")
    p_init.add_argument("--ledger-dir", type=Path, default=Path.cwd(), help="台账所在目录")

    p_add = trk_sub.add_parser("add", help="新增投递记录")
    p_add.add_argument("--title", required=True, help="书名")
    p_add.add_argument("--genre", required=True, help="题材")
    p_add.add_argument("--hook-strategy", required=True, help="导语策略")
    p_add.add_argument("--han-count", type=int, required=True, help="正文汉字数")
    p_add.add_argument("--channel", required=True, help="投递渠道/编辑邮箱")
    p_add.add_argument("--status", default="待审", help="状态：待审/拒稿/过稿保底/分成起量")
    p_add.add_argument("--notes", default="", help="备注")
    p_add.add_argument("--ledger-dir", type=Path, default=Path.cwd(), help="台账所在目录")

    p_upd = trk_sub.add_parser("update", help="更新投递记录状态")
    p_upd.add_argument("--id", required=True, help="记录 ID")
    p_upd.add_argument("--status", required=True, help="状态：待审/拒稿/过稿保底/分成起量")
    p_upd.add_argument("--notes", default=None, help="反馈/拒稿原因")
    p_upd.add_argument("--ledger-dir", type=Path, default=Path.cwd(), help="台账所在目录")

    p_sts = trk_sub.add_parser("stats", help="统计投递与过稿率")
    p_sts.add_argument("--ledger-dir", type=Path, default=Path.cwd(), help="台账所在目录")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "package":
            return cmd_package(args)
        if args.command == "track":
            return cmd_track(args)
        return 2
    except (FileNotFoundError, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
