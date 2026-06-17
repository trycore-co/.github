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
- [x] Reusable workflow Python en `trycore-co/.github` (`reusable-pr-check-python.yml`)
- [x] Reusable workflow Node/React en `trycore-co/.github` (`reusable-pr-check-node.yml`)

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
- El reusable workflow Node/React ya existe en `trycore-co/.github/.github/workflows/reusable-pr-check-node.yml@main`

**Lo que debes hacer:**
1. Explorar el repo e identificar: qué servicios/directorios existen, si cada uno tiene `tests/unit/` (Python) o `src/**` (Node), y qué versión de lenguaje usan
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

**⚠️ Python con `pyproject.toml` — crear `requirements-dev.txt`.**
El reusable ejecuta `pip install -r <requirements-file>`. Si el proyecto usa `pyproject.toml` (sin `requirements.txt` propio), crear el archivo `backend/requirements-dev.txt` con una sola línea:
```
-e .[dev]
```
Y en el wrapper pasar `requirements-file: requirements-dev.txt`. Sin este archivo el pipeline falla con `FileNotFoundError`.

**⚠️ Python — los tests deben estar en `tests/unit/`.**
El reusable ejecuta `pytest tests/unit/` de forma fija. Si los tests están en `tests/` directamente, moverlos a `tests/unit/` y actualizar `testpaths` en `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests/unit"]
```
Sin esta estructura el reusable reporta 0 tests sin error visible.

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
- El reusable workflow Node/React ya existe en `trycore-co/.github/.github/workflows/reusable-pr-check-node.yml@main`

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

## Caso 3 — Stack sin reusable existente

**Para el líder:** pide esto cuando el repo usa un stack para el que **no existe todavía** un reusable workflow en `trycore-co/.github`.

> **Reusable workflows disponibles actualmente (junio 2026):**
> - **Python** → `reusable-pr-check-python.yml` → usar **Caso 1**
> - **Node.js / React / Vite / Vitest** → `reusable-pr-check-node.yml` → usar **Caso 1**
> - **Java/Maven / JHipster** → `reusable-pr-check-maven.yml` → usar **Caso 1**
> - **Angular** → `reusable-pr-check-angular.yml` → usar **Caso 1**
>
> **Este caso aplica solo para stacks que NO están en la lista anterior** — por ejemplo Go, .NET, Ruby, etc.

**Diferencia con los casos anteriores:** aquí hay que crear el reusable workflow primero en el repo de la org, y luego sí crear el wrapper en el repo del proyecto. Son dos repos distintos.

**Para la IA 🤖 — copiar y pegar esto en el chat:**

---

Necesito implementar el pipeline de CI/CD para este repositorio. El stack es **[indicar el stack — asegurarse primero que no existe ya un reusable en la lista de Caso 3]**.

Antes de generar cualquier archivo, lee la guía oficial completa en:
https://github.com/trycore-co/.github/blob/main/docs/BUENAS-PRACTICAS-PIPELINE.md

**Lo que ya existe y NO debes configurar:**
- `SONAR_TOKEN` ya es secret de organización en `trycore-co`
- `SONAR_HOST_URL` ya es variable de organización en `trycore-co`
- El reusable workflow para Python ya existe — **no lo toques**
- El reusable workflow para Node.js ya existe — **no lo toques**
- El reusable workflow para Java/Maven ya existe — **no lo toques**
- El reusable workflow para Angular ya existe — **no lo toques**

**Lo que debes hacer — en orden:**

**Fase 1 — Crear el reusable workflow en `trycore-co/.github`**

1. Clonar `git@github.com:trycore-co/.github.git`
2. Crear `.github/workflows/reusable-pr-check-<stack>.yml` basándote en el template del stack correspondiente de la guía (§4 Java, §6 React/Vite, §7 Angular) pero adaptado a `workflow_call` con los mismos inputs que tiene `reusable-pr-check-python.yml` (ver §16.3 como referencia de estructura)
3. El reusable workflow debe:
   - Declarar `on: workflow_call:` con inputs para: `service-dir`, `sonar-project-key`, `sonar-project-name`, y los que apliquen al stack
   - Declarar `secrets: SONAR_TOKEN: required: true`
   - Usar `working-directory: ${{ inputs.service-dir }}` en cada step `run:` individualmente — **nunca** en `defaults.run.working-directory` (ver §16.6.1)
   - Incluir los tres bloques de informes: tests, SonarQube summary y Trivy (ver §3 de la guía para los patrones de cada bloque)
