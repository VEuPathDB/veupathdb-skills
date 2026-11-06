"""YAML for STF files. Pure.

dump_yaml writes block-style YAML that R's yaml package (YAML 1.1) and a YAML 1.2
reader both read back as the same text: a string is written plain unless
needs_quoting says otherwise. load_stf_yaml reads the subset STF files use with
yaml-lite's typing (yes/no stay text, dates stay text) and rejects anchors,
aliases, tags, extra documents and flow mappings with content.
"""

import io
import json
import re
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError
from ruamel.yaml.events import (
    AliasEvent, DocumentStartEvent, MappingEndEvent, MappingStartEvent, ScalarEvent,
    SequenceEndEvent, SequenceStartEvent, StreamEndEvent,
)
from ruamel.yaml.representer import RoundTripRepresenter
from ruamel.yaml.resolver import BaseResolver

_A = re.ASCII

# Plain scalars a YAML 1.1 reader (R's yaml) may resolve to a number: decimals with an optional
# trailing dot, exponent or _ separators (1., 1e3, 1_000), hex/octal/binary (0x1F, 0o17, 0b101),
# sexagesimal (1:30), and .inf/.nan in any case and sign.
_NUMERIC = [
    re.compile(r"[-+]?(\d[\d_]*(\.[\d_]*)?|\.\d[\d_]*)([eE][-+]?\d+)?", _A),
    re.compile(r"[-+]?0(x[0-9a-f_]+|o[0-7_]+|b[01_]+)", _A | re.IGNORECASE),
    re.compile(r"[-+]?\d[\d_]*(:[0-5]?\d)+(\.[\d_]*)?", _A),
    re.compile(r"[-+]?\.(inf|nan)", _A | re.IGNORECASE),
]
_YAML11_WORDS = re.compile(r"y|yes|n|no|on|off|true|false|null|~", _A | re.IGNORECASE)
_CONTROL = re.compile(r"[\n\r\t]")
_EDGE_SPACE = re.compile(r"^\s|\s$")
_COLON = re.compile(r": |:$")
_SPACE_HASH = re.compile(r"\s#")
_INDICATOR = re.compile(r"[-?:,\[\]{}#&*!|>'\"%@`]")


def _looks_numeric(s: str) -> bool:
    return any(p.fullmatch(s) for p in _NUMERIC)


def yaml11_resolves(s: str) -> bool:
    """True if R's yaml (YAML 1.1) would read the plain scalar s as something other than text."""
    return _YAML11_WORDS.fullmatch(s) is not None or _looks_numeric(s)


def needs_quoting(s: str) -> bool:
    """The yamlScalar rule from stf-common.js: whether s must be quoted to be read back as text."""
    return (
        s == ""
        or _CONTROL.search(s) is not None
        or _EDGE_SPACE.search(s) is not None
        or _COLON.search(s) is not None
        or _SPACE_HASH.search(s) is not None
        or _INDICATOR.match(s) is not None
        or yaml11_resolves(s)
    )


# ---- writer ----

_STR = "tag:yaml.org,2002:str"


class _Representer(RoundTripRepresenter):
    pass


def _represent_str(self, data: str):
    if not needs_quoting(data):
        style = None
    elif _CONTROL.search(data):
        style = '"'  # single quotes would fold the line break
    else:
        style = "'"
    return self.represent_scalar(_STR, data, style=style)


_Representer.add_representer(str, _represent_str)


class _PlainValueResolver(BaseResolver):
    """Resolves plain scalars the way load_stf_yaml types them, so the emitter writes every
    string needs_quoting leaves plain without quotes or a !!str tag (e.g. 2023-01-01)."""

    def __init__(self, version: Any = None, loader: Any = None, loadumper: Any = None):
        super().__init__(loadumper if loadumper is not None else loader)


for _tag, _pattern, _first in [
    ("tag:yaml.org,2002:null", r"(?i:null|~)?\Z", "nN~"),
    ("tag:yaml.org,2002:bool", r"(?i:true|false)\Z", "tTfF"),
    ("tag:yaml.org,2002:int", r"-?\d+\Z", "-0123456789"),
    ("tag:yaml.org,2002:float", r"-?(\d+\.\d+|\.\d+)\Z", "-.0123456789"),
]:
    _PlainValueResolver.add_implicit_resolver(_tag, re.compile(_pattern, _A), list(_first) + [""])


