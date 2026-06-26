#!/usr/bin/env python3
"""
Capa 3 — Scheduled Audit: Barrido completo trimestral docs↔código.
Plantilla para stack Python / FastAPI.

CÓMO ADAPTAR A UN NUEVO PROYECTO:
  1. Ajustar check_hu_traceability() para apuntar a la carpeta de HUs del proyecto
     (en esta plantilla: docs/04-historias/).
  2. Ajustar check_router_coverage() para apuntar a los "endpoints" del stack:
     - FastAPI:  app/routers/*.py
     - Express:  src/routes/*.js    → cambiar ls_files("app/routers/") a ls_files("src/routes/")
     - Java:     src/main/java/**/*Resource.java → cambiar el ls_files y el grep
  3. Ajustar el prompt de Claude para describir el stack real del proyecto.
  4. No cambiar el nombre del artefacto ni el esquema JSON de salida
     (scripts/ci/last-scheduled-audit.json, SIN punto inicial).

INVOCACIÓN por el reusable:
  python scripts/ci/scheduled-audit.py

ENV VARS consumidas:
  ANTHROPIC_API_KEY     — clave de API Anthropic (org-level, heredada con secrets: inherit)
  GITHUB_TOKEN          — provisto automáticamente por GitHub Actions
  GITHUB_REPOSITORY     — "owner/repo" provisto por GitHub Actions
  AUDIT_SCOPE           — "all" | "hus-only" | "routers-only" (default: "all")
                          Agregar opciones propias del proyecto si aplica.

ARCHIVO GENERADO:
  scripts/ci/last-scheduled-audit.json     ← SIN punto inicial (importante)
  Esquema:
  {
    "hus": [
      {"hu": "docs/04-historias/HU-001.md",
       "estado": "implementada|parcial|no_implementada|error_análisis",
       "evidencia": "app/routers/...",
       "accion": "ninguna|completar_impl|investigar"}
    ],
    "routers": [
      {"router": "app/routers/linkedin.py",
       "estado": "documentado|sin_doc|parcial",
       "doc_relacionada": "docs/...",
       "accion": "ninguna|crear_doc|actualizar_doc"}
    ]
  }

SALIDA:
  - GITHUB_STEP_SUMMARY: tabla con conteos y estado 🟢/🟡/🔴
  - GitHub Issue con labels "knowledge-audit", "quarterly", "automated" si hay drift
  - Exit 0 siempre (no bloquea el pipeline)
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent.parent
MODEL       = "claude-sonnet-4-6"
MAX_CONTENT = 8_000


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR).stdout.strip()


def ls_files(pattern: str) -> list[str]:
    out = run(["git", "ls-files", pattern])
    return [f for f in out.split("\n") if f]


def read_file(path: str, max_chars: int = MAX_CONTENT) -> str:
    full = BASE_DIR / path
    if not full.exists():
        return f"(archivo no encontrado: {path})"
    return full.read_text(encoding="utf-8", errors="replace")[:max_chars]


def call_claude(prompt: str, api_key: str, max_tokens: int = 2048) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["content"][0]["text"].strip()


# ── Check A: HU trazabilidad ──────────────────────────────────────────────────
# ADAPTAR: cambiar "docs/04-historias/" si el proyecto usa otra carpeta de HUs.
# ADAPTAR: cambiar las rutas en _grep_hu_evidence() para que busquen en las
#          carpetas de código correctas del proyecto.

def _grep_hu_evidence(hu_id: str, keywords: list[str]) -> str:
    result = run(["git", "grep", "-rl", "--ignore-case", hu_id, "--", "app/"])
    if result:
        return f"Código con referencia directa: {result.split(chr(10))[0]}"
    # ADAPTAR: cambiar "app/routers/", "app/scrapers/", "app/services/" a las
    #          carpetas de código del proyecto.
    for kw in keywords[:3]:
        if len(kw) < 4:
            continue
        result = run(["git", "grep", "-rl", "--ignore-case", kw, "--", "app/routers/", "app/scrapers/", "app/services/"])
        if result:
            return f"Código relacionado ({kw}): {result.split(chr(10))[0]}"
    return ""


def _extract_keywords(hu_path: str) -> list[str]:
    name = hu_path.split("/")[-1].replace(".md", "")
    parts = re.split(r"[-_]", name)[2:]
    return [p for p in parts if len(p) > 3]


def check_hu_traceability(api_key: str) -> list[dict]:
    # ADAPTAR: cambiar "docs/04-historias/" si el proyecto usa otra estructura.
    hu_files = ls_files("docs/04-historias/")
    recent = run(["git", "log", "--since=90 days ago", "--name-only", "--pretty=format:", "--", "docs/04-historias/"])
    recent_set = set(f for f in recent.split("\n") if f.startswith("docs/04-historias/"))

    findings = []
    ambiguous = []

    for hu_path in hu_files:
        match = re.search(r"HU-(\d+)", hu_path)
        if not match:
            continue
        hu_id    = f"HU-{match.group(1)}"
        keywords = _extract_keywords(hu_path)
        evidence = _grep_hu_evidence(hu_id, keywords)

        if evidence:
            findings.append({"hu": hu_path, "estado": "implementada", "evidencia": evidence, "accion": "ninguna"})
        elif hu_path in recent_set:
            ambiguous.append(hu_path)
        else:
            findings.append({"hu": hu_path, "estado": "parcial", "evidencia": "Sin referencia directa en app/", "accion": "verificar_manualmente"})

    # Claude solo para HUs recientes sin evidencia (máx 10)
    for i in range(0, min(len(ambiguous), 10), 3):
        batch = ambiguous[i:i+3]
        batch_content = "\n\n".join(f"=== {f} ===\n{read_file(f, 600)}" for f in batch)
        app_files = run(["git", "ls-files", "app/"])
        # ADAPTAR: ajustar la descripción del microservicio en el prompt.
        prompt = f"""Auditor de trazabilidad para microservicio Python/FastAPI.