4. Commit y push a `main` de `trycore-co/.github`

**Fase 2 — Crear el wrapper en este repo**

5. Crear `.github/workflows/pr-check-<nombre>.yml` con ~25 líneas:

```yaml
name: PR Check — <Nombre>

on:
  workflow_dispatch:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
    paths:
      - '<service-dir>/**'    # omitir paths si es repo de un solo servicio

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-<stack>.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: <service-dir>
      sonar-project-key: <project-key>
      sonar-project-name: <Nombre Legible>
      # inputs adicionales según el stack
    secrets: inherit
```

**⚠️ El bloque `permissions:` en el job caller es obligatorio** — sin él GitHub falla con `startup_failure` antes de crear cualquier job (§16.6.1).

**⚠️ Regla al escribir el reusable workflow — env vars:** no agregar `env:` con valores específicos de tu proyecto en ningún step del reusable. Todo lo que pongas ahí se inyecta en **todos** los repos de la org que usen ese workflow. Si tu proyecto necesita variables de entorno para los tests, defínelas como GitHub repository variables en el repo del proyecto — no en el reusable. Ver §16.6.2 de la guía.

**⚠️ Regla al escribir el reusable workflow — Quality Gate:** no poner `continue-on-error: true` en el step de Quality Gate dentro del reusable. Ese flag impide que el QG bloquee PRs en **todos** los repos de la org sin excepción — nadie puede contrarrestarlo desde su wrapper. Si un proyecto necesita desbloquear temporalmente el QG, debe ajustar los umbrales en el servidor SonarQube. Ver §16.6.3 de la guía y la tabla de responsabilidades §16.6.4.

**Fase 3 — Documentar**

6. En `trycore-co/.github/docs/BUENAS-PRACTICAS-PIPELINE.md`, agregar:
   - Una subsección en §16.2 mencionando el nuevo archivo en la estructura del repo org
   - Una nueva sección §16.X con el reusable workflow completo del nuevo stack, siguiendo el mismo formato que §16.3
   - Una fila en la tabla de reusable workflows disponibles (si existe)

7. Actualizar la nota al inicio de `BUENAS-PRACTICAS-PIPELINE.md` indicando que el reusable workflow para el nuevo stack ya existe

**Fase 4 — Validar**

8. Ejecutar `gh workflow run pr-check-<nombre>.yml --ref <rama>` desde el repo del proyecto
9. Confirmar que el resultado es `in_progress` o `success` — nunca `startup_failure` en menos de 5 segundos
10. Verificar que los tres bloques de informes aparecen en el Step Summary (ver §16.7.3)

---

## ¿Cuál caso aplica a mi proyecto?

```
¿Qué stack tiene el repo?
│
├── Python / FastAPI / pytest
│     │
│     └── ¿Tiene archivos en .github/workflows/?
│           ├── No  → Caso 1  (repo nuevo Python)
│           └── Sí  → ¿Más de 50 líneas?
│                     ├── Sí → Caso 2  (migración Python)
│                     └── No → Ya usa el wrapper — no hacer nada
│
├── React / Vite / Vitest / Node.js
│     │
│     └── ¿Tiene archivos en .github/workflows/?
│           ├── No  → Caso 1  (repo nuevo Node — uses: reusable-pr-check-node.yml)
│           └── Sí  → ¿Más de 50 líneas?
│                     ├── Sí → Caso 2  (migración Node)
│                     └── No → Ya usa el wrapper — no hacer nada
│
└── Java / Angular / otro
      │
      └── ¿Existe reusable-pr-check-<stack>.yml en trycore-co/.github?
            ├── Sí → Caso 1 o 2 adaptando el uses: al stack correcto
            └── No → Caso 3  (crear reusable nuevo + wrapper)
```

---

## Caso 4 — Crear el job de despliegue en Jenkins

**Para el líder:** una vez que el repo tiene `Jenkinsfile` en la raíz, hacer esto una sola vez en Jenkins para activar el despliegue automático a `develop`.

**Prerequisito:** el `Jenkinsfile` ya debe existir en el repo (si no existe, pedirle a una IA que lo genere siguiendo la [política Jenkins](jenkins-cicd-policy.md)).

### Paso a paso en la UI de Jenkins

