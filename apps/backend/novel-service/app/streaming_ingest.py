from __future__ import annotations

import hashlib
import mmap
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .parsing import (
    AliasUnit,
    ChapterUnit,
    EventDigest,
    NAME_RE,
    PassageUnit,
    SceneUnit,
    STOPWORDS,
    _extract_chapter_number,
)


CHINESE_CHAPTER_RE = re.compile(r"^\s*第\s*[0-9一二三四五六七八九十百千万零两〇]+\s*[章节卷回部篇].{0,50}$")
ENGLISH_CHAPTER_RE = re.compile(r"^\s*(chapter|vol|volume|book)\s+[0-9ivxlcdm]+[\s:：.\-].{0,60}$", re.IGNORECASE)
ARABIC_CHAPTER_RE = re.compile(r"^\s*[0-9]{1,4}\s*[.、\-:：]\s*[\w\u4e00-\u9fff ].{0,60}$")
MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s+.{1,60}$")
INDENTED_SHORT_RE = re.compile(r"^\s{2,}[\w\u4e00-\u9fff ].{1,40}$")
PUNCTUATION_END_RE = re.compile(r"[，。！？；：,.!?;:]$")


@dataclass(frozen=True)
class ChapterBlock:
    title: str
    body: str
    char_start: int
    strategy: str


@dataclass(frozen=True)
class StreamingNovelParse:
    chapters: list[ChapterUnit]
    scenes: list[SceneUnit]
    passages: list[PassageUnit]
    event_digests: list[EventDigest]
    aliases: list[AliasUnit]
    relation_edges: list[dict[str, object]]
    heading_strategy_counts: dict[str, int]


def iter_chapter_blocks(path: Path) -> Iterator[ChapterBlock]:
    """Yield chapter blocks using mmap-backed line scanning.

    Input:
    - path: UTF-8/UTF-16/GBK compatible novel file path.

    Output:
    - Ordered chapter blocks with detected heading strategy.

    Failure:
    - Raises OSError if the source file cannot be opened.
    """
    encoding = detect_text_encoding(path)
    with path.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as buffer:
            current_title = "Chapter 1"
            current_lines: list[str] = []
            current_start = 0
            current_strategy = "fallback"
            previous_blank = True
            cursor = 0

            while True:
                raw_line = buffer.readline()
                if not raw_line:
                    break
                decoded = raw_line.decode(encoding, errors="replace")
                stripped = decoded.strip()
                strategy = detect_heading_strategy(stripped, previous_blank=previous_blank)
                if strategy and current_lines:
                    body = "".join(current_lines).strip()
                    if body:
                        yield ChapterBlock(
                            title=current_title,
                            body=body,
                            char_start=current_start,
                            strategy=current_strategy,
                        )
                    current_title = stripped[:80]
                    current_lines = []
                    current_start = cursor + len(decoded)
                    current_strategy = strategy
                elif strategy:
                    current_title = stripped[:80]
                    current_start = cursor + len(decoded)
                    current_strategy = strategy
                else:
                    if not current_lines and stripped:
                        current_start = cursor
                    current_lines.append(decoded)

                previous_blank = not stripped
                cursor += len(decoded)

            body = "".join(current_lines).strip()
            if body:
                yield ChapterBlock(
                    title=current_title,
                    body=body,
                    char_start=current_start,
                    strategy=current_strategy,
                )


def detect_text_encoding(path: Path) -> str:
    with path.open("rb") as handle:
        sample = handle.read(65536)
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "gb18030", "gbk"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def detect_heading_strategy(line: str, *, previous_blank: bool) -> str:
    if not line:
        return ""
    if CHINESE_CHAPTER_RE.match(line):
        return "cn_chapter"
    if ENGLISH_CHAPTER_RE.match(line):
        return "en_chapter"
    if ARABIC_CHAPTER_RE.match(line):
        return "arabic_heading"
    if MARKDOWN_HEADING_RE.match(line):
        return "markdown_heading"
    if previous_blank and len(line) <= 40 and INDENTED_SHORT_RE.match(f"  {line}") and not PUNCTUATION_END_RE.search(line):
        return "stat_short_heading"
    return ""


