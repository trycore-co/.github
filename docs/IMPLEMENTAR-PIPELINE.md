# Implementar Pipeline CI/CD — Guía de Ejecución

> **Para líderes técnicos:** este documento explica qué hace el pipeline, qué esperar como resultado, y cómo pedirle a una IA que lo implemente. No es necesario leer la guía técnica completa para usar este archivo.
>
> **Para IAs:** las secciones marcadas con 🤖 contienen el prompt listo para ejecutar. Leer todo el documento antes de empezar.

---

## ¿Qué hace el pipeline?

Cada vez que se abre un Pull Request, el pipeline ejecuta automáticamente tres análisis y publica los resultados directamente en la pestaña **Summary** del PR:

| Análisis | Herramienta | Qué revisa | ¿Bloquea el merge? |
|---|---|---|---|
| Unit Tests | pytest + JUnit | Tests pasando / fallando | Sí, si `has-tests: true` |
| Calidad de código | SonarQube | Cobertura ≥ 80%, bugs, vulnerabilidades, duplicaciones | Sí, si Quality Gate falla |
| Vulnerabilidades en dependencias | Trivy | CVEs CRITICAL/HIGH/MEDIUM con fix disponible | No — solo informativo |

El resultado visible en el PR se ve así:

```
🔍 SonarQube — ✅ PASSED

| Métrica          | Valor  | Umbral     |
|------------------|--------|------------|
| Quality Gate     | ✅ PASSED | —        |
| Coverage         | 87.3%  | ≥ 80%     |
| Duplicaciones    | 1.2%   | ≤ 3%      |
| Bugs             | 0      | 0 críticos |
| Vulnerabilidades | 0      | 0 críticas |
| Code Smells      | 4      | —          |

🛡️ SCA — Trivy — ✅ Sin vulnerabilidades CRITICAL/HIGH
```

---

## Prerequisitos — verificar antes de empezar

Estas configuraciones ya existen en la organización `trycore-co`. Solo confirmar que el repo está dentro de la org:

- [x] `SONAR_TOKEN` — secret de organización (no configurar por repo)
- [x] `SONAR_HOST_URL` — variable de organización (no configurar por repo)
- [x] Reusable workflow Python en `trycore-co/.github`

Si el repo es de una org diferente a `trycore-co`, ver §16.1 de la [Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md) para configurar los secrets antes de continuar.

---

## Caso 1 — Repo nuevo sin pipeline existente

**Para el líder:** pide esto cuando el repo no tiene ningún archivo en `.github/workflows/`.

**Para la IA 🤖 — copiar y pegar esto en el chat:**

---

Necesito que implementes el pipeline de CI/CD en este repositorio siguiendo los estándares de la organización `trycore-co`.

Antes de generar cualquier archivo, lee la guía oficial completa en:
https://github.com/trycore-co/.github/blob/main/docs/BUENAS-PRACTICAS-PIPELINE.md

**Lo que ya existe y NO debes configurar:**
- `SONAR_TOKEN` ya es secret de organización
- `SONAR_HOST_URL` ya es variable de organización
- El reusable workflow Python ya existe en `trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main`

**Lo que debes hacer:**
1. Explorar el repo e identificar: qué servicios/directorios existen, si cada uno tiene `tests/unit/`, y qué versión de Python usan
2. Por cada servicio, crear `.github/workflows/pr-check-<nombre-servicio>.yml` usando el wrapper de §16.4 de la guía
3. Cada archivo debe tener ~25 líneas con esta estructura:

```yaml
name: PR Check — <Nombre Servicio>

on:
  workflow_dispatch:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
    paths:
      - '<service-dir>/**'

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: <service-dir>
      sonar-project-key: <service-dir>
      sonar-project-name: <Nombre Legible>
      python-version: '3.11'
      has-tests: true         # false si no existe tests/unit/
      tests-continue-on-error: false
    secrets: inherit
```