1. Entrar a Jenkins (`http://<servidor>:8013` o la URL de la org)
2. Navegar al **folder del proyecto** (ej: `Trycore → AI-hub`)
3. Click en **"New Item"** (esquina superior izquierda)
4. Escribir el nombre del job (ej: `deploy-ia-hub`) y seleccionar **"Pipeline"** → OK
5. En la configuración del job:
   - **Description:** breve descripción del proyecto
   - **Build Triggers:** marcar **"Poll SCM"** y en el campo de cron escribir `H/2 * * * *`
   - **Pipeline → Definition:** seleccionar **"Pipeline script from SCM"**
   - **SCM:** Git
   - **Repository URL:** URL HTTPS del repo de GitHub (ej: `https://github.com/trycore-co/<repo>.git`)
   - **Credentials:** seleccionar la credencial de GitHub (ver §3.2 de la [política Jenkins](jenkins-cicd-policy.md) para el ID)
   - **Branches to build:** `*/develop` (añadir `*/release/*` y `*/main` si aplica)
   - **Script Path:** `Jenkinsfile`
6. Click en **Save**
7. Ir al job recién creado → **"Build with Parameters"** → ejecutar el primer build manualmente para verificar

> ⚠️ **No agregar `triggers { pollSCM }` en el Jenkinsfile** si ya configuraste Poll SCM en la UI — causa builds duplicados. El Jenkinsfile solo debe declarar la lógica de stages, no el trigger.

### Credencial de Google Chat (webhook)

El `Jenkinsfile` de cada proyecto usa una credencial tipo **Secret Text** para enviar notificaciones. Crearla antes del primer build:

**Para la IA 🤖 — si necesitas crear la credencial desde curl:**

La creación de credenciales en Jenkins por API tiene una trampa: el **CSRF token (crumb) es de sesión** — si lo obtienes en un request y lo usas en otro sin compartir las cookies, Jenkins devuelve 403 o 500 sin mensaje útil.

La forma más confiable desde curl:

```bash
# 1. Obtener crumb guardando las cookies en archivo
curl -s -u "admin:PASSWORD" \
  -c /tmp/jenkins-cookies.txt \
  "http://<jenkins>/crumbIssuer/api/json"
# Tomar el valor de "crumb" de la respuesta

# 2. Crear la credencial usando LAS MISMAS cookies
curl -s -u "admin:PASSWORD" \
  -b /tmp/jenkins-cookies.txt \
  -c /tmp/jenkins-cookies.txt \
  -H "Jenkins-Crumb: <CRUMB-DEL-PASO-1>" \
  -X POST "http://<jenkins>/credentials/store/system/domain/_/createCredentials" \
  --data-urlencode 'json={
    "": "0",
    "credentials": {
      "scope": "GLOBAL",
      "id": "gchat-webhook-<proyecto>",
      "secret": "https://chat.googleapis.com/...",
      "description": "Google Chat webhook <proyecto>",
      "$class": "org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl"
    }
  }'
```

**Alternativa sin curl — Script Console de Groovy** (más confiable, no tiene problemas de CSRF):

1. Jenkins → **Manage Jenkins → Script Console**
2. Ejecutar:

```groovy
import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.*
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import hudson.util.Secret

def cred = new StringCredentialsImpl(
    CredentialsScope.GLOBAL,
    'gchat-webhook-<proyecto>',
    'Google Chat webhook <proyecto>',
    Secret.fromString('https://chat.googleapis.com/...')
)
SystemCredentialsProvider.getInstance()
    .getStore()
    .addCredentials(Domain.global(), cred)
println "Credencial creada OK"
```

---

## Referencia

- [Guía completa de Buenas Prácticas CI/CD](BUENAS-PRACTICAS-PIPELINE.md) — referencia técnica detallada
- [§16.3](BUENAS-PRACTICAS-PIPELINE.md#163-reusable-workflow--python-todo-en-uno) — estructura del reusable workflow Python (modelo para otros stacks)
- [§16.6.1](BUENAS-PRACTICAS-PIPELINE.md#1661-lección-aprendida--startup_failure-por-permissions-en-reusable-workflows) — diagnóstico de `startup_failure`
- [§16.7](BUENAS-PRACTICAS-PIPELINE.md#167-migración-de-un-repo-existente-al-wrapper-reusable) — guía de migración paso a paso
