"""
generator/linter.py
Real Python static analysis using ast + pyflakes.
Dockerfile linting using rule-based checks.
Auto-detects file type from filename or content.
"""

import ast
import re
from typing import List, Dict


# ── File type detection ───────────────────────────────────────
def detect_filetype(code: str, filename: str) -> str:
    """
    Returns 'python' or 'dockerfile' based on filename and content.
    """
    fname = filename.lower().strip()

    # Filename-based detection
    if fname in ("dockerfile", "dockerfile.dev", "dockerfile.prod", "dockerfile.test"):
        return "dockerfile"
    if fname.startswith("dockerfile."):
        return "dockerfile"
    if fname.endswith(".py"):
        return "python"

    # Content-based detection — check first non-empty lines
    lines = [l.strip() for l in code.splitlines() if l.strip()]
    if lines:
        first = lines[0].upper()
        if first.startswith("FROM ") or first.startswith("# syntax="):
            return "dockerfile"
        # Count dockerfile instructions
        dockerfile_instructions = {
            "FROM", "RUN", "CMD", "LABEL", "EXPOSE", "ENV", "ADD",
            "COPY", "ENTRYPOINT", "VOLUME", "USER", "WORKDIR", "ARG",
            "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL"
        }
        df_hits = sum(
            1 for l in lines[:20]
            if l.split()[0].upper() in dockerfile_instructions
        )
        if df_hits >= 3:
            return "dockerfile"

    return "python"


