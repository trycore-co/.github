#!/usr/bin/env python3
"""
Capa 2 — Merge Audit: Análisis de coherencia docs↔código en cada merge a main.
Plantilla para stack Python / FastAPI.

CÓMO ADAPTAR A UN NUEVO PROYECTO:
  1. Ajustar CODE_ZONES y DOC_ZONES (líneas ~35-36) para que reflejen las
     carpetas reales de código y documentación del proyecto.
  2. Ajustar el prompt dentro de analyze_coherence() para describir
     el stack real del proyecto (qué hace, qué tecnologías usa).
  3. No cambiar la firma de main() ni el nombre del artefacto generado
     (scripts/ci/knowledge-snapshot.json) — el reusable espera ese path.

INVOCACIÓN por el reusable:
  python scripts/ci/merge-audit.py

ENV VARS consumidas:
  ANTHROPIC_API_KEY     — clave de API Anthropic (org-level, heredada con secrets: inherit)
  GITHUB_TOKEN          — provisto automáticamente por GitHub Actions
  GITHUB_REPOSITORY     — "owner/repo" provisto por GitHub Actions
  GITHUB_SHA            — SHA del commit, provisto por GitHub Actions
  DRY_RUN               — "true" para no crear issues (default: "false")
  MERGE_BASE_REF        — rama base para el diff (ej. "develop")

ARCHIVO GENERADO:
  scripts/ci/knowledge-snapshot.json
  Esquema: {"sha": "...", "total_files": N, "docs": ["docs/file.md", ...]}

SALIDA:
  - GITHUB_STEP_SUMMARY: resumen con estado 🟢/🟡/🔴 y hallazgos
  - GitHub Issue con label "knowledge-drift" si drift_critico=true
  - Exit 0 siempre (no bloquea el pipeline)
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR      = Path(__file__).resolve().parent.parent.parent
MAX_DIFF_CHARS = 12_000
MODEL          = "claude-haiku-4-5-20251001"

# ── Zonas del proyecto ────────────────────────────────────────────────────────
# Ajustar para cada proyecto:
#   Python/FastAPI:  CODE_ZONES = ("app/routers/", "app/scrapers/", "app/services/")
#   Java/Maven:      CODE_ZONES = ("src/main/java/",)
#   Node.js:         CODE_ZONES = ("src/",)
CODE_ZONES = ("app/routers/", "app/scrapers/", "app/services/")
DOC_ZONES  = ("docs/",)


# ── Helpers git ───────────────────────────────────────────────────────────────

def run(cmd: list[str], **kw) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR, **kw).stdout.strip()


def _merge_base_ref() -> str:
    explicit = os.environ.get("MERGE_BASE_REF", "")
    if explicit:
        run(["git", "fetch", "origin", explicit])
        return f"origin/{explicit}"
    return "HEAD^1"


def changed_files_in_merge() -> list[str]:
    base = _merge_base_ref()
    files = run(["git", "diff", "--name-only", base, "HEAD"])
    return [f for f in files.split("\n") if f]


def diff_for_file(path: str) -> str:
    base = _merge_base_ref()
    return run(["git", "diff", base, "HEAD", "--", path])[:MAX_DIFF_CHARS]


# ── Análisis con Claude ───────────────────────────────────────────────────────

def call_claude(prompt: str, api_key: str) -> dict:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1024,
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def analyze_coherence(code_diffs: str, doc_diffs: str, api_key: str) -> dict:
    # ADAPTAR: describe el stack del proyecto en la primera línea del prompt.
    # Ejemplo para un monolito Spring Boot:
    #   "Eres un auditor técnico. Merge a `main` de un monolito Spring Boot (JHipster)..."
    prompt = f"""Eres un auditor técnico. Se hizo un merge a la rama `main` de un microservicio
Python/FastAPI. Ajustar esta descripción al stack real del proyecto.

CAMBIOS DE CÓDIGO en este merge:
{code_diffs or "(ninguno)"}

CAMBIOS DE DOCUMENTACIÓN en este merge:
{doc_diffs or "(ninguno)"}

Analiza si los docs actualizados son coherentes con el código que llegó.
Responde SOLO con un objeto JSON con esta estructura exacta:
{{
  "coherencia": "ok" | "parcial" | "drift",
  "drift_critico": true | false,
  "hallazgos": [
    {{"tipo": "ok"|"warning"|"error", "descripcion": "...", "archivo": "..."}}
  ],
  "resumen": "Una frase de resumen para el título del issue si hay drift."
}}

