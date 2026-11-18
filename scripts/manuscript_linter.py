#!/usr/bin/env python3
"""Deterministic multi-dimensional linter for short web-novel manuscripts.

Standard library only. Checks Han count, chapter alignment, dialogue ratio,
paragraph pacing, tiered banned expressions, 40% paywall placement, and
story_bible.json payoff ledger resolution.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile


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

DIALOGUE_SPAN_RE = re.compile(r'“[^”\n]*”|「[^」\n]*」|『[^』\n]*』|"[^"\n]*"')
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?]+")

TIER1_WORDS = (
    "五味杂陈",
    "面面相觑",
    "不可置信",
    "不容置疑",
    "戛然而止",
    "瞳孔地震",
    "死寂",
    "空气凝固",
    "重锤",
    "炸雷",
    "轧机",
    "离岸信托",
    "对赌协议",
    "共患神经",
)

TIER1_PATTERNS = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("嘴角+动词", r"嘴角[^，。！？\n]{0,4}(?:勾|扬|撇|抽|沉|掀)"),
        ("眼神+一丝/一抹", r"(?:眼中|眸中|眼底|目光)[^，。！？\n]{0,4}(?:闪过|掠过|透着|满是)(?:一丝|一抹|三分)"),
        ("心中/心里感受", r"(?:心中|心里)(?:泛起|涌起|升起|一紧|一沉|一痛|一阵)"),
        ("暴力比喻", r"(?:像|如同|仿佛)[^，。！？\n]{0,6}(?:重锤|炸雷|利刃|冰窖|晴天霹雳)"),
        ("空气/时间拟人", r"(?:空气|时间|气氛)[^，。！？\n]{0,4}(?:凝固|凝滞|静止|窒息)"),
        ("深吸一口气+缓缓", r"深吸一?口气[^，。！？\n]{0,6}(?:缓缓|慢慢|幽幽)"),
        ("带着一丝/一抹/一股", r"带着一(?:丝|抹|股)[^，。！？\n]{1,5}"),
        ("说教对比总结", r"这不是[^，。！？\n]{1,18}而是"),
    )
)

TIER2_DENSITY_WORDS = (
    "顿时",
    "立刻",
    "连忙",
    "瞬间",
    "渐渐",
    "不断",
    "再次",
    "十分",
    "果然",
    "猛地",
    "显然",
    "似乎",
    "仿佛",
)


class InputError(Exception):
    """Raised when input files or CLI arguments are invalid."""


class StrictParser(argparse.ArgumentParser):
    """ArgumentParser that raises InputError instead of calling sys.exit."""

    def error(self, message: str) -> None:
        raise InputError(message)


def is_han(char: str) -> bool:
    """Return True if char falls in the fixed CJK Han Unicode blocks."""
    cp = ord(char)
    return cp == 0x3007 or any(lo <= cp <= hi for lo, hi in HAN_RANGES)


def count_han(text: str) -> int:
    """Count Han characters in text."""
    return sum(is_han(ch) for ch in text)


def chapter_reason(line: str) -> str | None:
    """Return chapter label classification if line is a standalone chapter header."""
    text = line.strip()
    if not text:
        return None
    text = MARKDOWN_PREFIX_RE.sub("", text, count=1)
    for pattern, kind in ((CHAPTER_RE, "chapter_label"), (INDEX_RE, "numeric_label")):
        match = pattern.fullmatch(text)
        if not match:
            continue
        tail = match.group("tail")
        if not tail:
            return kind
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
            return kind + "_with_title"
    return None


def parse_chapters(lines: list[str]) -> tuple[list[dict], list[dict]]:
    """Split manuscript lines into structured chapters and excluded header records."""
    excluded: list[dict] = []
    chapters: list[dict] = []
    preamble_lines: list[tuple[int, str]] = []
    current_chapter: dict | None = None

    for line_no, raw_line in enumerate(lines, 1):
        reason = chapter_reason(raw_line)
        if reason:
            stripped = raw_line.rstrip("\r\n")
            excluded.append({"line_number": line_no, "text": stripped, "reason": reason})
            if current_chapter is not None:
                chapters.append(current_chapter)
            current_chapter = {
                "index": len(chapters) + 1,
                "label": stripped.strip(),
                "line_number": line_no,
                "body_lines": [],
            }
        else:
            if current_chapter is not None:
                current_chapter["body_lines"].append((line_no, raw_line))
            else:
                preamble_lines.append((line_no, raw_line))

    if current_chapter is not None:
        chapters.append(current_chapter)

    # Fallback if manuscript contains no chapter headers at all.
    if not chapters and preamble_lines:
        chapters.append(
            {
                "index": 1,
                "label": "(unlabeled)",
                "line_number": 1,
                "body_lines": preamble_lines,
                "unlabeled": True,
            }
        )
    elif preamble_lines and any(count_han(ln) > 0 for _, ln in preamble_lines):
        # Attach non-empty preamble into chapter 1 metrics while flagging it.
        chapters[0]["has_preamble"] = True
        chapters[0]["body_lines"] = preamble_lines + chapters[0]["body_lines"]

    for ch in chapters:
        ch_text = "".join(ln for _, ln in ch["body_lines"])
        ch["han_count"] = count_han(ch_text)

    return chapters, excluded


def calc_dialogue_metrics(body_lines: list[tuple[int, str]]) -> dict:
    """Compute dialogue Han character count and ratio across body lines."""
    total_body_han = 0
    dialogue_han = 0

    for _, line in body_lines:
        line_han = count_han(line)
        total_body_han += line_han
        if line_han == 0:
            continue

        spans: list[tuple[int, int]] = []
        for match in DIALOGUE_SPAN_RE.finditer(line):
            spans.append((match.start(), match.end()))

        if not spans:
            continue

        # Merge overlapping spans defensively to avoid double counting.
        spans.sort()
        merged: list[tuple[int, int]] = [spans[0]]
        for start, end in spans[1:]:
            prev_s, prev_e = merged[-1]
            if start <= prev_e:
                merged[-1] = (prev_s, max(prev_e, end))
            else:
                merged.append((start, end))

        for start, end in merged:
            dialogue_han += count_han(line[start:end])

    ratio = round(dialogue_han / total_body_han, 4) if total_body_han > 0 else 0.0
    return {
        "dialogue_han_count": dialogue_han,
        "body_han_count": total_body_han,
        "dialogue_ratio": ratio,
    }


def check_paragraph_pacing(body_lines: list[tuple[int, str]]) -> dict:
    """Check paragraph Han length and sentence count to prevent dense text walls."""
    total_paragraphs = 0
    violations: list[dict] = []

    for line_no, raw_line in body_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        total_paragraphs += 1
        han_cnt = count_han(stripped)
        is_dialogue = stripped[0] in '“「『"'
        sentences = [seg for seg in SENTENCE_SPLIT_RE.split(stripped) if count_han(seg) > 0]
        sentence_cnt = max(len(sentences), 1 if han_cnt > 0 else 0)
        max_sentences = 4 if is_dialogue else 3

        if han_cnt > 90 or sentence_cnt > max_sentences:
            violations.append(
                {
                    "line_number": line_no,
                    "han_count": han_cnt,
                    "sentence_count": sentence_cnt,
                    "is_dialogue": is_dialogue,
                    "preview": stripped[:45] + ("..." if len(stripped) > 45 else ""),
                }
            )

    ratio = round(len(violations) / total_paragraphs, 4) if total_paragraphs > 0 else 0.0
    return {
        "total_paragraphs": total_paragraphs,
        "violation_count": len(violations),
        "long_paragraph_ratio": ratio,
        "max_allowed_ratio": 0.05,
        "passed": total_paragraphs > 0 and ratio <= 0.05,
        "samples": violations[:10],
    }


def scan_banned_expressions(body_lines: list[tuple[int, str]], total_body_han: int) -> dict:
    """Scan body lines for Tier-1 hard-banned items and Tier-2 density words."""
    tier1_hits: list[dict] = []
    tier2_counts: dict[str, int] = {}

    for line_no, raw_line in body_lines:
        text = raw_line.rstrip("\r\n")
        if not text.strip():
            continue

        for word in TIER1_WORDS:
            if word in text:
                tier1_hits.append(
                    {"line_number": line_no, "rule": f"词:{word}", "preview": text.strip()[:45]}
                )

        for rule_name, regex in TIER1_PATTERNS:
            for match in regex.finditer(text):
                tier1_hits.append(
                    {
                        "line_number": line_no,
                        "rule": f"句式:{rule_name}({match.group(0)})",
                        "preview": text.strip()[:45],
                    }
                )

        for word in TIER2_DENSITY_WORDS:
            cnt = text.count(word)
            if cnt > 0:
                tier2_counts[word] = tier2_counts.get(word, 0) + cnt

    tier2_total = sum(tier2_counts.values())
    per_1k = round((tier2_total / total_body_han) * 1000, 3) if total_body_han > 0 else 0.0
    return {
        "tier1_hit_count": len(tier1_hits),
        "tier1_hits": tier1_hits[:20],
        "tier2_total_count": tier2_total,
        "tier2_per_1k_han": per_1k,
        "tier2_max_per_1k_han": 1.5,
        "tier2_breakdown": tier2_counts,
        "passed": len(tier1_hits) == 0 and per_1k <= 1.5,
    }


def evaluate_paywall(
    chapters: list[dict],
    total_body_han: int,
    paywall_chapter: int | None,
    mode: str,
) -> dict:
    """Evaluate chapter balance, cumulative 40% paywall ratio, and cliffhanger preview."""
    chapter_stats = []
    cum_han = 0
    thin_chapters = []

    for ch in chapters:
        han = ch["han_count"]
        cum_han += han
        cum_ratio = round(cum_han / total_body_han, 4) if total_body_han > 0 else 0.0
        if han < 600:
            thin_chapters.append({"index": ch["index"], "label": ch["label"], "han_count": han})
        chapter_stats.append(
            {
                "index": ch["index"],
                "label": ch["label"],
                "han_count": han,
                "cumulative_han": cum_han,
                "cumulative_ratio": cum_ratio,
            }
        )

    recommended = None
    if chapter_stats:
        recommended = min(chapter_stats, key=lambda c: abs(c["cumulative_ratio"] - 0.40))

    target_idx = paywall_chapter if paywall_chapter is not None else (
        len(chapters) if mode == "sample" else (recommended["index"] if recommended else None)
    )

    cliffhanger_preview: list[str] = []
    target_ratio = None
    paywall_in_range = False

    if target_idx is not None and 1 <= target_idx <= len(chapters):
        target_ch = chapters[target_idx - 1]
        non_empty = [ln.strip() for _, ln in target_ch["body_lines"] if ln.strip()]
        cliffhanger_preview = non_empty[-3:]
        target_ratio = chapter_stats[target_idx - 1]["cumulative_ratio"]
        if mode == "sample":
            paywall_in_range = (paywall_chapter is None) or (len(chapters) == paywall_chapter)
        else:
            paywall_in_range = 0.30 <= target_ratio <= 0.50
    elif mode == "sample" and chapters:
        non_empty = [ln.strip() for _, ln in chapters[-1]["body_lines"] if ln.strip()]
        cliffhanger_preview = non_empty[-3:]

    passed = paywall_in_range and len(thin_chapters) == 0 and len(chapters) > 0
    return {
        "chapter_count": len(chapters),
        "chapters": chapter_stats,
        "thin_chapters_under_600": thin_chapters,
        "recommended_paywall_chapter": recommended["index"] if recommended else None,
        "paywall_chapter": paywall_chapter,
        "paywall_cumulative_ratio": target_ratio,
        "paywall_window": [0.30, 0.50] if mode == "full" else None,
        "cliffhanger_preview": cliffhanger_preview,
        "passed": passed,
    }


def check_bible_ledger(bible_path: Path | None, mode: str) -> dict:
    """Validate story_bible.json and ensure debts/props are resolved in full mode."""
    if bible_path is None:
        return {"checked": False, "passed": True, "unresolved_debts": [], "unresolved_props": []}
    if not bible_path.is_file():
        raise InputError(f"story_bible文件不存在: {bible_path}")
    try:
        data = json.loads(bible_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"story_bible解析失败: {exc}") from exc

    if not isinstance(data, dict):
        raise InputError("story_bible根节点必须是JSON对象")

    debts = data.get("debts") or []
    props = data.get("props") or []
    unresolved_debts = [
        {"id": d.get("id"), "payoff_chapter": d.get("payoff_chapter"), "status": d.get("status")}
        for d in debts
        if isinstance(d, dict) and d.get("status") != "resolved"
    ]
    unresolved_props = [
        {"id": p.get("id"), "name": p.get("name"), "status": p.get("status")}
        for p in props
        if isinstance(p, dict) and p.get("status") != "resolved"
    ]

    passed = True if mode == "sample" else (not unresolved_debts and not unresolved_props)
    return {
        "checked": True,
        "bible_path": str(bible_path),
        "total_debts": len(debts),
        "total_props": len(props),
        "unresolved_debts": unresolved_debts,
        "unresolved_props": unresolved_props,
        "passed": passed,
    }


def same_file(first: Path, second: Path) -> bool:
    """Return True if two paths refer to the same file."""
    if first.resolve() == second.resolve():
        return True
    return first.exists() and second.exists() and os.path.samefile(first, second)


def save_report(path: Path, report: dict, source: Path) -> None:
    """Atomically write JSON report while refusing to overwrite source or symlinks."""
    if same_file(source, path):
        raise InputError("--output不得与正文指向同一文件")
    if path.is_symlink():
        raise InputError("--output不得是符号链接")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".lint-report-",
            delete=False,
        ) as tmp:
            temp_name = tmp.name
            json.dump(report, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def build_hints(gates: dict, dialogue: dict, pacing: dict, banned: dict, paywall: dict, ledger: dict, han_range: tuple[int, int], body_han: int) -> list[str]:
    """Build actionable remediation hints in Simplified Chinese for failed gates."""
    hints: list[str] = []
    if not gates["han_count"]["passed"]:
        hints.append(f"正文汉字数为 {body_han}，不在要求区间 {han_range[0]}–{han_range[1]} 内，请按细纲扩写冲突层级或精简废话。")
    if not gates["chapter_count"]["passed"]:
        hints.append(gates["chapter_count"]["detail"])
    if not gates["dialogue_ratio"]["passed"]:
        hints.append(
            f"对话占比为 {dialogue['dialogue_ratio']:.1%}，请调整至指定范围，把内心叙述和背景交代改为人物交锋台词。"
        )
    if not gates["paragraph_pacing"]["passed"]:
        hints.append(
            f"检测到 {pacing['violation_count']} 段文字墙（单段>90字或句数过多），请拆成动作/对白独立短行。"
        )
    if not gates["banned_expressions"]["passed"]:
        if banned["tier1_hit_count"] > 0:
            hints.append(f"命中 {banned['tier1_hit_count']} 处 Tier-1 硬禁词/套话或悬浮词，必须全部改写为具体动作与生活化词汇。")
        if banned["tier2_per_1k_han"] > banned["tier2_max_per_1k_han"]:
            hints.append(f"Tier-2 高频 AI 副词密度达 {banned['tier2_per_1k_han']}/千字（上限 1.5），请删减“顿时/立刻/连忙/瞬间”等词。")
    if not gates["paywall_placement"]["passed"]:
        if paywall["thin_chapters_under_600"]:
            hints.append("存在不足 600 汉字的缩水章节，请补足场次与冲突回合。")
        else:
            hints.append("40% 付费卡点章节位置偏离目标窗口 [30%, 50%]，请检查卡点章号或章节篇幅分布。")
    if not gates["bible_ledger"]["passed"]:
        hints.append(
            f"story_bible.json 仍有未核销项（debts: {len(ledger['unresolved_debts'])}, props: {len(ledger['unresolved_props'])}），请核对打脸剧情并更新状态为 resolved。"
        )
    return hints


def main(argv: list[str] | None = None) -> int:
    parser = StrictParser(
        description="小程序短篇稿件全维度静态质检器（标准库零依赖）"
    )
    parser.add_argument("manuscript", type=Path, help="UTF-8 .txt 正文路径")
    parser.add_argument("--mode", choices=["sample", "full"], default="full", help="质检模式：sample(前4000字小样) 或 full(完稿)")
    parser.add_argument("--min-han", type=int, default=None, help="最少正文汉字数")
    parser.add_argument("--max-han", type=int, default=None, help="最多正文汉字数")
    parser.add_argument("--min-dialogue", type=float, default=0.55, help="最低对话占比（默认 0.55）")
    parser.add_argument("--max-dialogue", type=float, default=0.75, help="最高对话占比（默认 0.75）")
    parser.add_argument("--expected-chapters", type=int, default=None, help="预期章节数")
    parser.add_argument("--paywall-chapter", type=int, default=None, help="付费卡点章号")
    parser.add_argument("--bible", type=Path, default=None, help="story_bible.json 路径")
    parser.add_argument("--output", type=Path, default=None, help="JSON 报告输出路径")

    args = None
    report: dict = {"status": "input_error"}
    exit_code = 2

    try:
        args = parser.parse_args(argv)
        min_han = args.min_han if args.min_han is not None else (3200 if args.mode == "sample" else 11500)
        max_han = args.max_han if args.max_han is not None else (5500 if args.mode == "sample" else 16000)

        if min_han < 0 or max_han < min_han:
            raise InputError("须满足 0 <= --min-han <= --max-han")
        if not (0.0 <= args.min_dialogue <= args.max_dialogue <= 1.0):
            raise InputError("须满足 0.0 <= --min-dialogue <= --max-dialogue <= 1.0")
        if args.expected_chapters is not None and args.expected_chapters <= 0:
            raise InputError("--expected-chapters 必须大于 0")
        if args.paywall_chapter is not None and args.paywall_chapter <= 0:
            raise InputError("--paywall-chapter 必须大于 0")
        if args.output and same_file(args.manuscript, args.output):
            raise InputError("--output不得与正文指向同一文件")
        if args.manuscript.suffix.lower() != ".txt":
            raise InputError("正文必须为 .txt 文件")
        if not args.manuscript.is_file():
            raise InputError("正文文件不存在或不是普通文件")

        raw = args.manuscript.read_text(encoding="utf-8-sig")
        raw_lines = raw.splitlines(keepends=True)
        chapters, excluded = parse_chapters(raw_lines)
        body_lines = [item for ch in chapters for item in ch["body_lines"]]

        dialogue = calc_dialogue_metrics(body_lines)
        body_han = dialogue["body_han_count"]
        pacing = check_paragraph_pacing(body_lines)
        banned = scan_banned_expressions(body_lines, body_han)
        paywall = evaluate_paywall(chapters, body_han, args.paywall_chapter, args.mode)
        ledger = check_bible_ledger(args.bible, args.mode)

        unlabeled_only = len(chapters) == 1 and bool(chapters[0].get("unlabeled"))
        actual_chapter_count = 0 if unlabeled_only else len(chapters)
        if args.expected_chapters is not None:
            ch_ok = actual_chapter_count == args.expected_chapters
            ch_detail = f"实测章节数 {actual_chapter_count}，预期 {args.expected_chapters}"
        else:
            ch_ok = actual_chapter_count >= 1
            ch_detail = f"实测章节数 {actual_chapter_count}"

        gates = {
            "han_count": {
                "passed": min_han <= body_han <= max_han,
                "detail": f"正文汉字 {body_han}，范围 [{min_han}, {max_han}]",
            },
            "chapter_count": {"passed": ch_ok, "detail": ch_detail},
            "dialogue_ratio": {
                "passed": args.min_dialogue <= dialogue["dialogue_ratio"] <= args.max_dialogue,
                "detail": f"对话占比 {dialogue['dialogue_ratio']:.1%}，范围 [{args.min_dialogue:.0%}, {args.max_dialogue:.0%}]",
            },
            "paragraph_pacing": {
                "passed": pacing["passed"],
                "detail": f"违规文字墙段落 {pacing['violation_count']}/{pacing['total_paragraphs']} ({pacing['long_paragraph_ratio']:.1%})",
            },
            "banned_expressions": {
                "passed": banned["passed"],
                "detail": f"Tier-1 命中 {banned['tier1_hit_count']} 次，Tier-2 密度 {banned['tier2_per_1k_han']}/千字",
            },
            "paywall_placement": {
                "passed": paywall["passed"],
                "detail": f"卡点章 {paywall['paywall_chapter']} 累计占比 {paywall['paywall_cumulative_ratio']}",
            },
            "bible_ledger": {
                "passed": ledger["passed"],
                "detail": f"未核销债务 {len(ledger['unresolved_debts'])}，未核销道具 {len(ledger['unresolved_props'])}",
            },
        }

        all_passed = all(g["passed"] for g in gates.values())
        status = "pass" if all_passed else "fail"
        exit_code = 0 if all_passed else 1

        report = {
            "status": status,
            "mode": args.mode,
            "manuscript": str(args.manuscript),
            "han_range": {"min_han": min_han, "max_han": max_han},
            "body_han_count": body_han,
            "raw_han_count": count_han(raw),
            "excluded_lines": excluded,
            "dialogue": dialogue,
            "paragraph_pacing": pacing,
            "banned_expressions": banned,
            "paywall": paywall,
            "bible_ledger": ledger,
            "gates": gates,
            "remediation_hints": build_hints(
                gates, dialogue, pacing, banned, paywall, ledger, (min_han, max_han), body_han
            ),
        }
    except (InputError, OSError, UnicodeError, ValueError) as exc:
        report = {"status": "input_error", "error": str(exc)}
        exit_code = 2

    if args and args.output:
        try:
            save_report(args.output, report, args.manuscript)
        except (InputError, OSError, ValueError) as exc:
            report = {"status": "input_error", "error": str(exc)}
            exit_code = 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
