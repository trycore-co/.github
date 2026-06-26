#!/usr/bin/env python3
"""
Capa 1 — PR Gate: Verificación determinista de cobertura documental.
Plantilla para stack Python / FastAPI.

CÓMO ADAPTAR A UN NUEVO PROYECTO:
  1. Ajustar CODE_ZONES y DOC_ZONES en las primeras líneas (o dejar que las tome del env).
  2. Ajustar ROUTER_PATTERN si el proyecto usa otro directorio de endpoints
     (ej. "src/routes/" para Node, "src/main/java/" para Java → cambiar el regex).
  3. Ajustar los mensajes de las reglas R1/R2/R3 para mencionar los archivos
     correctos del proyecto (en lugar de "app/routers/", "docs/04-historias/", etc.).
  4. No cambiar la firma de main() ni el exit code — el reusable espera exit 1 para ERROR.

INVOCACIÓN por el reusable:
  python scripts/ci/docs-coverage-check.py

ENV VARS consumidas:
  CODE_ZONES      Prefijos de código separados por coma (default: "app/")
  DOC_ZONES       Prefijos de docs separados por coma  (default: "docs/")
  GITHUB_BASE_REF Rama base del PR (ej. "develop") — lo inyecta GitHub Actions
  GITHUB_STEP_SUMMARY  Ruta al archivo de resumen — lo inyecta GitHub Actions

SALIDA:
  - Annotations ::error / ::warning en stdout (las recoge GitHub)
  - Texto append al GITHUB_STEP_SUMMARY (aparece en la pestaña Summary del PR)
  - Exit 1 si hay al menos un ERROR, exit 0 si solo hay WARNINGs o nada
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Zonas del proyecto ────────────────────────────────────────────────────────
# Ajustar aquí o pasar por env vars desde el workflow wrapper:
#   code_zones: 'app/'          → Python/FastAPI
#   code_zones: 'src/main/'     → Java/Maven
#   code_zones: 'src/'          → Node.js
#   doc_zones:  'docs/'         → estándar Trycore
#   doc_zones:  'docs/,openspec/' → si hay specs separadas

_code_env = os.environ.get("CODE_ZONES", "app/")
_doc_env  = os.environ.get("DOC_ZONES",  "docs/")
CODE_ZONES = tuple(z.strip() for z in _code_env.split(",") if z.strip())
DOC_ZONES  = tuple(z.strip() for z in _doc_env.split(",")  if z.strip())

# Patrón de "nuevo endpoint": ajustar si el proyecto no usa FastAPI routers.
# FastAPI: app/routers/*.py
# Express: src/routes/*.js  → cambiar a rf"^{re.escape(_code_root)}routes/[^/]+\\.js$"
# Java:    src/main/java/**/*Resource.java → cambiar a rf".*Resource\\.java$"
_code_root = CODE_ZONES[0] if CODE_ZONES else "app/"
ROUTER_PATTERN = re.compile(rf"^{re.escape(_code_root)}routers/[^/]+\.py$")


@dataclass
class Finding:
    severity: str   # "ERROR" | "WARNING"
    rule: str
    message: str
    files: list[str] = field(default_factory=list)


def get_changed_files() -> list[str]:
    base = os.environ.get("GITHUB_BASE_REF", "develop")
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base}...HEAD"],
            capture_output=True, text=True, check=True, cwd=BASE_DIR,
        )
        return [f for f in result.stdout.strip().split("\n") if f]
    except subprocess.CalledProcessError:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1...HEAD"],
            capture_output=True, text=True, cwd=BASE_DIR,
        )
        return [f for f in result.stdout.strip().split("\n") if f]


def get_added_files() -> set[str]:
    base = os.environ.get("GITHUB_BASE_REF", "develop")
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=A", f"origin/{base}...HEAD"],
            capture_output=True, text=True, cwd=BASE_DIR,
        )
        return {f for f in result.stdout.strip().split("\n") if f}
    except Exception:
        return set()


def classify(files: list[str]) -> dict:
    zones: dict[str, list[str]] = {
        "code": [], "docs": [], "new_routers": [], "other": [],
    }
    added = get_added_files()
    for f in files:
        if any(f.startswith(z) for z in CODE_ZONES):
            zones["code"].append(f)
            if ROUTER_PATTERN.match(f) and f in added:
                zones["new_routers"].append(f)
        if any(f.startswith(z) for z in DOC_ZONES):
            zones["docs"].append(f)
        if not any(f.startswith(z) for z in CODE_ZONES + DOC_ZONES):
            zones["other"].append(f)
    return zones


def apply_rules(zones: dict) -> list[Finding]:
    findings: list[Finding] = []

    # R1 — código sin docs
    # Ajustar el mensaje para mencionar las carpetas correctas del proyecto.
    if zones["code"] and not zones["docs"]:
        findings.append(Finding(
            severity="ERROR",
            rule="R1",
            message=(
                "Se modificó código de la aplicación pero no se actualizó ningún archivo en docs/. "
                "Cada cambio de comportamiento debe quedar documentado."
            ),
            files=zones["code"][:5],
        ))

    # R2 — nuevo endpoint/router sin docs
    # Ajustar el mensaje para mencionar qué tipo de archivo es "nuevo endpoint" en este stack.
    if zones["new_routers"] and not zones["docs"]:
        findings.append(Finding(
            severity="ERROR",
            rule="R2",
            message=(
                "Se agregó un nuevo router pero no hay cambios en docs/. "
                "Un router nuevo es una integración nueva — documéntala."
            ),
            files=zones["new_routers"],
        ))

    # R3 — solo docs sin código (warning)
    if zones["docs"] and not zones["code"]:
        findings.append(Finding(
            severity="WARNING",
            rule="R3",
            message=(
                "PR contiene solo cambios de documentación sin código asociado. "
                "Verificar que no sea una actualización de doc que olvidó incluir el código."
            ),
            files=zones["docs"][:3],
        ))

    return findings


def emit_github_annotations(findings: list[Finding]) -> None:
    for f in findings:
        level = "error" if f.severity == "ERROR" else "warning"
        detail = ", ".join(f.files) if f.files else ""
        print(f"::{level} title=[{f.rule}] Doc Coverage::{f.message} | Archivos: {detail}")


def write_step_summary(zones: dict, findings: list[Finding]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    errors   = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARNING"]

    if errors:
        icon, titulo, bajada = (
            "🔴",
            "Necesitamos actualizar los docs antes de continuar",
            "Este PR toca código de la aplicación, pero la documentación no refleja esos cambios todavía. "
            "Actualiza los archivos indicados y vuelve a hacer push — el check se re-ejecuta automáticamente.",
        )
    elif warnings:
        icon, titulo, bajada = (
            "🟡",
            "Todo bien — solo una nota para el equipo",
            "No hay nada bloqueante. El aviso de abajo es informativo.",
        )
    else:
        icon, titulo, bajada = (
            "🟢",
            "Documentación al día ✓",
            "El PR incluye tanto el código como su documentación correspondiente. ¡Buen trabajo!",
        )

    lines = [
        f"## {icon} Doc Coverage — {titulo}",
        "",
        f"_{bajada}_",
        "",
        "### ¿Qué tocó este PR?",
        "",
        "| Zona | Archivos |",
        "|------|----------|",
        f"| Código (`{CODE_ZONES[0]}`) | {len(zones['code'])} |",
        f"| Documentación (`{DOC_ZONES[0]}`) | {len(zones['docs'])} |",
        f"| Endpoints nuevos | {len(zones['new_routers'])} |",
        "",
    ]

    if findings:
        lines.append("### Lo que encontramos")
        lines.append("")
        for f in findings:
            bullet = "❌" if f.severity == "ERROR" else "💡"
            label  = "Acción requerida" if f.severity == "ERROR" else "Para tener en cuenta"
            lines.append(f"**{bullet} {label}** — {f.message}")
            if f.files:
                for path in f.files[:3]:
                    lines.append(f"- `{path}`")
            lines.append("")
    else:
        lines.append("_Sin observaciones. El PR puede proceder._")

    with open(summary_path, "a") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    print("── Doc Coverage Check (Capa 1) ──────────────────────────────")
    files = get_changed_files()

    if not files or files == [""]:
        print("Sin archivos cambiados detectados. Nada que verificar.")
        return 0

    print(f"Archivos en diff: {len(files)}")
    zones = classify(files)
    findings = apply_rules(zones)

    emit_github_annotations(findings)
    write_step_summary(zones, findings)

    errors   = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARNING"]

    if findings:
        print(f"\nHallazgos: {len(errors)} errores, {len(warnings)} advertencias")
        for f in findings:
            prefix = "  ERROR  " if f.severity == "ERROR" else "  WARN   "
            print(f"{prefix}[{f.rule}] {f.message}")
            for path in f.files[:3]:
                print(f"           → {path}")
    else:
        print("✓ Sin violaciones. Doc coverage OK.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
