# Plantillas — Scripts CI para Código como Conocimiento

Scripts de referencia para implementar el sistema de 3 capas de auditoría documental en proyectos nuevos.
Ver [CODIGO-COMO-CONOCIMIENTO.md](../CODIGO-COMO-CONOCIMIENTO.md) para la documentación completa.

## Contenido

| Archivo | Capa | Stack | Función |
|---------|------|-------|---------|
| `docs-coverage-check.python-fastapi.py` | 1 — PR Gate | Python/FastAPI | Verifica en cada PR que código y docs lleguen juntos |
| `merge-audit.python-fastapi.py` | 2 — Merge Audit | Python/FastAPI | Analiza coherencia docs↔código con Claude Haiku en cada merge |
| `scheduled-audit.python-fastapi.py` | 3 — Audit Trimestral | Python/FastAPI | Barrido completo trimestral con Claude Sonnet |

## Cómo usar

1. Copiar los 3 archivos a `scripts/ci/` del proyecto nuevo
2. Renombrarlos a `docs-coverage-check.py`, `merge-audit.py`, `scheduled-audit.py`
3. Ajustar las variables marcadas con `# ADAPTAR:` en cada script
4. Crear los 3 workflows en `.github/workflows/` siguiendo los templates en `CODIGO-COMO-CONOCIMIENTO.md`
5. Crear los labels requeridos (ver sección Prerrequisitos de la guía)

## Qué adaptar por stack

| Variable | Python/FastAPI (ya configurado) | Java/Maven | Node.js |
|----------|--------------------------------|------------|---------|
| `CODE_ZONES` | `("app/routers/", "app/scrapers/", "app/services/")` | `("src/main/java/",)` | `("src/",)` |
| `DOC_ZONES` | `("docs/",)` | `("docs/",)` | `("docs/",)` |
| `ROUTER_PATTERN` | `app/routers/*.py` | `*Resource.java` | `src/routes/*.js` |
| Prompt Claude | describe microservicio FastAPI | describe monolito Spring | describe app Node |