Ajustar esta descripción al stack real del proyecto.

HISTORIAS DE USUARIO recientes:
{batch_content}

ARCHIVOS EN app/:
{app_files[:2000]}

¿Estas HUs tienen código en app/ que las implemente?
Responde SOLO con array JSON:
[{{"hu": "ruta/HU-XXX.md", "estado": "implementada"|"parcial"|"no_implementada",
   "evidencia": "archivo o módulo concreto", "accion": "ninguna"|"completar_impl"}}]
"""
        try:
            raw = call_claude(prompt, api_key, max_tokens=600)
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            findings.extend(json.loads(raw))
        except Exception as exc:
            for f in batch:
                findings.append({"hu": f, "estado": "error_análisis", "evidencia": str(exc)[:80], "accion": "investigar"})

    return findings


# ── Check B: Cobertura de endpoints ──────────────────────────────────────────
# ADAPTAR: cambiar ls_files("app/routers/") al directorio de endpoints del stack.
# ADAPTAR: ajustar el prompt si el patrón de nombre de endpoints es distinto.

def check_router_coverage(api_key: str) -> list[dict]:
    # ADAPTAR: cambiar "app/routers/" al directorio de endpoints del proyecto.
    router_files = ls_files("app/routers/")
    doc_files    = run(["git", "ls-files", "docs/"]).split("\n")

    # ADAPTAR: ajustar la descripción del stack en el prompt.
    prompt = f"""Auditor de cobertura documental para microservicio Python/FastAPI.
Ajustar esta descripción al stack real del proyecto.

ENDPOINTS IMPLEMENTADOS (app/routers/):
{chr(10).join(router_files)}

ARCHIVOS DE DOCUMENTACIÓN (docs/):
{chr(10).join(doc_files[:60])}

