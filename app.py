import os
import sys
import subprocess
import zipfile
import tempfile
from flask import Flask, render_template, request, send_file, jsonify
from generator.composer import (
    generate_dockerfile,
    generate_dockerfile_for_service,
    generate_compose,
    generate_compose_multi,
    get_stack_defaults,
)
from generator.linter   import lint_code, summarize
from generator.scanner  import scan_image

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mlops-intern-task")
UPLOAD_FOLDER  = tempfile.mkdtemp()


# ── Index ────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# ── Stack defaults ───────────────────────────────────────────
@app.route("/stack-defaults", methods=["GET"])
def stack_defaults():
    stack = request.args.get("stack", "python")
    return jsonify(get_stack_defaults(stack))


# ── Generate single-service (kept for OPS tab) ───────────────
@app.route("/generate", methods=["POST"])
def generate():
    service_name = request.form.get("service_name", "app").strip()
    port         = request.form.get("port", "8080").strip()
    image_base   = request.form.get("image_base", "python:3.11-slim").strip()
    stack        = request.form.get("stack", "python").strip()
    env_vars_raw = request.form.get("env_vars", "").strip()
    volumes_raw  = request.form.get("volumes", "").strip()

    env_vars = {}
    for line in env_vars_raw.splitlines():
        line = line.strip()
        if "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()

    volumes = [v.strip() for v in volumes_raw.splitlines() if v.strip()]

    dockerfile_content = generate_dockerfile(image_base, port, stack)
    compose_content    = generate_compose(service_name, port, env_vars, volumes)

    zip_path = os.path.join(UPLOAD_FOLDER, "docker_output.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Dockerfile", dockerfile_content)
        zf.writestr("docker-compose.yml", compose_content)
        zf.writestr("entrypoint.sh", open("generator/entrypoint.sh").read())

    return send_file(zip_path, as_attachment=True, download_name="docker_output.zip")


