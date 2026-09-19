from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

_FM_RE = re.compile(
    r"\A\ufeff?---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|$)",
    re.DOTALL | re.MULTILINE,
)


@dataclass
class Document:
    meta: dict
    body: str
    text: str
    match: re.Match | None = None
    node: yaml.MappingNode | None = None
    fields: tuple = ()

    def with_integer(self, key: str, value: int) -> str | None:
        """Patch a counter, retaining its existing numeric quote style."""
        return self._with_scalar(key, str(value), keep_quotes=True)

    def with_scalar(self, key: str, value: str | int | bool) -> str | None:
        """Patch one scalar field while retaining unrelated Markdown."""
        style = "'" if isinstance(value, str) else None
        if isinstance(value, str):
            for key_node, value_node in self.fields:
                if (
                    key_node.value == key and isinstance(value_node, yaml.ScalarNode)
                    and value_node.style in ("'", '"')
                ):
                    style = value_node.style
        replacement = yaml.safe_dump(
            value, allow_unicode=True, default_flow_style=True, default_style=style,
        ).removesuffix("...\n").rstrip("\n")
        return self._with_scalar(key, replacement)

    def _with_scalar(self, key: str, replacement: str, *, keep_quotes: bool = False) -> str | None:
        """Patch a top-level scalar using its original YAML source marks.

        Compound and anchored values remain unchanged so a field update cannot
        alter other metadata through a YAML alias.
        """
        if self.match is None or self.node is None:
            return None
        header = self.match.group(1)
        offset = self.match.start(1)
        matching = [
            (k, v) for k, v in self.fields
            if isinstance(k, yaml.ScalarNode) and k.value == key
        ]
        if matching:
            key_node, value_node = matching[-1]  # same duplicate-key rule as PyYAML
            if not isinstance(value_node, yaml.ScalarNode):
                return None
            start, end = value_node.start_mark.index, value_node.end_mark.index
            if start < key_node.end_mark.index:
                # An alias node points back to its anchor, not this occurrence.
                alias = next(
                    (t for t in yaml.scan(header)
                     if isinstance(t, yaml.tokens.AliasToken)
                     and t.start_mark.index >= key_node.end_mark.index),
                    None,
                )
                if alias is None:
                    return None
                start, end = alias.start_mark.index, alias.end_mark.index
            fragment = header[start:end]
            if any(isinstance(t, yaml.tokens.AnchorToken) for t in yaml.scan(fragment)):
                return None
            if keep_quotes and fragment.startswith(("'", '"')):
                replacement = fragment[0] + replacement + fragment[0]
            if not fragment and start and header[start - 1] == ":":
                replacement = " " + replacement
            if fragment.endswith("\r\n"):
                replacement += "\r\n"
            elif fragment.endswith("\n"):
                replacement += "\n"
        elif self.node.flow_style:
            start = end = self.node.end_mark.index - 1  # before the closing }
            tokens = list(yaml.scan(header))
            closing = next(
                i for i, token in enumerate(tokens)
                if isinstance(token, yaml.tokens.FlowMappingEndToken)
                and token.end_mark.index == self.node.end_mark.index
            )
            comma = self.fields and not isinstance(
                tokens[closing - 1], yaml.tokens.FlowEntryToken
            )
            replacement = (", " if comma else " ") + f"{key}: {replacement}"
        else:
            start = end = self.node.end_mark.index
            newline = "\r\n" if "\r\n" in header else "\n"
            indent = " " * self.node.start_mark.column
            replacement = f"{indent}{key}: {replacement}{newline}"
        return self.text[:offset + start] + replacement + self.text[offset + end:]


def parse_document(text: str) -> Document:
    """Parse once, retaining YAML locations for lossless counter updates."""
    match = _FM_RE.match(text)
    if not match:
        return Document({}, text, text)
    body = text[match.end():]
    loader = None
    try:
        # PyYAML wheels usually include LibYAML. Both safe loaders expose the
        # same node marks; retain the Python fallback for source-only installs.
        loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)(match.group(1))
        node = loader.get_single_node()
        if not isinstance(node, yaml.MappingNode):
            return Document({}, body, text)
        # construct_document flattens YAML merges in-place; retain only keys
        # actually written at the top level so inherited counters are overridden.
        fields = tuple(node.value)
        meta = loader.construct_document(node)
    except (yaml.YAMLError, ValueError, OverflowError):
        return Document({}, body, text)
    finally:
        if loader is not None:
            loader.dispose()
    return Document(meta, body, text, match, node, fields)


def parse(text: str) -> tuple[dict, str]:
    document = parse_document(text)
    return document.meta, document.body


def dump(meta: dict, body: str) -> str:
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False)
    if not fm.endswith("\n"):
        fm += "\n"
    return f"---\n{fm}---\n\n{body.strip()}\n"
