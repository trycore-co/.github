# Código como Conocimiento — Guía
_Actualizado: 2026-06-26_

> **¿Qué es esto?** Una capa automática que asegura que todo lo que el equipo construye también queda documentado. En proyectos con desarrollo acelerado por IA, el código crece más rápido de lo que la documentación puede seguirlo manualmente — este sistema lo resuelve.

---

## La idea en una frase

**Si un cambio no está en Git, no existe. Si está en Git, está verificado.**

Todo el conocimiento de arquitectura, decisiones y lógica de negocio vive en el repositorio y se audita automáticamente en cada PR, en cada merge y trimestralmente.

---

## ¿Qué hace el sistema?

Tres capas automáticas que corren en GitHub Actions sobre el runner Jarvis:

| Capa | Cuándo | Qué hace | ¿Bloquea? | Reusable |
|------|--------|----------|-----------|---------|
| 1 — PR Gate | Cada PR | Verifica que el código llegue con sus docs | ✅ Sí | `reusable-docs-coverage.yml` |
| 2 — Merge Audit | Cada merge a `main` | Revisa coherencia con IA + guarda snapshot | ❌ No (abre issue) | `reusable-docs-merge-audit.yml` |
| 3 — Audit Trimestral | 1 ene/abr/jul/oct | Audita docs vs código real | ❌ No (abre issue) | `reusable-docs-scheduled-audit.yml` |

> **Diseño clave**: los reusables proveen el entorno (checkout, Python, secrets, artefactos).
> Los scripts Python con la lógica real viven en **cada proyecto** (`scripts/ci/`) y se adaptan a su estructura.

---

## Lo que ve el equipo en cada PR

Cuando alguien abre un PR que toca código sin actualizar los docs, el bot:
1. Emite **GitHub annotations** directamente sobre los archivos afectados (`::error title=[R1] Doc Coverage::...`)
2. Agrega un **Step Summary** con tabla de zonas tocadas, hallazgos y acción requerida
3. Comenta en el PR con enlace al resumen y instrucciones claras

Si el PR es un hotfix o refactor sin cambio de comportamiento, el **líder técnico aprueba dejando un comentario** explicando la excepción. No hay override automático.

---

## Lo que ve el equipo en cada merge a `main`

Después de cada merge, una IA (Claude Haiku) revisa si lo que llegó es coherente. Si encuentra drift crítico, abre un **GitHub Issue** con:
- Qué archivo de código cambió
- Qué doc debería haberse actualizado
- Sugerencia de acción

El issue se asigna al autor del merge para resolverlo en el sprint corriente.

Además, guarda un **knowledge snapshot** como artefacto de Actions: un inventario de todos los archivos de docs en ese commit. Es el "backup incremental" de conocimiento — útil para búsqueda semántica futura (RAG).

---

## Lo que ve el equipo trimestralmente

El primer día de enero, abril, julio y octubre corre un audit completo. Revisa (los checks dependen del tipo de proyecto — ver sección de implementación):

- **ADRs** — ¿Las decisiones de arquitectura documentadas siguen implementadas en el código?
- **Historias de Usuario** — ¿Cada HU marcada como completada tiene código o test que la respalde?
- **Contratos de API / Routers** — ¿Cada spec/router tiene docs correspondientes?

Genera un issue con una tabla de todo lo que tiene drift, agrupado por tipo. El líder del sprint lo revisa y asigna responsables.

---

## Cómo implementarlo en un proyecto nuevo

### Prerrequisitos (5 min)

**Secrets**: `ANTHROPIC_API_KEY` está configurado a nivel de organización — no se configura por repo.

**Labels** (una vez por repo):

```bash
gh label create "knowledge-drift" --color "d93f0b" --description "Drift documental detectado en merge"
gh label create "knowledge-audit"  --color "e4e669" --description "Audit trimestral de conocimiento"
gh label create "automated"        --color "0075ca" --description "Issue generado automáticamente"
gh label create "quarterly"        --color "cfd3d7" --description "Revisión trimestral"
```

---

### Capa 1 — PR Gate

**Qué necesitas**:
1. `scripts/ci/docs-coverage-check.py` (adaptado al stack del proyecto — ver plantillas abajo)
2. `.github/workflows/docs-coverage-check.yml` usando el reusable

**Workflow** (copiar y ajustar `code_zones` y `doc_zones`):