Reglas:
- "ok": todo lo que cambió tiene doc coherente.
- "parcial": cambios de código sin doc correspondiente (warning).
- "drift": la doc actualizada contradice o es inconsistente con el código (error).
- drift_critico = true si hay al menos un hallazgo de tipo "error".
- Sé conciso en las descripciones (máx 100 chars por hallazgo).
"""
    try:
        resp = call_claude(prompt, api_key)
        content = resp["content"][0]["text"].strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as exc:
        return {
            "coherencia": "parcial",
            "drift_critico": False,
            "hallazgos": [{"tipo": "warning", "descripcion": f"Error al llamar Claude: {exc}", "archivo": "n/a"}],
            "resumen": "Error en análisis automático",
        }


# ── Knowledge snapshot ────────────────────────────────────────────────────────

def build_snapshot(sha: str) -> str:
    docs_files = run(["git", "ls-files", "docs/"]).split("\n")
    manifest = {
        "sha": sha,
        "total_files": len([f for f in docs_files if f]),
        "docs": sorted(f for f in docs_files if f),
    }
    snapshot_path = BASE_DIR / "scripts" / "ci" / "knowledge-snapshot.json"
    snapshot_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return json.dumps(manifest)


# ── GitHub Issue ──────────────────────────────────────────────────────────────

def create_github_issue(title: str, body: str, token: str, repo: str) -> str:
    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": ["knowledge-drift", "automated"],
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
        print(f"  WARN: No se pudo crear el issue: {exc.code} {exc.reason}")
        return ""


def format_issue_body(analysis: dict, sha: str, files: list[str]) -> str:
    hallazgos = "\n".join(
        f"- {'❌' if h['tipo']=='error' else '⚠️'} **{h['archivo']}**: {h['descripcion']}"
        for h in analysis.get("hallazgos", [])
    )
    return f"""## Drift documental detectado en merge `{sha[:8]}`

**Coherencia:** `{analysis['coherencia']}`

### Hallazgos
{hallazgos or "_Sin hallazgos detallados._"}

### Archivos del merge
{chr(10).join(f'- `{f}`' for f in files[:20])}

---
_Generado automáticamente por `merge-audit.py` (Capa 2 — Código como Conocimiento)._
_Revisar y cerrar este issue una vez que la documentación esté al día._
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    api_key  = os.environ.get("ANTHROPIC_API_KEY", "")
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    gh_repo  = os.environ.get("GITHUB_REPOSITORY", "")
    sha      = os.environ.get("GITHUB_SHA", run(["git", "rev-parse", "HEAD"]))
    dry_run  = os.environ.get("DRY_RUN", "false").lower() == "true"

    print("── Merge Audit (Capa 2) ─────────────────────────────────────")
    print(f"SHA: {sha[:8]}  dry_run: {dry_run}")

    files = changed_files_in_merge()
    print(f"Archivos en merge: {len(files)}")

    code_files = [f for f in files if any(f.startswith(z) for z in CODE_ZONES)]
    doc_files  = [f for f in files if any(f.startswith(z) for z in DOC_ZONES)]

    # Knowledge snapshot (siempre, aunque no haya API key)
    snapshot = build_snapshot(sha)
    print(f"Snapshot generado: {json.loads(snapshot)['total_files']} archivos documentados")

    if not api_key:
        print("ANTHROPIC_API_KEY no configurada — saltando análisis AI (modo offline)")
        return 0

    code_diffs = "\n\n".join(
        f"### {f}\n{diff_for_file(f)}" for f in code_files[:6]
    )[:MAX_DIFF_CHARS]

    doc_diffs = "\n\n".join(
        f"### {f}\n{diff_for_file(f)}" for f in doc_files[:6]
    )[:MAX_DIFF_CHARS]

    print("Llamando a Claude para análisis de coherencia...")
    analysis = analyze_coherence(code_diffs, doc_diffs, api_key)

    print(f"Resultado: coherencia={analysis['coherencia']}  drift_critico={analysis['drift_critico']}")
    for h in analysis.get("hallazgos", []):
        icon = "✓" if h["tipo"] == "ok" else ("⚠" if h["tipo"] == "warning" else "✗")
        print(f"  {icon} [{h['archivo']}] {h['descripcion']}")

    # Step summary
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        estado = analysis["coherencia"]
        icon = {"ok": "🟢", "parcial": "🟡", "drift": "🔴"}.get(estado, "⚪")
        if estado == "ok":
            titulo = "Docs y código llegaron juntos al merge ✓"
            bajada = "Revisamos el merge con IA y todo es coherente."
        elif estado == "parcial":
            titulo = "Hay código sin documentación correspondiente"
            bajada = "El merge llegó con cambios de código que no tienen docs actualizados."
        else:
            titulo = "La documentación contradice el código — requiere atención"
            bajada = "Encontramos inconsistencias entre lo que dicen los docs y lo que hace el código."

        snap = json.loads(snapshot)
        hallazgos = analysis.get("hallazgos", [])
        buenos  = [h for h in hallazgos if h["tipo"] == "ok"]
        avisos  = [h for h in hallazgos if h["tipo"] == "warning"]
        errores = [h for h in hallazgos if h["tipo"] == "error"]

        with open(summary_path, "a") as fh:
            fh.write(f"\n## {icon} Revisión de merge — {titulo}\n\n")
            fh.write(f"_{bajada}_\n\n")
            if buenos:
                fh.write(f"**Lo que está bien ({len(buenos)}):** " + " · ".join(h['descripcion'][:50] for h in buenos[:3]) + "\n\n")
            for h in errores + avisos:
                bullet = "❌" if h["tipo"] == "error" else "💡"
                fh.write(f"- {bullet} **{h['archivo']}**: {h['descripcion']}\n")
            fh.write(f"\n---\n📦 _Knowledge snapshot: **{snap['total_files']} archivos** documentados_\n")

    if analysis.get("drift_critico") and gh_token and gh_repo and not dry_run:
        title = f"[Knowledge Drift] {analysis.get('resumen', 'Drift documental')} ({sha[:8]})"
        body  = format_issue_body(analysis, sha, files)
        url   = create_github_issue(title, body, gh_token, gh_repo)
        print(f"Issue creado: {url}")

    return 0  # Capa 2 nunca bloquea el pipeline


if __name__ == "__main__":
    sys.exit(main())
