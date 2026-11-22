"""Score reviewed expectations against exported ADM task snapshots, offline."""
import argparse
import json
from collections import Counter
from pathlib import Path


MISSING = object()


def read_pointer(value, pointer):
    for token in pointer[1:].split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value.get(key, MISSING)
        elif isinstance(value, list) and key.isascii() and key.isdecimal() and int(key) < len(value):
            value = value[int(key)]
        else:
            return MISSING
    return value


def evaluate(cases):
    groups = {}
    seen = set()
    if not isinstance(cases, list) or not cases:
        raise ValueError("at least one labeled case is required")
    for case in cases:
        task, expected = case["task"], case["expected"]
        identity = case["caseId"], case["materialType"]
        if not all(isinstance(key, str) and key.strip() for key in identity):
            raise ValueError("caseId and materialType must be nonempty strings")
        if identity[0] in seen or not isinstance(expected, dict) or not expected:
            raise ValueError("case IDs must be unique and each case needs expected fields")
        if any(not path.startswith(("/adm/", "/lines/")) and path != "/lines" for path in expected):
            raise ValueError("expected fields must use /adm/... or /lines JSON Pointers")
        if task.get("state") not in ("SUCCEEDED", "FAILED"):
            raise ValueError("only completed task snapshots can be scored")
        seen.add(identity[0])
        version = (task.get("model"), task.get("promptVersion"), task.get("validationVersion"),
                   task.get("outputFormat") or case.get("outputFormat"))
        error = task.get("error") or {}
        final_correct = False
        candidates = {"raw": task.get("originalCandidate"), "validated": task.get("candidate")}
        for material_type in (None, identity[1]):
            counts, failures, models = groups.setdefault((*version, material_type), (Counter(), Counter(), Counter()))
            counts["cases"] += 1
            models[task.get("responseModel") or "UNKNOWN"] += 1
            if error:
                failures[error.get("code") or "UNKNOWN"] += 1
            counts["jsonObjects"] += isinstance(candidates["raw"], dict) or task.get("schemaMatched") is not None
            counts["shapeMeasured"] += type(task.get("schemaMatched")) is bool
            counts["schemaMatched"] += task.get("schemaMatched") is True
            counts["labeledFields"] += len(expected)
            for stage, candidate in candidates.items():
                matched = sum(read_pointer(candidate, path) == value for path, value in expected.items())
                counts[stage + "CorrectFields"] += matched
                counts[stage + "CorrectCases"] += matched == len(expected)
                if stage == "validated":
                    final_correct = matched == len(expected)
            passed = task["state"] == "SUCCEEDED" and task.get("saveStatus") == "SAVED"
            counts["passedGate"] += passed
            counts["incorrectPassedGate"] += passed and not final_correct
    keys = ("model", "promptVersion", "validationVersion", "outputFormat", "materialType")
    return [{**dict(zip(keys, group)), **counts, "failuresByCode": dict(failures),
             "responseModels": dict(models)}
            for group, (counts, failures, models) in groups.items()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8-sig"))
    print(json.dumps(evaluate(cases), ensure_ascii=False, indent=2))