def dump_yaml(data: Any) -> str:
    yaml = YAML(typ="rt")
    yaml.Representer = _Representer
    yaml.Resolver = _PlainValueResolver
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    out = io.StringIO()
    yaml.dump(data, out)
    return out.getvalue()


# ---- reader ----

class YamlError(ValueError):
    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.line = line


_INT = re.compile(r"-?\d+", _A)
_DECIMAL = re.compile(r"-?(\d+\.\d+|\.\d+)", _A)
_NULL = re.compile(r"null|~", _A | re.IGNORECASE)
_BOOL = re.compile(r"true|false", _A | re.IGNORECASE)


def _plain_value(s: str) -> Any:
    """yaml-lite's typing: numbers, booleans and null resolve; yes/no stay strings."""
    if s == "" or _NULL.fullmatch(s):
        return None
    if _BOOL.fullmatch(s):
        return s.lower() == "true"
    if _INT.fullmatch(s):
        return int(s)
    if _DECIMAL.fullmatch(s):
        f = float(s)
        return int(f) if f.is_integer() else f
    return s


def _line(event) -> int:
    return event.start_mark.line + 1


class _Builder:
    def __init__(self, events):
        self.events = events
        self.warnings: list[str] = []

    def next(self):
        return next(self.events)

    def check(self, event):
        if isinstance(event, AliasEvent):
            raise YamlError("unsupported YAML construct: *", _line(event))
        if getattr(event, "anchor", None) is not None:
            raise YamlError("unsupported YAML construct: &", _line(event))
        if getattr(event, "tag", None) is not None:
            raise YamlError("unsupported YAML construct: !", _line(event))

    def node(self, event, flow_item: bool = False) -> Any:
        self.check(event)
        if isinstance(event, ScalarEvent):
            return self.scalar(event)
        if flow_item:
            raise YamlError("nested flow collections are not supported", _line(event))
        if isinstance(event, SequenceStartEvent):
            return self.sequence(event)
        if isinstance(event, MappingStartEvent):
            return self.mapping(event)
        raise YamlError("unexpected content", _line(event))

    def scalar(self, event) -> Any:
        if event.style:  # quoted or block scalar
            return event.value
        value = _plain_value(event.value)
        if isinstance(value, str) and yaml11_resolves(value):
            self.warnings.append(
                f"line {_line(event)}: unquoted value {json.dumps(value, ensure_ascii=False)} would be read "
                "as a non-text value by study-wrangler's YAML 1.1 reader; quote it")
        return value

    def sequence(self, start) -> list:
        flow = bool(start.flow_style)
        out = []
        while True:
            event = self.next()
            if isinstance(event, SequenceEndEvent):
                if flow and event.start_mark.line != start.start_mark.line:
                    raise YamlError("unterminated flow sequence (multi-line flow is not supported)", _line(start))
                return out
            out.append(self.node(event, flow_item=flow))

    def mapping(self, start) -> dict:
        out = {}
        while True:
            event = self.next()
            if isinstance(event, MappingEndEvent):
                return out
            if start.flow_style:
                raise YamlError("flow mappings with content are not supported", _line(start))
            self.check(event)
            if not isinstance(event, ScalarEvent):
                raise YamlError("unsupported YAML construct: complex mapping key", _line(event))
            out[event.value] = self.node(self.next())


def _error_line(e: MarkedYAMLError) -> int:
    # An unterminated quoted string is reported at the end of the stream; point at its start
    if e.context_mark is not None and e.context and "quoted scalar" in e.context:
        return e.context_mark.line + 1
    mark = e.problem_mark or e.context_mark
    return mark.line + 1 if mark is not None else 1


def load_stf_yaml(text: str) -> tuple[Any, list[str]]:
    """Reads an STF YAML file; returns (data, warnings). Raises YamlError on unsupported YAML."""
    builder = _Builder(iter(YAML(typ="safe", pure=True).parse(text)))
    try:
        data = None
        documents = 0
        while True:
            event = builder.next()
            if isinstance(event, StreamEndEvent):
                return data, builder.warnings
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if documents > 1:
                    raise YamlError("multiple documents are not supported", _line(event))
                data = builder.node(builder.next())
    except MarkedYAMLError as e:
        raise YamlError(e.problem or str(e), _error_line(e)) from None