def build_streaming_parse(blocks: list[ChapterBlock]) -> StreamingNovelParse:
    chapters: list[ChapterUnit] = []
    scenes: list[SceneUnit] = []
    passages: list[PassageUnit] = []
    event_digests: list[EventDigest] = []
    alias_counter: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    relation_counter: Counter[tuple[str, str]] = Counter()
    relation_support: dict[tuple[str, str], list[dict[str, object]]] = {}
    strategy_counts: Counter[str] = Counter()

    for chapter_index, block in enumerate(blocks, start=1):
        strategy_counts[block.strategy] += 1
        chapter = ChapterUnit(
            id=str(uuid4()),
            chapter_index=chapter_index,
            chapter_number=_extract_chapter_number(block.title, fallback=chapter_index),
            title=block.title or f"Chapter {chapter_index}",
            summary=summarize_text(block.body, 220),
            text=block.body,
            char_start=block.char_start,
            char_end=block.char_start + len(block.body),
        )
        chapters.append(chapter)
        chapter_scenes = build_scene_units(chapter)
        scenes.extend(chapter_scenes)
        for scene in chapter_scenes:
            digest = build_event_digest(scene)
            event_digests.append(digest)
            scene_passages = build_passage_units(scene)
            passages.extend(scene_passages)
            _update_alias_counter(alias_counter, first_seen, chapter.chapter_index, scene.text[:500])
            _update_relation_counter(
                relation_counter,
                relation_support,
                chapter.chapter_index,
                scene.scene_index,
                scene.text,
            )

        _update_alias_counter(alias_counter, first_seen, chapter.chapter_index, chapter.title)

    aliases = [
        AliasUnit(alias=name, canonical=name, kind="entity", first_chapter_index=first_seen[name])
        for name, count in alias_counter.most_common(120)
        if count >= 4
    ]
    relation_edges = [
        {
            "id": str(uuid4()),
            "entity_a": pair[0],
            "entity_b": pair[1],
            "relation_summary": f"{pair[0]} and {pair[1]} co-occur across scenes",
            "support_json": relation_support.get(pair, [])[:8],
        }
        for pair, count in relation_counter.most_common(80)
        if count >= 2
    ]
    return StreamingNovelParse(
        chapters=chapters,
        scenes=scenes,
        passages=passages,
        event_digests=event_digests,
        aliases=aliases,
        relation_edges=relation_edges,
        heading_strategy_counts=dict(strategy_counts),
    )


def build_scene_units(chapter: ChapterUnit) -> list[SceneUnit]:
    parts = [part.strip() for part in re.split(r"\n\s*\n+", chapter.text) if part.strip()]
    if not parts:
        parts = [chapter.text.strip()]

    scenes: list[SceneUnit] = []
    buffer: list[str] = []
    buffer_start = chapter.char_start
    scene_index = 1
    cursor = chapter.char_start
    transition_markers = (
        "随后",
        "然后",
        "不久",
        "与此同时",
        "次日",
        "当晚",
        "清晨",
        "傍晚",
        "离开",
        "来到",
        "回到",
    )

    for part in parts:
        part_start = cursor
        cursor += len(part) + 2
        candidate = "\n\n".join(buffer + [part]).strip()
        should_flush = False
        if candidate and len(candidate) >= 1600:
            should_flush = True
        elif buffer and any(marker in part for marker in transition_markers) and len(candidate) >= 600:
            should_flush = True

        if should_flush:
            text = "\n\n".join(buffer).strip()
            if text:
                scenes.append(
                    SceneUnit(
                        id=str(uuid4()),
                        chapter_id=chapter.id,
                        chapter_index=chapter.chapter_index,
                        scene_index=scene_index,
                        title=f"{chapter.title} / Scene {scene_index}",
                        summary=summarize_text(text, 160),
                        search_text=text[:600],
                        text=text,
                        char_start=buffer_start,
                        char_end=buffer_start + len(text),
                    )
                )
                scene_index += 1
            buffer = [part]
            buffer_start = part_start
        else:
            if not buffer:
                buffer_start = part_start
            buffer.append(part)

    if buffer:
        text = "\n\n".join(buffer).strip()
        scenes.append(
            SceneUnit(
                id=str(uuid4()),
                chapter_id=chapter.id,
                chapter_index=chapter.chapter_index,
                scene_index=scene_index,
                title=f"{chapter.title} / Scene {scene_index}",
                summary=summarize_text(text, 160),
                search_text=text[:600],
                text=text,
                char_start=buffer_start,
                char_end=buffer_start + len(text),
            )
        )
    return scenes


