# Código como Conocimiento — Guía
_Actualizado: 2026-06-24_

> **¿Qué es esto?** Una capa automática que asegura que todo lo que el equipo construye también queda documentado. En proyectos con desarrollo acelerado por IA, el código crece más rápido de lo que la documentación puede seguirlo manualmente — este sistema lo resuelve.

---

## La idea en una frase

**Si un cambio no está en Git, no existe. Si está en Git, está verificado.**

Todo el conocimiento de arquitectura, decisiones y lógica de negocio vive en el repositorio y se audita automáticamente en cada PR, en cada merge y trimestralmente.

---

## ¿Qué hace el sistema?

Tres capas automáticas que corren en GitHub Actions sobre el runner Jarvis:

| Cuándo | Qué hace | ¿Bloquea? |
|--------|----------|-----------|
| Cada PR | Verifica que el código llegue con sus docs | ✅ Sí, si falta documentación |
| Cada merge a  | Revisa coherencia con IA + guarda snapshot | ❌ No (abre issue si hay drift) |
| Cada trimestre | Audita ADRs, HUs y specs vs código real | ❌ No (abre issue con reporte) |

---

## Lo que ve el equipo en cada PR

Cuando alguien abre un PR que toca código sin actualizar los docs, el bot comenta automáticamente con instrucciones claras de qué actualizar. No es un error críptico — es una conversación.

Si el PR es un hotfix o refactor sin cambio de comportamiento, el **líder técnico aprueba dejando un comentario** explicando la excepción. No hay override automático.

---

## Lo que ve el equipo en cada merge a 

Después de cada merge, una IA (Claude Haiku) revisa si lo que llegó es coherente. Si encuentra drift crítico, abre un **GitHub Issue** con:
- Qué archivo de código cambió
- Qué doc debería haberse actualizado
- Sugerencia de acción

El issue se asigna al autor del merge para resolverlo en el sprint corriente.

Además, guarda un **knowledge snapshot**: un inventario de todos los archivos de docs y specs en ese momento. Es el "backup incremental" de conocimiento — útil si en el futuro se implementa búsqueda semántica (RAG).

---

## Lo que ve el equipo trimestralmente

El primer día de enero, abril, julio y octubre corre un audit completo. Revisa:

- **ADRs** — ¿Las decisiones de arquitectura documentadas siguen implementadas en el código?
- **Historias de Usuario** — ¿Cada HU marcada como completada tiene código o test que la respalde?
- **Contratos de API** — ¿Cada spec en OpenSpec tiene un endpoint real implementado?

Genera un issue con una tabla de todo lo que tiene drift, agrupado por tipo. El líder del sprint lo revisa y asigna responsables.

---

## Cómo implementarlo en un proyecto nuevo

### Prerrequisitos (5 min)

1. **Script Python**: copiar  al repo del proyecto
2. **Secret de API**: agregar  en Settings → Secrets (solo para Capas 2 y 3)
3. **Labels en GitHub**: crear , , , 

```bash
gh label create "knowledge-drift" --color "d93f0b" --description "Drift documental detectado en merge"
gh label create "knowledge-audit"  --color "e4e669" --description "Audit trimestral de conocimiento"
gh label create "automated"        --color "0075ca" --description "Issue generado automáticamente"
gh label create "quarterly"        --color "cfd3d7" --description "Revisión trimestral"
```

### Capa 1 — PR Gate (sin costo de API, lista en 10 min)

Agrega este workflow al repo usando el reusable de la org:

```yaml
# .github/workflows/docs-coverage-check.yml
name: Doc Coverage — PR Gate

on:
  pull_request:
    branches: [develop, main, 'release/**']
    paths:
      - 'src/**'        # ajustar a las zonas de código del proyecto
      - 'docs/**'
      - 'openspec/**'
  workflow_dispatch:
    inputs:
      base_ref:
        description: 'Rama base'
        default: 'develop'

jobs:
  doc-coverage:
    uses: trycore-co/.github/.github/workflows/reusable-docs-coverage.yml@main
    with:
      runner: self-hosted
      base_ref: ${{ inputs.base_ref || 'develop' }}
      code_zones: 'src/main/'          # ajustar
      doc_zones: 'docs/,openspec/'     # ajustar
    secrets: inherit
```

Luego activar como **required status check** en branch protection de  y .

### Capas 2 y 3 — Merge Audit y Scheduled Audit

Copiar directamente del proyecto docfly-saas-docs:
- 
- 
- 
- 

Ajustar las rutas  y  al inicio de cada script si el proyecto tiene estructura diferente.

---

## Preguntas frecuentes del equipo

**¿Qué pasa si hago un PR de solo docs?**
El sistema lo detecta y avisa (no bloquea). Es un recordatorio de verificar que no se olvidó el código.

**¿Qué pasa si el issue del audit trimestral es muy grande?**
El líder técnico lo triagea: algunos items se cierran como "false positive" (el modelo no encontró el código pero existe), otros se convierten en tareas del sprint. El audit mejora con el tiempo.

**¿Por qué no bloquea el pipeline en Capas 2 y 3?**
Porque el merge ya llegó a  — bloquear retroactivamente no tiene sentido. Lo que sí hace es crear trabajo visible en el backlog para cerrar la deuda documental.

**¿Cuánto cuesta?**
- Capa 1: \/bin/zsh (sin IA)
- Capa 2: ~\/bin/zsh.03 por merge a main (Claude Haiku)
- Capa 3: ~\/bin/zsh.50–2.00 por ejecución trimestral (Claude Sonnet)

---

## Relación con los otros documentos de la org

| Documento | Para qué |
|-----------|----------|
| [Buenas Prácticas Pipeline](BUENAS-PRACTICAS-PIPELINE.md) | CI/CD: compilación, tests, Sonar, Trivy |
| [Implementar Pipeline](IMPLEMENTAR-PIPELINE.md) | Guía paso a paso para líderes |
| [Jenkins CI/CD Policy](jenkins-cicd-policy.md) | Despliegue on-premise con Jenkins |
| **Este documento** | Auditoría automática de conocimiento |

El principio que une todo: **el repositorio es la fuente de verdad — del código y del conocimiento.**
