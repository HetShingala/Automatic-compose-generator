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
    """
    Given a list of 'host:container' strings, return YAML lines
    for the volumes block in docker-compose.
    """
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
    """Return default image and port for a given stack."""
    cfg = STACK_CONFIGS.get(stack, STACK_CONFIGS["python"])
    return {
        "default_image": cfg["default_image"],
        "default_port":  cfg["default_port"],
    }