# ── Generate multi-service  ← NEW ───────────────────────────
@app.route("/generate-multi", methods=["POST"])
def generate_multi():
    """
    Body JSON:
      services:      [{ name, type, build, base_image, stack, image,
                        ports[], volumes[], environment[], command,
                        depends_on[], restart,
                        healthcheck: {test, interval, timeout, retries, start_period} }]
      named_volumes: ["grafana_data", ...]

    Zip structure:
      docker-compose.yml            ← always at root
      Dockerfile + entrypoint.sh    ← single build service → root
      <n>/Dockerfile                ← multiple build services → subfolders
      <n>/entrypoint.sh
    Image-only services get no Dockerfile (they pull from a registry).
    """
    data          = request.get_json(force=True)
    services      = data.get("services", [])
    named_volumes = data.get("named_volumes", [])

    if not services:
        return jsonify({"error": "No services provided"}), 400

    # Log received service types for debugging
    import sys
    print(f"[generate-multi] received {len(services)} services: "
          f"{[(s.get('name'), s.get('type')) for s in services]}", file=sys.stderr)

    build_services = [s for s in services if s.get("type") == "build"]

    # Build context per service:
    #   1 build service  → build: .     (Dockerfile at zip root)
    #   2+ build services → build: ./<n> (each in its own subfolder)
    build_ctx_overrides = {
        (s.get("name") or "service").strip(): (
            "." if len(build_services) == 1
            else f"./{(s.get('name') or 'service').strip()}"
        )
        for s in build_services
    }

    named_networks  = data.get("named_networks", [])
    compose_content = generate_compose_multi(
        services, named_volumes, named_networks, build_ctx_overrides=build_ctx_overrides
    )

    try:
        with open("generator/entrypoint.sh") as f:
            entrypoint = f.read()
    except FileNotFoundError:
        entrypoint = (
            "#!/bin/bash\nset -e\n\n"
            "echo '[entrypoint] Starting ML pipeline...'\n\n"
            "python train.py\n\n"
            "echo '[entrypoint] Training complete. Running evaluation...'\n\n"
            "python evaluate.py\n\n"
            "echo '[entrypoint] Pipeline finished.'\n"
        )

    zip_path = os.path.join(UPLOAD_FOLDER, "docker_output_multi.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("docker-compose.yml", compose_content)
        for svc in build_services:
            name   = (svc.get("name") or "service").strip()
            prefix = "" if len(build_services) == 1 else f"{name}/"
            zf.writestr(f"{prefix}Dockerfile",    generate_dockerfile_for_service(svc))
            zf.writestr(f"{prefix}entrypoint.sh", entrypoint)

    return send_file(zip_path, as_attachment=True, download_name="docker_output.zip")


# ── Preview multi-service YAML (no download)  ← NEW ─────────
@app.route("/preview-multi", methods=["POST"])
def preview_multi():
    data           = request.get_json(force=True)
    services       = data.get("services", [])
    named_volumes  = data.get("named_volumes", [])
    named_networks = data.get("named_networks", [])
    yaml           = generate_compose_multi(services, named_volumes, named_networks)
    return jsonify({"yaml": yaml})


# ── Lint ─────────────────────────────────────────────────────
@app.route("/lint", methods=["POST"])
def lint():
    data     = request.get_json()
    code     = data.get("code", "").strip()
    filename = data.get("filename", "script.py").strip()

    if not code:
        return jsonify({"error": "No code provided"}), 400

    issues = lint_code(code, filename)
    return jsonify({
        "filename": filename,
        "issues":   issues,
        "summary":  summarize(issues)
    })


# ── Scan ─────────────────────────────────────────────────────
@app.route("/scan", methods=["POST"])
def scan():
    data     = request.get_json()
    image    = data.get("image", "").strip()
    severity = data.get("severity", "CRITICAL,HIGH,MEDIUM,LOW").strip()

    if not image:
        return jsonify({"error": "No image provided"}), 400

    result = scan_image(image, severity)
    return jsonify(result)


# ── One-Click OPS ────────────────────────────────────────────
@app.route("/ops", methods=["POST"])
def ops():
    data = request.get_json()

    project_dir  = data.get("project_dir", "").strip() or None
    image_base   = data.get("image_base", "python:3.11-slim").strip()
    stack        = data.get("stack", "python").strip()
    code         = data.get("code", "").strip()
    filename     = data.get("filename", "train.py").strip()
    stop_on_lint = data.get("stop_on_lint", True)
    stop_on_scan = data.get("stop_on_scan", True)
    severity     = data.get("severity", "CRITICAL,HIGH")

    steps = []

    # Step 1 — Generate
    steps.append({
        "step":    "generate",
        "status":  "ok",
        "message": f"Dockerfile ({stack}) + docker-compose.yml generated"
    })

    # Step 2 — Lint
    if code and stack == "python":
        lint_issues  = lint_code(code, filename)
        lint_summary = summarize(lint_issues)
        if lint_summary["errors"] > 0 and stop_on_lint:
            steps.append({
                "step":    "lint",
                "status":  "error",
                "message": f"{lint_summary['errors']} lint error(s) found — pipeline aborted",
                "issues":  lint_issues
            })
            return jsonify({"status": "aborted", "aborted_at": "lint", "steps": steps})
        steps.append({
            "step":    "lint",
            "status":  "warning" if lint_summary["errors"] > 0 else "ok",
            "message": f"{lint_summary['errors']} errors, {lint_summary['warnings']} warnings",
            "issues":  lint_issues
        })
    else:
        reason = "no code provided" if not code else f"linting not supported for {stack}"
        steps.append({"step": "lint", "status": "skipped", "message": f"Skipped — {reason}"})

    # Step 3 — Scan
    scan_result    = scan_image(image_base, severity)
    scan_summary   = scan_result.get("summary", {})
    critical_count = scan_summary.get("CRITICAL", 0)
    if critical_count > 0 and stop_on_scan:
        steps.append({
            "step":            "scan",
            "status":          "error",
            "message":         f"{critical_count} critical CVE(s) in {image_base} — pipeline aborted",
            "vulnerabilities": scan_result["vulnerabilities"]
        })
        return jsonify({"status": "aborted", "aborted_at": "scan", "steps": steps})
    steps.append({
        "step":            "scan",
        "status":          "warning" if critical_count > 0 else "ok",
        "message":         f"CRITICAL:{scan_summary.get('CRITICAL',0)} HIGH:{scan_summary.get('HIGH',0)} MEDIUM:{scan_summary.get('MEDIUM',0)}",
        "vulnerabilities": scan_result["vulnerabilities"]
    })

    # Step 4 — Build (real: docker compose build)
    try:
        result = subprocess.run(
            ["docker", "compose", "build"],
            capture_output=True, text=True, timeout=300,
            cwd=project_dir or None
        )
        if result.returncode == 0:
            steps.append({
                "step":    "build",
                "status":  "ok",
                "message": "docker compose build succeeded"
            })
        else:
            err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
            steps.append({
                "step":    "build",
                "status":  "error",
                "message": f"docker compose build failed — {err}"
            })
            return jsonify({"status": "aborted", "aborted_at": "build", "steps": steps})
    except FileNotFoundError:
        steps.append({"step": "build", "status": "error",
                      "message": "docker not found — is Docker installed and running?"})
        return jsonify({"status": "aborted", "aborted_at": "build", "steps": steps})
    except subprocess.TimeoutExpired:
        steps.append({"step": "build", "status": "error",
                      "message": "docker compose build timed out after 5 minutes"})
        return jsonify({"status": "aborted", "aborted_at": "build", "steps": steps})

    # Step 5 — Deploy (real: docker compose up -d)
    try:
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            capture_output=True, text=True, timeout=120,
            cwd=project_dir or None
        )
        if result.returncode == 0:
            # Count services that started
            started = [l for l in result.stderr.splitlines() if "Started" in l or "Running" in l or "Created" in l]
            msg = f"{len(started)} container(s) started" if started else "all services started"
            steps.append({"step": "deploy", "status": "ok", "message": msg})
        else:
            err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
            steps.append({
                "step":    "deploy",
                "status":  "error",
                "message": f"docker compose up failed — {err}"
            })
            return jsonify({"status": "aborted", "aborted_at": "deploy", "steps": steps})
    except FileNotFoundError:
        steps.append({"step": "deploy", "status": "error",
                      "message": "docker not found — is Docker installed and running?"})
        return jsonify({"status": "aborted", "aborted_at": "deploy", "steps": steps})
    except subprocess.TimeoutExpired:
        steps.append({"step": "deploy", "status": "error",
                      "message": "docker compose up timed out after 2 minutes"})
        return jsonify({"status": "aborted", "aborted_at": "deploy", "steps": steps})

    # Step 6 — Monitor (real: health check each service)
    import urllib.request
    import urllib.error
    import time

    # Wait for services to be ready after deploy
    # Poll every 3s for up to 60s before giving up
    print("[monitor] Waiting for services to be ready...", file=sys.stderr)
    SERVICES = [
        ("Prometheus",  "http://localhost:9090/-/healthy",                    False),
        ("MLflow",      "http://localhost:5000/api/2.0/mlflow/experiments/list", True),
        ("Grafana",     "http://localhost:3000/api/health",                   False),
        ("NodeExporter","http://localhost:9100/metrics",                      True),
    ]
    deadline = time.time() + 60
    remaining = list(SERVICES)
    healthy, unhealthy = [], []

    while remaining and time.time() < deadline:
        still_waiting = []
        for name, url, accept_any in remaining:
            try:
                urllib.request.urlopen(url, timeout=5)
                healthy.append(name)
            except urllib.error.HTTPError as e:
                if accept_any or e.code < 500:
                    healthy.append(name)
                else:
                    still_waiting.append((name, url, accept_any))
            except Exception:
                still_waiting.append((name, url, accept_any))
        remaining = still_waiting
        if remaining:
            time.sleep(3)

    # Anything still not reachable after deadline
    unhealthy = [name for name, _, _ in remaining]

    if unhealthy and not healthy:
        steps.append({
            "step":    "monitor",
            "status":  "warning",
            "message": f"no services reachable — are they running? ({', '.join(unhealthy)})"
        })
    elif unhealthy:
        steps.append({
            "step":    "monitor",
            "status":  "warning",
            "message": f"healthy: {', '.join(healthy)} | unreachable: {', '.join(unhealthy)}"
        })
    else:
        steps.append({
            "step":    "monitor",
            "status":  "ok",
            "message": f"all healthy — {', '.join(healthy)}"
        })

    return jsonify({"status": "success", "steps": steps})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)