Para cada endpoint, determina si existe documentación que lo describa.
Responde SOLO con array JSON:
[
  {{
    "router": "app/routers/nombre.py",
    "estado": "documentado" | "sin_doc" | "parcial",
    "doc_relacionada": "ruta/archivo.md o vacío",
    "accion": "ninguna" | "crear_doc" | "actualizar_doc"
  }}
]
"""
    try:
        raw = call_claude(prompt, api_key, max_tokens=1000)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        return [{"router": "error", "estado": "error_análisis", "doc_relacionada": "", "accion": str(exc)[:80]}]


# ── GitHub Issue ──────────────────────────────────────────────────────────────

def create_issue(title: str, body: str, token: str, repo: str) -> str:
    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": ["knowledge-audit", "quarterly", "automated"],
    }).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp).get("html_url", "")
    except urllib.error.HTTPError as exc:
        print(f"  WARN: Issue no creado: {exc.code}")
        return ""


def format_report(hus: list, routers: list) -> tuple[str, str]:
    hu_issues     = [h for h in hus if h.get("estado") not in ("implementada",)]
    router_issues = [r for r in routers if r.get("estado") == "sin_doc"]
    total         = len(hu_issues) + len(router_issues)
    title         = f"[Knowledge Audit Trimestral] {total} items de drift detectados"

    sections = []

    if hu_issues:
        rows = [
            f"| `{h['hu'].split('/')[-1]}` | {h['estado']} | {h['evidencia'][:60]} | {h['accion']} |"
            for h in hu_issues
        ]
        sections.append(
            "## HUs sin implementación completa\n"
            "| HU | Estado | Evidencia | Acción |\n"
            "|----|--------|-----------|--------|\n" + "\n".join(rows)
        )

    if router_issues:
        rows = [
            f"| `{r['router'].split('/')[-1]}` | {r['estado']} | {r.get('doc_relacionada','')[:50]} | {r['accion']} |"
            for r in router_issues
        ]
        sections.append(
            "## Endpoints sin documentación\n"
            "| Endpoint | Estado | Doc encontrada | Acción |\n"
            "|----------|--------|----------------|--------|\n" + "\n".join(rows)
        )

    body = "\n\n".join(sections) if sections else "_No se detectó drift significativo._"
    body += "\n\n---\n_Generado por `scheduled-audit.py` (Capa 3 — Código como Conocimiento)._"
    return title, body


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    api_key  = os.environ.get("ANTHROPIC_API_KEY", "")
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    gh_repo  = os.environ.get("GITHUB_REPOSITORY", "")
    scope    = os.environ.get("AUDIT_SCOPE", "all")

    print("── Scheduled Audit (Capa 3) ─────────────────────────────────")

    if not api_key:
        print("ANTHROPIC_API_KEY no configurada. Saliendo.")
        return 1

    hus     = []
    routers = []

    if scope in ("all", "hus-only"):
        print("Check A: HU trazabilidad...")
        hus = check_hu_traceability(api_key)
        hu_issues = [h for h in hus if h.get("estado") != "implementada"]
        print(f"  HUs analizadas: {len(hus)}  Con observaciones: {len(hu_issues)}")

    if scope in ("all", "routers-only"):
        print("Check B: Cobertura de endpoints...")
        routers = check_router_coverage(api_key)
        router_issues = [r for r in routers if r.get("estado") == "sin_doc"]
        print(f"  Endpoints analizados: {len(routers)}  Sin docs: {len(router_issues)}")

    hu_issues     = [h for h in hus if h.get("estado") not in ("implementada",)]
    router_issues = [r for r in routers if r.get("estado") == "sin_doc"]
    total         = len(hu_issues) + len(router_issues)
    print(f"\nTotal items de drift: {total}")

    # ── Artefacto — IMPORTANTE: sin punto inicial en el nombre del archivo ────
    # actions/upload-artifact ignora archivos ocultos (los que empiezan con ".").
    # El nombre DEBE ser "last-scheduled-audit.json", no ".last-scheduled-audit.json".
    report = {"hus": hus, "routers": routers}
    report_path = BASE_DIR / "scripts" / "ci" / "last-scheduled-audit.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        icon = "🔴" if total > 5 else ("🟡" if total > 0 else "🟢")
        if total == 0:
            titulo = "Todo el conocimiento está vigente y trazado ✓"
            bajada = "Revisamos HUs y endpoints. Todo lo documentado tiene código que lo respalda."
        elif total <= 5:
            titulo = f"{total} item(s) necesitan atención del equipo"
            bajada = "Hay algunas discrepancias menores. Se abrirá un issue con el detalle."
        else:
            titulo = f"{total} items con drift — revisar antes del próximo release"
            bajada = "Hay una brecha significativa entre lo documentado y lo implementado."

        with open(summary_path, "a") as fh:
            fh.write(f"\n## {icon} Auditoría trimestral — {titulo}\n\n")
            fh.write(f"_{bajada}_\n\n")
            fh.write("| Qué revisamos | Cantidad | Requieren atención |\n")
            fh.write("|---------------|----------|--------------------|\n")
            fh.write(f"| Historias de Usuario | {len(hus)} | {len(hu_issues)} |\n")
            fh.write(f"| Endpoints de integración | {len(routers)} | {len(router_issues)} |\n")
            if total > 0:
                fh.write(f"\n> 🎫 Se creó un issue automático con el detalle de cada item.\n")

    if total > 0 and gh_token and gh_repo:
        title, body = format_report(hus, routers)
        url = create_issue(title, body, gh_token, gh_repo)
        print(f"Issue creado: {url}")

    return 0  # Capa 3 nunca bloquea el pipeline


if __name__ == "__main__":
    sys.exit(main())