```yaml
# .github/workflows/docs-coverage-check.yml
name: Doc Coverage — PR Gate (Capa 1)

on:
  pull_request:
    branches: [develop, main, 'release/**']
    paths:
      - 'app/**'        # ajustar al stack: app/ (Python), src/ (Java/Node), gateway/ (JHipster)
      - 'docs/**'
  workflow_dispatch:
    inputs:
      base_ref: {description: 'Rama base', default: 'develop'}

jobs:
  doc-coverage:
    uses: trycore-co/.github/.github/workflows/reusable-docs-coverage.yml@main
    permissions:
      contents: read
      pull-requests: write
    with:
      runner: self-hosted
      base_ref: ${{ inputs.base_ref || 'develop' }}
      code_zones: 'app/'          # ajustar: 'app/' | 'src/main/' | 'gateway/,core/'
      doc_zones: 'docs/'          # ajustar: 'docs/' | 'docs/,openspec/'
    secrets: inherit
```

**Script** — el reusable llama a `scripts/ci/docs-coverage-check.py` en el repo del proyecto.
Plantillas en [`docs/plantillas/`](plantillas/) para cada stack.

**Activar como required check** en branch protection de `develop` y `main`.

---

### Capa 2 — Merge Audit

**Qué necesitas**:
1. `scripts/ci/merge-audit.py` (adaptado al stack — ver plantillas)
2. `.github/workflows/merge-audit.yml` usando el reusable

**Workflow**:

```yaml
# .github/workflows/merge-audit.yml
name: Merge Audit + Knowledge Snapshot (Capa 2)

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'No crear issues aunque haya drift'
        type: boolean
        default: false
      base_ref:
        description: 'Rama base para el diff'
        default: 'develop'

jobs:
  merge-audit:
    uses: trycore-co/.github/.github/workflows/reusable-docs-merge-audit.yml@main
    permissions:
      contents: read
      issues: write
    with:
      runner: self-hosted
      dry_run: ${{ inputs.dry_run || false }}
      base_ref: ${{ inputs.base_ref || 'develop' }}
    secrets: inherit
```

**Script `merge-audit.py`** — contrato exacto:

| Elemento | Valor |
|----------|-------|
| Invocación | `python scripts/ci/merge-audit.py` |
| **Env vars de entrada** | `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_SHA`, `DRY_RUN` (`"true"`/`"false"`), `MERGE_BASE_REF` (rama base, ej. `"develop"`) |
| **Archivo generado** | `scripts/ci/knowledge-snapshot.json` |
| **Exit code** | Siempre 0 (no bloquea el pipeline) |

**Qué debe hacer**:
1. Obtener los archivos que llegaron en el merge (`git diff HEAD^1 HEAD`)
2. Separar en `code_files` y `doc_files` según las zonas del proyecto
3. Llamar a `claude-haiku-4-5-20251001` con ambos diffs para analizar coherencia
4. Claude devuelve JSON con este esquema:
   ```json
   {"drift_critico": false, "hallazgos": ["descripción del problema"], "accion_sugerida": "texto"}
   ```
5. Generar `scripts/ci/knowledge-snapshot.json` — manifest de todos los docs:
   ```json
   {"sha": "abc123", "timestamp": "2026-06-26T09:00:00Z", "docs": ["docs/file.md", ...]}
   ```
6. Si `drift_critico=true` y `DRY_RUN != "true"` → crear GitHub Issue con label `knowledge-drift`
7. Escribir Step Summary con estado (🟢/🟡/🔴), hallazgos y link al snapshot

> **Modelo**: `claude-haiku-4-5-20251001` — rápido (~12 s) y económico (~$0.03/merge).

---

### Capa 3 — Audit Trimestral

**Qué necesitas**:
1. `scripts/ci/scheduled-audit.py` (adaptado al stack — ver plantillas)
2. `.github/workflows/scheduled-audit.yml` usando el reusable

**Workflow**:

```yaml
# .github/workflows/scheduled-audit.yml
name: Scheduled Audit Trimestral (Capa 3)

on:
  schedule:
    - cron: '0 9 1 1,4,7,10 *'   # primer día de cada trimestre a las 9 AM UTC
  workflow_dispatch:
    inputs:
      scope:
        description: 'Alcance'
        type: choice
        options: [all, hus-only, routers-only]   # ajustar opciones al proyecto
        default: all

jobs:
  scheduled-audit:
    uses: trycore-co/.github/.github/workflows/reusable-docs-scheduled-audit.yml@main
    permissions:
      contents: read
      issues: write
    with:
      runner: self-hosted
      scope: ${{ inputs.scope || 'all' }}
    secrets: inherit
```

**Script `scheduled-audit.py`** — qué debe hacer según el stack:

