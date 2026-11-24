"""A validator for the question sheet's published schemas (sminos/types/sheet/schema/), which hold JSON Schema
2020-12 to the keywords the plan's I1 names: type, properties, required, additionalProperties, enum, const, items,
minItems, maxItems, minLength, maxLength, minimum, pattern, oneOf, and $ref into the same file's $defs. The suite's
runners have no schema library. A keyword outside that set is an error of the schema, so a schema that grows past
what another repository's validator is promised fails here first. Lengths count code points (K5); a pattern is
read as ECMA-262 reads it (`$` is the end of input).

    errors(schema, instance) -> [str]      empty when the instance is valid
"""

import re

ANNOTATIONS = {"$schema", "$id", "$defs", "title", "description", "$comment"}
KEYWORDS = {"type", "properties", "required", "additionalProperties", "enum", "const", "items", "minItems",
            "maxItems", "minLength", "maxLength", "minimum", "pattern", "oneOf", "$ref"}
TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def ecma(pattern):
    """A pattern as ECMA-262 reads it, for Python's `re`: `$` with no flags is the end of input there, where Python's
    also matches before a last newline. The published patterns use `$` only as their last character."""
    return pattern[:-1] + r"\Z" if pattern.endswith("$") and not pattern.endswith("\\$") else pattern


def _equal(a, b):
    """JSON equality: 1 is not true, 1 equals 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return type(a) in (int, float) and type(b) in (int, float) and a == b or a == b and type(a) is type(b)


def errors(schema, instance, root=None, path="$"):
    root = schema if root is None else root
    out = []
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        return ["%s: the schema uses keywords outside the set: %s" % (path, ", ".join(sorted(unknown)))]
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            return ["%s: $ref %s is not into $defs" % (path, ref)]
        out += errors(root["$defs"][ref[len("#/$defs/"):]], instance, root, path)
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(TYPES[k](instance) for k in kinds):
            return out + ["%s: not of type %s" % (path, "/".join(kinds))]
    if "const" in schema and not _equal(instance, schema["const"]):
        out.append("%s: not %r" % (path, schema["const"]))
    if "enum" in schema and not any(_equal(instance, e) for e in schema["enum"]):
        out.append("%s: %r not one of %r" % (path, instance, schema["enum"]))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            out.append("%s: shorter than %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            out.append("%s: longer than %d" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(ecma(schema["pattern"]), instance):
            out.append("%s: does not match %s" % (path, schema["pattern"]))
    if TYPES["number"](instance) and "minimum" in schema and instance < schema["minimum"]:
        out.append("%s: below %s" % (path, schema["minimum"]))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            out.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            out.append("%s: more than %d items" % (path, schema["maxItems"]))
        if "items" in schema:
            for i, v in enumerate(instance):
                out += errors(schema["items"], v, root, "%s[%d]" % (path, i))
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in instance:
                out.append("%s: %s is required" % (path, k))
        for k, v in instance.items():
            if k in props:
                out += errors(props[k], v, root, "%s.%s" % (path, k))
            elif "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    out.append("%s: %s is not allowed" % (path, k))
                elif isinstance(extra, dict):
                    out += errors(extra, v, root, "%s.%s" % (path, k))
    if "oneOf" in schema:
        passing = [i for i, s in enumerate(schema["oneOf"]) if not errors(s, instance, root, path)]
        if len(passing) != 1:
            out.append("%s: matches %d of oneOf's %d" % (path, len(passing), len(schema["oneOf"])))
    return out
