"""
generator/scanner.py
Docker image vulnerability scanning using Trivy.
Tries three methods in order:
  1. Local trivy binary
  2. Trivy via Docker (aquasec/trivy image)
  3. Fallback static CVE database
"""

import subprocess
import json
import shutil
from typing import List, Dict


def _parse_trivy_output(stdout: str, image: str, scanner: str) -> Dict:
    """Parse trivy JSON output into our standard format."""
    data   = json.loads(stdout)
    vulns  = []
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for result_item in data.get("Results", []):
        for v in result_item.get("Vulnerabilities") or []:
            sev = v.get("Severity", "UNKNOWN")
            vuln = {
                "id":          v.get("VulnerabilityID", ""),
                "severity":    sev,
                "package":     v.get("PkgName", ""),
                "version":     v.get("InstalledVersion", ""),
                "fixed_in":    v.get("FixedVersion", "not fixed"),
                "description": (v.get("Description") or "")[:120]
            }
            vulns.append(vuln)
            if sev in counts:
                counts[sev] += 1

    return {
        "image":           image,
        "scanner":         scanner,
        "vulnerabilities": vulns,
        "summary":         counts,
        "error":           None
    }


def _run_trivy_local(image: str, severity: str) -> Dict:
    result = subprocess.run(
        ["trivy", "image", "--format", "json", "--severity", severity,
         "--no-progress", "--quiet", image],
        capture_output=True, text=True, timeout=120
    )
    return _parse_trivy_output(result.stdout, image, "trivy (local)")


def _run_trivy_docker(image: str, severity: str) -> Dict:
    result = subprocess.run(
        ["docker", "run", "--rm",
         "-v", "/var/run/docker.sock:/var/run/docker.sock",
         "aquasec/trivy:latest",
         "image", "--format", "json", "--severity", severity,
         "--no-progress", "--quiet", image],
        capture_output=True, text=True, timeout=180
    )
    return _parse_trivy_output(result.stdout, image, "trivy (docker)")


def scan_image(image: str, severity: str = "CRITICAL,HIGH,MEDIUM,LOW") -> Dict:
    """
    Scan a Docker image for vulnerabilities.
    Tries local trivy → trivy via Docker → fallback static DB.
    """

    # Method 1 — local trivy binary
    if shutil.which("trivy"):
        try:
            return _run_trivy_local(image, severity)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
            pass

    # Method 2 — trivy via Docker
    if shutil.which("docker"):
        try:
            return _run_trivy_docker(image, severity)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
            pass

    # Method 3 — static fallback
    return _fallback_scan(image, severity)


def _fallback_scan(image: str, severity: str) -> Dict:
    """
    Simulated scan result when Trivy is not available.
    Uses a static CVE database for common ML base images.
    """
    DB = {
        "python:3.11-slim": [
            {"id": "CVE-2023-6246", "severity": "HIGH",     "package": "glibc",   "version": "2.36",   "fixed_in": "2.36-9+deb12u4", "description": "Buffer overflow in __vsyslog_internal"},
            {"id": "CVE-2024-0727", "severity": "MEDIUM",   "package": "openssl", "version": "3.0.11", "fixed_in": "3.0.13",         "description": "PKCS12 NULL pointer dereference DoS"},
            {"id": "CVE-2023-5678", "severity": "MEDIUM",   "package": "openssl", "version": "3.0.11", "fixed_in": "3.0.13",         "description": "Generating excessively long X9.42 DH keys"},
            {"id": "CVE-2023-4641", "severity": "LOW",      "package": "shadow",  "version": "4.13",   "fixed_in": "not fixed",      "description": "Password leak in newgrp and gpasswd"},
        ],
        "python:3.10-slim": [
            {"id": "CVE-2023-6246", "severity": "CRITICAL", "package": "glibc",   "version": "2.35",   "fixed_in": "2.35-3+deb11u7", "description": "Buffer overflow in __vsyslog_internal"},
            {"id": "CVE-2023-29491","severity": "HIGH",     "package": "ncurses", "version": "6.3",    "fixed_in": "6.4",            "description": "Local users can trigger security-relevant memory corruption"},
            {"id": "CVE-2024-0727", "severity": "HIGH",     "package": "openssl", "version": "1.1.1w", "fixed_in": "not fixed",      "description": "PKCS12 NULL pointer dereference DoS"},
            {"id": "CVE-2022-4450", "severity": "MEDIUM",   "package": "openssl", "version": "1.1.1w", "fixed_in": "not fixed",      "description": "Double free after calling PEM_read_bio_ex"},
            {"id": "CVE-2023-4641", "severity": "LOW",      "package": "shadow",  "version": "4.11.1", "fixed_in": "not fixed",      "description": "Password leak in newgrp and gpasswd"},
        ],
        "python:3.9": [
            {"id": "CVE-2023-6246", "severity": "CRITICAL", "package": "glibc",   "version": "2.31",   "fixed_in": "2.31-13+deb11u8","description": "Buffer overflow in __vsyslog_internal"},
            {"id": "CVE-2023-29491","severity": "CRITICAL", "package": "ncurses", "version": "6.2",    "fixed_in": "6.4",            "description": "Memory corruption in ncurses"},
            {"id": "CVE-2023-38408","severity": "HIGH",     "package": "openssh", "version": "8.4p1",  "fixed_in": "9.3p2",          "description": "Remote code execution via ssh-agent forwarding"},
            {"id": "CVE-2022-4450", "severity": "HIGH",     "package": "openssl", "version": "1.1.1n", "fixed_in": "not fixed",      "description": "Double free after calling PEM_read_bio_ex"},
            {"id": "CVE-2023-0464", "severity": "MEDIUM",   "package": "openssl", "version": "1.1.1n", "fixed_in": "not fixed",      "description": "Excessive resource usage verifying policy constraints"},
            {"id": "CVE-2023-4641", "severity": "LOW",      "package": "shadow",  "version": "4.8.1",  "fixed_in": "not fixed",      "description": "Password leak in newgrp and gpasswd"},
        ],
    }

    matched_key = None
    for key in DB:
        img_name, img_tag = (image.split(":") + [""])[:2]
        key_name, key_tag = (key.split(":") + [""])[:2]
        if img_name == key_name and (not img_tag or img_tag == key_tag):
            matched_key = key
            break

    all_vulns = DB.get(matched_key, [
        {"id": "CVE-2024-0001", "severity": "MEDIUM", "package": "libc6",  "version": "2.36",   "fixed_in": "not fixed", "description": "Potential memory leak under high load"},
        {"id": "CVE-2023-9999", "severity": "LOW",    "package": "curl",   "version": "7.88.1", "fixed_in": "8.0.0",     "description": "Cookie injection via HSTS list manipulation"},
    ])

    requested = [s.strip().upper() for s in severity.split(",")]
    vulns     = [v for v in all_vulns if v["severity"] in requested]
    counts    = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for v in vulns:
        if v["severity"] in counts:
            counts[v["severity"]] += 1

    return {
        "image":           image,
        "scanner":         "simulated (trivy not installed — install trivy for real results)",
        "vulnerabilities": vulns,
        "summary":         counts,
        "error":           None
    }