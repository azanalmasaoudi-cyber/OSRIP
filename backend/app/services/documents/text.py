"""Text for PDF reports: Arabic letter shaping, right-to-left ordering and line wrapping.

PDF draws glyphs where it is told; it does not join Arabic letters or order mixed text. So:

* Shaping: each Arabic letter takes its isolated, initial, medial or final form (Unicode
  Arabic Presentation Forms-B) from its neighbours' joining types, with the lam-alef
  ligatures. Short-vowel marks (harakat) are left out, because placing them needs the
  font's positioning tables; letters outside the basic Arabic alphabet keep their base
  form.
* Ordering: a simplified Unicode Bidirectional Algorithm for one line: strong letters,
  numbers kept left to right with their separators, signs and percent, bracket pairs
  resolved from their content, other neutrals from their neighbours, then the standard
  reordering of levels (rule L2), with brackets mirrored in right-to-left runs.

Wrapping happens in logical order on spaces (a word longer than the line is cut), and each
line is then ordered for display. Text is otherwise never changed.
"""

from __future__ import annotations

from collections.abc import Callable

# (letter, number of forms): isolated, final[, initial, medial], from U+FE80 in this order.
_FORMS_ORDER = (
    (0x0621, 1), (0x0622, 2), (0x0623, 2), (0x0624, 2), (0x0625, 2), (0x0626, 4), (0x0627, 2),
    (0x0628, 4), (0x0629, 2), (0x062A, 4), (0x062B, 4), (0x062C, 4), (0x062D, 4), (0x062E, 4),
    (0x062F, 2), (0x0630, 2), (0x0631, 2), (0x0632, 2), (0x0633, 4), (0x0634, 4), (0x0635, 4),
    (0x0636, 4), (0x0637, 4), (0x0638, 4), (0x0639, 4), (0x063A, 4), (0x0641, 4), (0x0642, 4),
    (0x0643, 4), (0x0644, 4), (0x0645, 4), (0x0646, 4), (0x0647, 4), (0x0648, 2), (0x0649, 2),
    (0x064A, 4),
)  # fmt: skip
FORMS: dict[int, tuple[int, ...]] = {}
_next = 0xFE80
for _letter, _count in _FORMS_ORDER:
    FORMS[_letter] = tuple(range(_next, _next + _count))
    _next += _count
DUAL = {letter for letter, count in _FORMS_ORDER if count == 4}
RIGHT = {letter for letter, count in _FORMS_ORDER if count == 2} | {0x0671}
TATWEEL = 0x0640
# lam + alef variant -> (isolated, final) ligature
LAM_ALEF = {0x0622: (0xFEF5, 0xFEF6), 0x0623: (0xFEF7, 0xFEF8), 0x0625: (0xFEF9, 0xFEFA),
            0x0627: (0xFEFB, 0xFEFC)}  # fmt: skip
LAM = 0x0644
# Marks that do not take part in joining; left out of the drawn text (see the module note).
_MARKS = set(range(0x064B, 0x0660)) | {0x0670, 0x06D6, 0x06D7, 0x06D8, 0x06D9, 0x06DA,
                                       0x06DB, 0x06DC, 0x06DF, 0x06E0, 0x06E1, 0x06E2, 0x06E3,
                                       0x06E4, 0x06E7, 0x06E8, 0x06EA, 0x06EB, 0x06EC, 0x06ED}  # fmt: skip
# What each drawn presentation form stands for (for the PDF's text layer).
BASE_TEXT: dict[int, str] = {}
for _letter, _forms in FORMS.items():
    for _f in _forms:
        BASE_TEXT[_f] = chr(_letter)
for _alef, (_iso, _fin) in LAM_ALEF.items():
    BASE_TEXT[_iso] = BASE_TEXT[_fin] = chr(LAM) + chr(_alef)
MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<",
          "«": "»", "»": "«"}  # fmt: skip
_OPEN = {"(": ")", "[": "]", "{": "}"}
_DIGITS = (
    set("0123456789")
    | {chr(c) for c in range(0x0660, 0x066A)}
    | {chr(c) for c in range(0x06F0, 0x06FA)}
)
_NUMBER_INNER = set(".,:/٫٬")


def _joins_left(cp: int) -> bool:
    return cp in DUAL or cp == TATWEEL


def _joins_right(cp: int) -> bool:
    return cp in DUAL or cp in RIGHT or cp == TATWEEL


def shape(text: str) -> str:
    """Arabic letters in their contextual forms (logical order kept), marks left out."""
    chars = [c for c in text if ord(c) not in _MARKS]
    out: list[str] = []
    i = 0
    n = len(chars)
    while i < n:
        cp = ord(chars[i])
        prev = ord(chars[i - 1]) if i > 0 else None
        joined_before = prev is not None and _joins_left(prev) and _joins_right(cp)
        if cp == LAM and i + 1 < n and ord(chars[i + 1]) in LAM_ALEF:
            iso, fin = LAM_ALEF[ord(chars[i + 1])]
            out.append(chr(fin if joined_before else iso))
            i += 2
            continue
        forms = FORMS.get(cp)
        if forms is None:
            out.append(chars[i])
            i += 1
            continue
        nxt = ord(chars[i + 1]) if i + 1 < n else None
        joins_after = nxt is not None and _joins_left(cp) and _joins_right(nxt)
        if len(forms) == 4:
            index = (
                3
                if joined_before and joins_after
                else 1
                if joined_before
                else 2
                if joins_after
                else 0
            )
        else:
            index = 1 if joined_before and len(forms) > 1 else 0
        out.append(chr(forms[index]))
        i += 1
    return "".join(out)