def build_passage_units(scene: SceneUnit) -> list[PassageUnit]:
    units: list[PassageUnit] = []
    cursor = 0
    passage_index = 1
    while cursor < len(scene.text):
        end = min(cursor + 900, len(scene.text))
        snippet = scene.text[cursor:end].strip()
        if snippet:
            units.append(
                PassageUnit(
                    id=str(uuid4()),
                    chapter_id=scene.chapter_id,
                    scene_id=scene.id,
                    chapter_index=scene.chapter_index,
                    scene_index=scene.scene_index,
                    passage_index=passage_index,
                    text=snippet,
                    search_text=snippet[:700],
                    char_start=scene.char_start + cursor,
                    char_end=scene.char_start + end,
                )
            )
            passage_index += 1
        if end >= len(scene.text):
            break
        cursor = max(end - 120, cursor + 1)
    return units


def build_event_digest(scene: SceneUnit) -> EventDigest:
    names = [token for token in NAME_RE.findall(scene.text[:220]) if token not in STOPWORDS][:3]
    where_match = re.search(r"(?:在|到|进入|回到)([\u4e00-\u9fff]{2,8})", scene.text[:200])
    where_text = where_match.group(1) if where_match else ""
    return EventDigest(
        id=str(uuid4()),
        chapter_id=scene.chapter_id,
        scene_id=scene.id,
        chapter_index=scene.chapter_index,
        scene_index=scene.scene_index,
        who_text=" / ".join(names),
        where_text=where_text,
        what_text=summarize_text(scene.text, 100),
        result_text=summarize_text(scene.text[-120:], 80),
        search_text=scene.text[:700],
    )


def summarize_text(text: str, limit: int) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return compact[:limit].strip()


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_summary_nodes(chapters: list[ChapterUnit]) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    if not chapters:
        return nodes

    for start in range(0, len(chapters), 10):
        group = chapters[start : start + 10]
        node_title = f"Volume {start // 10 + 1}"
        node_summary = "；".join(chapter.summary for chapter in group[:5])
        nodes.append(
            {
                "id": str(uuid4()),
                "node_level": "volume",
                "node_key": node_title.lower().replace(" ", "-"),
                "title": node_title,
                "summary": node_summary,
                "source_chapter_from": group[0].chapter_index,
                "source_chapter_to": group[-1].chapter_index,
            }
        )

    global_summary = "；".join(chapter.summary for chapter in (chapters[:3] + chapters[-3:]))[:2000]
    nodes.append(
        {
            "id": str(uuid4()),
            "node_level": "global",
            "node_key": "global",
            "title": "Global Summary",
            "summary": global_summary,
            "source_chapter_from": chapters[0].chapter_index,
            "source_chapter_to": chapters[-1].chapter_index,
        }
    )
    return nodes


def _update_alias_counter(counter: Counter[str], first_seen: dict[str, int], chapter_index: int, text: str) -> None:
    for token in NAME_RE.findall(text):
        if token in STOPWORDS:
            continue
        counter[token] += 1
        first_seen.setdefault(token, chapter_index)


def _update_relation_counter(
    counter: Counter[tuple[str, str]],
    support: dict[tuple[str, str], list[dict[str, object]]],
    chapter_index: int,
    scene_index: int,
    text: str,
) -> None:
    scene_names = list(dict.fromkeys(token for token in NAME_RE.findall(text[:500]) if token not in STOPWORDS))[:6]
    for index, left in enumerate(scene_names):
        for right in scene_names[index + 1 :]:
            pair = tuple(sorted((left, right)))
            counter[pair] += 1
            support.setdefault(pair, []).append(
                {
                    "chapter_index": chapter_index,
                    "scene_index": scene_index,
                    "quote": summarize_text(text, 120),
                }
            )