# ── Python linting ────────────────────────────────────────────
def lint_python(code: str, filename: str = "script.py") -> List[Dict]:
    issues = []

    # Layer 1 — ast syntax check
    try:
        tree = ast.parse(code, filename=filename)
    except SyntaxError as e:
        issues.append({
            "severity": "error",
            "line": e.lineno or 0,
            "message": f"SyntaxError: {e.msg}"
        })
        return issues

    # Layer 2 — pyflakes (using reporter API for reliable capture)
    try:
        import pyflakes.api
        import pyflakes.reporter
        import io

        warning_messages = []
        error_messages   = []

        class CapturingReporter(pyflakes.reporter.Reporter):
            def flake(self, message):
                warning_messages.append({
                    "severity": "error" if "undefined" in str(message).lower() else "warning",
                    "line": message.lineno if hasattr(message, 'lineno') else 0,
                    "message": message.message % message.message_args
                })
            def unexpectedError(self, filename, msg):
                error_messages.append({"severity": "error", "line": 0, "message": str(msg)})
            def syntaxError(self, filename, msg, lineno, offset, text):
                error_messages.append({"severity": "error", "line": lineno or 0, "message": f"SyntaxError: {msg}"})

        reporter = CapturingReporter(io.StringIO(), io.StringIO())
        pyflakes.api.check(code, filename, reporter=reporter)
        issues.extend(warning_messages)
        issues.extend(error_messages)

    except ImportError:
        issues.append({
            "severity": "info",
            "line": 0,
            "message": "pyflakes not installed — run: pip install pyflakes"
        })
    except Exception:
        pass  # pyflakes failed silently — other checks still run

    # Layer 3 — security patterns
    lines = code.splitlines()
    for i, line in enumerate(lines, start=1):
        t = line.strip()

        # Match variable names that CONTAIN password/secret/api_key/token anywhere
        # Use word boundary only at start, allow suffix like _KEY, _TOKEN etc.
        if re.search(r'(?i)\b\w*(password|secret|api_key|token|api_secret|private_key)\w*\s*=\s*["\'][^"\']{3,}', t):
            issues.append({"severity": "error", "line": i,
                "message": "Hardcoded secret detected — use environment variables"})

        if re.search(r'\beval\s*\(', t):
            issues.append({"severity": "error", "line": i,
                "message": "eval() is a security risk — avoid dynamic code execution"})

        if "pickle.load(" in t and "# trusted" not in t:
            issues.append({"severity": "warning", "line": i,
                "message": "pickle.load() on untrusted data is unsafe — consider joblib or safetensors"})

        if re.search(r'os\.system\(|subprocess\.call\(|subprocess\.run\(.+shell=True', t):
            issues.append({"severity": "warning", "line": i,
                "message": "Shell command with potential injection risk — validate all inputs"})

    # Layer 4 — ML-specific checks
    # Join continuation lines so multiline calls are checked correctly
    # e.g. train_test_split(\n    X, y, random_state=SEED\n)
    joined_lines = {}
    raw_lines = code.splitlines()
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        combined = line
        j = i + 1
        # If line ends with ( or , it likely continues on next line
        while j < len(raw_lines) and line.rstrip().endswith(('(', ',', '\\')):
            combined += " " + raw_lines[j].strip()
            line = raw_lines[j]
            j += 1
        joined_lines[i + 1] = combined  # 1-indexed
        i = j if j > i + 1 else i + 1

    for i, line in enumerate(lines, start=1):
        t = line.strip()
        # Use joined version for multiline call checks
        t_joined = joined_lines.get(i, t)

        if re.search(r'(RandomForest|GradientBoosting|DecisionTree|SVM|KMeans)\w*\(', t):
            if "random_state" not in t_joined:
                issues.append({"severity": "warning", "line": i,
                    "message": "sklearn estimator missing random_state — results won't be reproducible"})

        if "train_test_split(" in t and "random_state" not in t_joined:
            issues.append({"severity": "warning", "line": i,
                "message": "train_test_split missing random_state — split will differ between runs"})

        if re.search(r'\w+\s*=\s*\(?\w+\.predict\(\w+\)\s*==', t):
            if ".mean()" not in t and ".sum()" not in t and "float(" not in t:
                issues.append({"severity": "error", "line": i,
                    "message": "Comparison returns ndarray not scalar — use .mean() or float(x.sum()/len(y))"})

        if t == "except:" or stripped_starts_bare_except(t):
            issues.append({"severity": "warning", "line": i,
                "message": "Bare except: catches all exceptions including KeyboardInterrupt — use except Exception"})

        if "json.dump(" in t and "default=" not in t:
            if "import numpy" in code or "import numpy as" in code:
                issues.append({"severity": "warning", "line": i,
                    "message": "json.dump() with numpy in scope — ndarray values will raise TypeError. Add default= handler"})

    # Deduplicate
    seen = set()
    deduped = []
    for issue in issues:
        key = (issue["line"], issue["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(issue)

    deduped.sort(key=lambda x: x["line"])
    return deduped


def stripped_starts_bare_except(t: str) -> bool:
    return bool(re.match(r'^except\s*:\s*$', t))


# ── Dockerfile linting ────────────────────────────────────────
def lint_dockerfile(code: str, filename: str = "Dockerfile") -> List[Dict]:
    issues = []
    lines  = code.splitlines()

    has_workdir     = False
    has_user        = False
    has_healthcheck = False
    from_count      = 0
    run_commands    = []
    last_apt_update_line = -1

    for i, line in enumerate(lines, start=1):
        t       = line.strip()
        t_upper = t.upper()

        # Skip comments and blank lines
        if not t or t.startswith("#"):
            continue

        parts = t.split()
        instruction = parts[0].upper() if parts else ""

        # FROM checks
        if instruction == "FROM":
            from_count += 1
            image_ref = parts[1] if len(parts) > 1 else ""
            # latest tag
            if image_ref.endswith(":latest") or (":" not in image_ref and "@" not in image_ref):
                if image_ref.lower() not in ("scratch",):
                    issues.append({"severity": "warning", "line": i,
                        "message": f"Unpinned image tag '{image_ref}' — use a specific version tag for reproducible builds"})

        # WORKDIR
        if instruction == "WORKDIR":
            has_workdir = True

        # USER
        if instruction == "USER":
            has_user = True
            user_val = parts[1] if len(parts) > 1 else ""
            if user_val in ("root", "0"):
                issues.append({"severity": "error", "line": i,
                    "message": "Running as root (USER root) is a security risk — use a non-root user"})

        # HEALTHCHECK
        if instruction == "HEALTHCHECK":
            has_healthcheck = True

        # ADD vs COPY
        if instruction == "ADD":
            src = parts[1] if len(parts) > 1 else ""
            if not src.startswith("http") and not src.endswith(".tar.gz") and not src.endswith(".tgz"):
                issues.append({"severity": "warning", "line": i,
                    "message": "Use COPY instead of ADD — ADD has implicit behaviour (auto-extract, URL fetch). Use COPY for simple file copies"})

        # RUN checks
        if instruction == "RUN":
            run_body = " ".join(parts[1:])
            run_commands.append((i, run_body))

            # apt-get update without install in same RUN
            if "apt-get update" in run_body and "apt-get install" not in run_body:
                last_apt_update_line = i
                issues.append({"severity": "warning", "line": i,
                    "message": "apt-get update without apt-get install in same RUN — cache may be stale. Combine into one RUN layer"})

            # apt-get install without --no-install-recommends
            if "apt-get install" in run_body and "--no-install-recommends" not in run_body:
                issues.append({"severity": "warning", "line": i,
                    "message": "apt-get install missing --no-install-recommends — adds unnecessary packages, increases image size"})

            # apt-get without rm -rf /var/lib/apt/lists
            if "apt-get install" in run_body and "rm -rf /var/lib/apt/lists" not in run_body:
                issues.append({"severity": "warning", "line": i,
                    "message": "apt-get install without cleaning apt cache — add && rm -rf /var/lib/apt/lists/* to reduce image size"})

            # chmod 777
            if "chmod 777" in run_body or "chmod -R 777" in run_body:
                issues.append({"severity": "error", "line": i,
                    "message": "chmod 777 grants world-writable permissions — use least-privilege permissions instead"})

            # pip install without --no-cache-dir
            if "pip install" in run_body and "--no-cache-dir" not in run_body:
                issues.append({"severity": "warning", "line": i,
                    "message": "pip install missing --no-cache-dir — pip cache is stored in image, increasing size unnecessarily"})

            # curl/wget piped to shell — risky
            if re.search(r'(curl|wget).+\|\s*(bash|sh|python)', run_body):
                issues.append({"severity": "error", "line": i,
                    "message": "Piping curl/wget directly to shell is a security risk — download, verify, then execute separately"})

        # ENV hardcoded secrets
        if instruction == "ENV":
            env_body = " ".join(parts[1:])
            if re.search(r'(PASSWORD|SECRET|API_KEY|TOKEN)\s*=\s*\S+', env_body, re.IGNORECASE):
                issues.append({"severity": "error", "line": i,
                    "message": "Hardcoded secret in ENV instruction — secrets baked into image layers are visible in docker history"})

        # EXPOSE checks
        if instruction == "EXPOSE":
            port = parts[1] if len(parts) > 1 else ""
            if port in ("22", "23", "3306", "5432", "6379", "27017"):
                issues.append({"severity": "warning", "line": i,
                    "message": f"Exposing sensitive port {port} — avoid exposing database/SSH ports unless necessary"})

        # COPY requirements before COPY . . pattern check
        if instruction == "COPY" and len(parts) >= 3:
            src = parts[1]
            if src == "." and not has_workdir:
                issues.append({"severity": "warning", "line": i,
                    "message": "COPY . . before WORKDIR is set — files will land in root directory"})

    # End-of-file checks
    if not has_workdir:
        issues.append({"severity": "warning", "line": 0,
            "message": "No WORKDIR instruction — files will be placed in root directory. Add WORKDIR /app"})

    if not has_user:
        issues.append({"severity": "warning", "line": 0,
            "message": "No USER instruction — container runs as root by default. Add a non-root USER for security"})

    if not has_healthcheck and from_count > 0:
        issues.append({"severity": "info", "line": 0,
            "message": "No HEALTHCHECK instruction — Docker can't detect if your app is unhealthy inside the container"})

    # Multiple consecutive RUN commands that could be combined
    if len(run_commands) >= 3:
        consecutive = []
        prev_line = -2
        for ln, body in run_commands:
            if ln == prev_line + 1:
                consecutive.append(ln)
            else:
                consecutive = [ln]
            prev_line = ln
            if len(consecutive) >= 3:
                issues.append({"severity": "info", "line": consecutive[0],
                    "message": f"Multiple consecutive RUN instructions — combine with && to reduce image layers"})
                consecutive = []
                break

    issues.sort(key=lambda x: x["line"])
    return issues


# ── Main entry point ──────────────────────────────────────────
def lint_code(code: str, filename: str = "script.py") -> List[Dict]:
    """Auto-detect file type and run appropriate linter."""
    filetype = detect_filetype(code, filename)
    if filetype == "dockerfile":
        return lint_dockerfile(code, filename)
    return lint_python(code, filename)


def summarize(issues: List[Dict]) -> Dict:
    errors   = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    infos    = sum(1 for i in issues if i["severity"] == "info")
    return {"errors": errors, "warnings": warnings, "infos": infos, "total": len(issues)}