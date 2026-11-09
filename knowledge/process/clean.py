"""Text cleaning. Conservative: never alters clinical numbers or comparison signs."""

from __future__ import annotations

import dataclasses
import html
import re
import unicodedata

from knowledge.models import Document

# Only real HTML-ish tags (a letter right after "<"), so "p<0.05" or "<5 mg" survive.
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACES = re.compile(r"[ \t ]+")
_BLANKS = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = _TAG.sub(" ", text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def clean_document(doc: Document) -> Document:
    return dataclasses.replace(doc, title=clean_text(doc.title), text=clean_text(doc.text))