4. Después de crear los archivos, hacer commit y push a una rama feature
5. Ejecutar `gh workflow run pr-check-<nombre>.yml --ref <rama>` para cada servicio
6. Confirmar que el resultado sea `in_progress` o `success` — si aparece `startup_failure` en menos de 5 segundos, leer §16.6.1 de la guía antes de continuar

**⚠️ El bloque `permissions:` en el job es obligatorio.** Sin él, GitHub rechaza el workflow con `startup_failure` sin mostrar ningún log de error.

---

## Caso 2 — Repo con pipeline inline existente (migración)

**Para el líder:** pide esto cuando el repo ya tiene archivos `.github/workflows/pr-check-*.yml` con 100–200 líneas cada uno. El objetivo es reducirlos a ~25 líneas sin perder ningún informe ni funcionalidad.

**Para la IA 🤖 — copiar y pegar esto en el chat:**

---

Necesito que migres los workflows de CI/CD de este repositorio al estándar de reusable workflows de la organización `trycore-co`.

Antes de tocar cualquier archivo, lee la guía oficial en:
https://github.com/trycore-co/.github/blob/main/docs/BUENAS-PRACTICAS-PIPELINE.md

Lee específicamente **§16.7** (Migración de repo existente) y **§16.6.1** (startup_failure).

**Lo que ya existe y NO debes configurar:**
- `SONAR_TOKEN` ya es secret de organización
- `SONAR_HOST_URL` ya es variable de organización
- El reusable workflow Python ya existe en `trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main`

**Lo que debes hacer:**

**Paso 1 — Inventariar** (§16.7.1): leer cada `.github/workflows/pr-check-*.yml` existente y extraer estos valores por servicio:

| Parámetro | Dónde mirarlo |
|---|---|
| `service-dir` | `working-directory:` en los steps `run:` |
| `sonar-project-key` | `-Dsonar.projectKey=` o `sonar-project.properties` |
| `sonar-project-name` | `-Dsonar.projectName=` |
| `python-version` | `python-version:` en setup-python |
| `has-tests` | ¿Hay un step de pytest? |
| `tests-continue-on-error` | ¿El step de pytest tiene `continue-on-error: true`? |

**Paso 2 — Reemplazar** cada archivo por el wrapper de §16.4, conservando exactamente los mismos parámetros del inventario. El archivo debe quedar con ~25 líneas.

**Paso 3 — Verificar** que cada wrapper incluye el bloque `permissions:` en el job. Es **obligatorio** — sin él GitHub falla con `startup_failure` sin logs (§16.6.1).

**Paso 4 — Validar**: commit, push a rama feature, ejecutar `gh workflow run` para cada servicio migrado. Confirmar que el resultado es `in_progress` o `success`, nunca `startup_failure` en menos de 5 segundos.

**Paso 5 — Limpieza**: si `SONAR_TOKEN` existía como secret a nivel de repo, eliminarlo después de confirmar que el de organización funciona.

**No cambiar lógica ni agregar features** — solo reemplazar el contenido inline por el wrapper. Los informes generados (JUnit, SonarQube, Trivy) son idénticos al workflow anterior. Ver §16.7.3 para saber exactamente qué esperar ver en el Summary después de la migración.

---

## ¿Cuál caso aplica a mi proyecto?

```
¿El repo tiene archivos en .github/workflows/?
│
├── No → Usar Caso 1 (repo nuevo)
│
└── Sí → ¿Los archivos tienen más de 50 líneas?
          │
          ├── Sí → Usar Caso 2 (migración)
          │
          └── No → Ya usa el wrapper reusable, no hacer nada
```

---

## Referencia

- [Guía completa de Buenas Prácticas CI/CD](BUENAS-PRACTICAS-PIPELINE.md) — referencia técnica detallada
- [§16.6.1](BUENAS-PRACTICAS-PIPELINE.md#1661-lección-aprendida--startup_failure-por-permissions-en-reusable-workflows) — diagnóstico de `startup_failure`
- [§16.7](BUENAS-PRACTICAS-PIPELINE.md#167-migración-de-un-repo-existente-al-wrapper-reusable) — guía de migración paso a paso