| Stack | Checks a implementar |
|-------|---------------------|
| JHipster/Java | ADR vigencia · HU trazabilidad · OpenSpec vs Resources Java |
| Python/FastAPI | HU trazabilidad · Router coverage (app/routers/ vs docs/) |
| Node/React | HU trazabilidad · Módulos vs docs/ |

**Contrato exacto del script**:

| Elemento | Valor |
|----------|-------|
| Invocación | `python scripts/ci/scheduled-audit.py` |
| **Env vars de entrada** | `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `AUDIT_SCOPE` (`"all"` \| `"hus-only"` \| `"routers-only"`) |
| **Archivo generado** | `scripts/ci/last-scheduled-audit.json` (**sin punto inicial** — `actions/upload-artifact` ignora archivos ocultos) |
| **Exit code** | Siempre 0 (no bloquea el pipeline) |

El script siempre debe:
- Guardar `scripts/ci/last-scheduled-audit.json` (artefacto — **sin punto inicial**, sin ese la acción de upload lo ignora)
- Escribir Step Summary con tabla de items y conteos
- Crear GitHub Issue con labels `knowledge-audit`, `quarterly`, `automated` si hay drift
- Retornar 0 (nunca bloquea el pipeline)

**Esquema del artefacto** `last-scheduled-audit.json`:
```json
{
  "hus": [
    {"hu": "docs/04-historias/HU-001.md", "estado": "implementada|parcial|no_implementada", "evidencia": "app/routers/...", "accion": "ninguna|completar_impl"}
  ],
  "routers": [
    {"router": "app/routers/linkedin.py", "estado": "documentado|sin_doc|parcial", "doc_relacionada": "docs/...", "accion": "ninguna|crear_doc"}
  ]
}
```

> **Modelo**: `claude-sonnet-4-6` — análisis profundo, corre solo 4 veces al año (~$0.50-2.00/ejecución).

---

## Plantillas por stack

Los scripts de referencia para copiar y adaptar:

| Stack | Referencia canónica |
|-------|-------------------|
| **JHipster / Java** | [`docfly-saas-docs/scripts/ci/`](https://github.com/trycore-co/docfly-saas-docs/tree/develop/scripts/ci) |
| **Python / FastAPI** | [`TrySynergy_TH_RPA/scripts/ci/`](https://github.com/trycore-co/TrySynergy_TH_RPA/tree/develop/scripts/ci) |

Al adaptar un script a un nuevo stack, cambiar:
- `CODE_ZONES` — prefijos de carpetas de código (ej. `app/`, `src/main/`)
- `DOC_ZONES` — prefijos de carpetas de docs (ej. `docs/`, `docs/,openspec/`)
- Patrones específicos (ROUTER_PATTERN para FastAPI, Resource/*.java para JHipster)
- El contexto del prompt de Claude (describir el stack del proyecto)

---

## Preguntas frecuentes del equipo

**¿Qué pasa si hago un PR de solo docs?**
El sistema lo detecta y avisa (no bloquea). Es un recordatorio de verificar que no se olvidó el código.

**¿Qué pasa si el issue del audit trimestral es muy grande?**
El líder técnico lo triagea: algunos items se cierran como "false positive" (el modelo no encontró el código pero existe), otros se convierten en tareas del sprint. El audit mejora con el tiempo.

**¿Por qué no bloquea el pipeline en Capas 2 y 3?**
Porque el merge ya llegó a `main` — bloquear retroactivamente no tiene sentido. Lo que sí hace es crear trabajo visible en el backlog para cerrar la deuda documental.

**¿Cuánto cuesta?**
- Capa 1: $0 (sin IA)
- Capa 2: ~$0.03 por merge a `main` (Claude Haiku)
- Capa 3: ~$0.50–2.00 por ejecución trimestral (Claude Sonnet)

**¿ANTHROPIC_API_KEY va en cada repo?**
No. Está configurada a nivel de **organización** en GitHub — todos los repos la heredan automáticamente con `secrets: inherit`.

---

## Relación con los otros documentos de la org

| Documento | Para qué |
|-----------|----------|
| [Buenas Prácticas Pipeline](BUENAS-PRACTICAS-PIPELINE.md) | CI/CD: compilación, tests, Sonar, Trivy |
| [Implementar Pipeline](IMPLEMENTAR-PIPELINE.md) | Guía paso a paso para líderes |
| [Jenkins CI/CD Policy](jenkins-cicd-policy.md) | Despliegue on-premise con Jenkins |
| **Este documento** | Auditoría automática de conocimiento (3 capas) |

El principio que une todo: **el repositorio es la fuente de verdad — del código y del conocimiento.**