def is_rtl(ch: str) -> bool:
    cp = ord(ch)
    return 0x0590 <= cp <= 0x08FF or 0xFB1D <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF


def _strong_ltr(ch: str) -> bool:
    return ch.isalpha() and not is_rtl(ch)


def direction(text: str, default_rtl: bool) -> bool:
    """The direction of a line in a document of the given direction: the document's own,
    unless the line has no letter of that direction (an Arabic sentence that begins with an
    English column name stays right to left; a purely English line in an Arabic report reads
    left to right)."""
    has_rtl = any(is_rtl(ch) and ch not in _DIGITS for ch in text)
    has_ltr = any(_strong_ltr(ch) for ch in text)
    if default_rtl:
        return has_rtl or not has_ltr
    return not has_ltr and has_rtl


def _classes(text: str) -> list[str]:
    """Per character: R, L, D (part of a number) or O (other neutral)."""
    out = ["O"] * len(text)
    for i, ch in enumerate(text):
        if ch in _DIGITS:
            out[i] = "D"
        elif is_rtl(ch):
            out[i] = "R"
        elif _strong_ltr(ch):
            out[i] = "L"
    # Separators between digits, a sign before a number and a percent sign after it belong to it.
    for i, ch in enumerate(text):
        if out[i] != "O":
            continue
        before = out[i - 1] if i > 0 else None
        after = out[i + 1] if i + 1 < len(text) else None
        if ch in _NUMBER_INNER and before == "D" and after == "D":
            out[i] = "D"
        elif ch in "+-−" and after == "D" and (before in (None, "O")):
            out[i] = "D"
    for i, ch in enumerate(text):
        if ch in "%٪‰" and i > 0 and out[i - 1] == "D":
            out[i] = "D"
    return out


def _resolve(text: str, rtl: bool) -> list[int]:
    """Embedding level per character for one line."""
    classes = _classes(text)
    base = "R" if rtl else "L"
    # Numbers act as the strong direction before them (L after L, otherwise R) for neutrals.
    effective: list[str] = []
    last_strong = base
    for c in classes:
        if c in ("R", "L"):
            last_strong = c
            effective.append(c)
        elif c == "D":
            effective.append("L" if last_strong == "L" else "R")
        else:
            effective.append("O")
    # Bracket pairs take the direction of their content (base direction when it has both).
    stack: list[tuple[str, int]] = []
    for i, ch in enumerate(text):
        if classes[i] != "O":
            continue
        if ch in _OPEN:
            stack.append((_OPEN[ch], i))
        elif stack and ch == stack[-1][0]:
            _, start = stack.pop()
            inside = {effective[k] for k in range(start + 1, i)} - {"O"}
            resolved = (
                base
                if (base in inside or not inside)
                else inside.pop()
                if len(inside) == 1
                else base
            )
            effective[start] = effective[i] = resolved
    # Other neutrals: the shared direction of the strong neighbours, else the base direction.
    n = len(text)
    i = 0
    while i < n:
        if effective[i] != "O":
            i += 1
            continue
        j = i
        while j < n and effective[j] == "O":
            j += 1
        before = effective[i - 1] if i > 0 else base
        after = effective[j] if j < n else base
        fill = before if before == after else base
        for k in range(i, j):
            effective[k] = fill
        i = j
    levels = []
    for c, e in zip(classes, effective, strict=True):
        if rtl:
            levels.append(1 if e == "R" and c != "D" else 2)
        else:
            levels.append(2 if c == "D" and e == "R" else 1 if e == "R" else 0)
    return levels


def visual(text: str, rtl: bool) -> str:
    """One line in drawing order (left to right), brackets mirrored in right-to-left runs."""
    if not text:
        return text
    levels = _resolve(text, rtl)
    chars = [
        MIRROR.get(ch, ch) if level % 2 else ch for ch, level in zip(text, levels, strict=True)
    ]
    top = max(levels)
    for level in range(top, 0, -1):
        i = 0
        while i < len(chars):
            if levels[i] >= level:
                j = i
                while j < len(chars) and levels[j] >= level:
                    j += 1
                chars[i:j] = chars[i:j][::-1]
                levels[i:j] = levels[i:j][::-1]
                i = j
            else:
                i += 1
    return "".join(chars)


def wrap(text: str, width: float, measure: Callable[[str], float]) -> list[str]:
    """Lines (logical order) that fit ``width`` as measured on shaped text."""
    lines: list[str] = []

    def flush_long(line: str) -> str:
        # A word longer than the line is cut where it fills the line.
        while measure(line) > width and len(line) > 1:
            cut = len(line)
            while cut > 1 and measure(line[:cut]) > width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
        return line

    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and measure(candidate) > width:
                lines.append(line)
                candidate = word
            line = flush_long(candidate)
        lines.append(line)
    return lines
