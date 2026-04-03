"""
Core generator logic.
Takes form inputs and produces Dockerfile + docker-compose.yml content.
Supports multiple project stacks: Python, Node.js, PHP/Laravel, Ruby, Go.
"""

STACK_CONFIGS = {
    "python": {
        "copy_deps":     "COPY requirements.txt .",
        "install_deps":  "RUN pip install --no-cache-dir -r requirements.txt",
        "default_image": "python:3.11-slim",
        "default_port":  "8080",
    },
    "node": {
        "copy_deps":     "COPY package*.json .",
        "install_deps":  "RUN npm install --production",
        "default_image": "node:20-slim",
        "default_port":  "3000",
    },
    "php": {
        "copy_deps":     "COPY composer.json composer.lock .",
        "install_deps":  "RUN composer install --no-dev --optimize-autoloader",
        "default_image": "php:8.2-fpm",
        "default_port":  "9000",
    },
    "ruby": {
        "copy_deps":     "COPY Gemfile Gemfile.lock .",
        "install_deps":  "RUN bundle install --without development test",
        "default_image": "ruby:3.2-slim",
        "default_port":  "3000",
    },
    "go": {
        "copy_deps":     "COPY go.mod go.sum .",
        "install_deps":  "RUN go mod download",
        "default_image": "golang:1.21-alpine",
        "default_port":  "8080",
    },
}


def generate_dockerfile(base_image: str, port: str, stack: str = "python") -> str:
    cfg = STACK_CONFIGS.get(stack, STACK_CONFIGS["python"])
    return f"""FROM {base_image}

WORKDIR /app

{cfg["copy_deps"]}
{cfg["install_deps"]}

COPY . .

RUN chmod +x ./entrypoint.sh

EXPOSE {port}

ENTRYPOINT ["./entrypoint.sh"]
"""


def format_volumes(volumes: list) -> str:
    lines = []
    for v in volumes:
        if ":" not in v:
            continue
        host, container = v.split(":", 1)
        lines.append(f"      - {host.strip()}:{container.strip()}")
    return "\n".join(lines)


def format_env_vars(env_vars: dict) -> str:
    if not env_vars:
        return ""
    lines = ["    environment:"]
    for k, v in env_vars.items():
        lines.append(f"      - {k}={v}")
    return "\n".join(lines)


def generate_compose(service_name: str, port: str, env_vars: dict, volumes: list) -> str:
    env_block  = format_env_vars(env_vars)
    vol_lines  = format_volumes(volumes)
    volumes_block = f"    volumes:\n{vol_lines}" if vol_lines else ""

    optional_blocks = "\n".join(filter(None, [env_block, volumes_block]))
    if optional_blocks:
        optional_blocks = "\n" + optional_blocks

    return f"""version: "3.9"

services:
  {service_name}:
    build: .
    ports:
      - "{port}:{port}"{optional_blocks}
"""


def get_stack_defaults(stack: str) -> dict:
    cfg = STACK_CONFIGS.get(stack, STACK_CONFIGS["python"])
    return {
        "default_image": cfg["default_image"],
        "default_port":  cfg["default_port"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-service generation  ← NEW
# ─────────────────────────────────────────────────────────────────────────────

def generate_dockerfile_for_service(svc: dict) -> str:
    """
    Generate a Dockerfile for one build-type service card.
      svc['stack']      — python/node/php/ruby/go  (default: python)
      svc['base_image'] — FROM line; blank → stack default
      svc['ports']      — list of "host:container"; first used for EXPOSE
    """
    stack      = (svc.get("stack") or "python").strip()
    base_image = (svc.get("base_image") or "").strip()
    cfg        = STACK_CONFIGS.get(stack, STACK_CONFIGS["python"])

    if not base_image:
        base_image = cfg["default_image"]

    ports = svc.get("ports") or []
    port  = "8080"
    if ports:
        first = str(ports[0]).strip()
        port  = first.split(":")[-1] if ":" in first else first

    return f"""FROM {base_image}

WORKDIR /app

{cfg["copy_deps"]}
{cfg["install_deps"]}

COPY . .

RUN chmod +x ./entrypoint.sh

EXPOSE {port}

ENTRYPOINT ["./entrypoint.sh"]
"""


def _build_service_block(svc: dict, build_ctx: str = None) -> str:
    """
    Render the indented body of one service entry in docker-compose.yml.
    build_ctx overrides svc['build'] (used to point a build service at its
    own subfolder inside the zip).
    """
    lines = []

    # source
    if svc.get("type") == "build":
        ctx = build_ctx or (svc.get("build") or ".") or "."
        lines.append(f"    build: {ctx}")
    else:
        img = (svc.get("image") or "").strip()
        if img:
            lines.append(f"    image: {img}")

    # ports
    ports = [str(x).strip() for x in (svc.get("ports") or []) if str(x).strip()]
    if ports:
        lines.append("    ports:")
        for p in ports:
            lines.append(f'      - "{p}"')

    # volumes
    vols = [str(x).strip() for x in (svc.get("volumes") or []) if str(x).strip()]
    if vols:
        lines.append("    volumes:")
        for v in vols:
            lines.append(f"      - {v}")

    # environment
    envs = [str(x).strip() for x in (svc.get("environment") or []) if str(x).strip()]
    if envs:
        lines.append("    environment:")
        for e in envs:
            lines.append(f"      - {e}")

    # command — multiline becomes block scalar with >
    cmd = (svc.get("command") or "").strip()
    if cmd:
        cmd_lines = [l.strip() for l in cmd.splitlines() if l.strip()]
        if len(cmd_lines) == 1:
            lines.append(f"    command: {cmd_lines[0]}")
        else:
            lines.append("    command: >")
            for cl in cmd_lines:
                lines.append(f"      {cl}")

    # depends_on
    deps = [str(x).strip() for x in (svc.get("depends_on") or []) if str(x).strip()]
    if deps:
        lines.append("    depends_on:")
        for d in deps:
            lines.append(f"      - {d}")

    # restart
    restart = (svc.get("restart") or "").strip()
    if restart:
        lines.append(f"    restart: {restart}")

    # networks
    nets = [str(x).strip() for x in (svc.get("networks") or []) if str(x).strip()]
    if nets:
        lines.append("    networks:")
        for n in nets:
            lines.append(f"      - {n}")

    # healthcheck
    hc = svc.get("healthcheck") or {}
    if (hc.get("test") or "").strip():
        lines.append("    healthcheck:")
        test_val = hc["test"].strip()
        if test_val.startswith("["):
            lines.append(f"      test: {test_val}")
        else:
            lines.append(f'      test: ["CMD-SHELL", "{test_val}"]')
        for key in ("interval", "timeout", "retries", "start_period"):
            if hc.get(key):
                lines.append(f"      {key}: {hc[key]}")

    return "\n".join(lines)


def generate_compose_multi(
    services: list,
    named_volumes: list = None,
    named_networks: list = None,
    build_ctx_overrides: dict = None,
) -> str:
    """
    Build a complete docker-compose.yml from a list of service dicts.

    named_volumes:       ["grafana_data", "pgdata", ...]
    named_networks:      ["app-net", "monitoring", ...]
    build_ctx_overrides: {"service-name": "./service-name"}
    """
    overrides = build_ctx_overrides or {}
    parts = ["services:"]

    for svc in services:
        name  = (svc.get("name") or "service").strip()
        block = _build_service_block(svc, build_ctx=overrides.get(name))
        parts.append(f"  {name}:")
        parts.append(block)
        parts.append("")

    named = [str(v).strip() for v in (named_volumes or []) if str(v).strip()]
    if named:
        parts.append("volumes:")
        for v in named:
            parts.append(f"  {v}:")

    named_nets = [str(n).strip() for n in (named_networks or []) if str(n).strip()]
    if named_nets:
        parts.append("networks:")
        for n in named_nets:
            parts.append(f"  {n}:")

    return "\n".join(parts).rstrip() + "\n"