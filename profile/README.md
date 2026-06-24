# Trycore

Consultoría de software especializada en arquitecturas modernas: microservicios, BPM, integraciones y plataformas de datos.

---

## CI/CD con GitHub Actions

### Qué hace el pipeline de calidad

Cada vez que se abre un Pull Request, el pipeline ejecuta automáticamente:

| Análisis | Herramienta | Resultado visible en el PR |
|---|---|---|
| Unit Tests | pytest / Vitest | Tabla de tests pasando/fallando |
| Calidad de código | SonarQube | Cobertura ≥ 80 %, bugs, vulnerabilidades |
| Vulnerabilidades en dependencias | Trivy | CVEs CRITICAL/HIGH con fix disponible |

Los resultados aparecen en la pestaña **Summary** del PR. SonarQube bloquea el merge si la cobertura baja del umbral o hay bugs críticos.

### Reusable workflows disponibles

Los workflows viven en este repo (`.github/workflows/`) y cualquier repo de la org los consume con ~25 líneas:

| Workflow | Stack | Estado |
|---|---|---|
| `reusable-pr-check-python.yml` | Python · FastAPI · pytest | ✅ Listo |
| `reusable-pr-check-node.yml` | React · Vite · Vitest · Node.js | ✅ Listo |
| `reusable-pr-check-maven.yml` | Java · Spring Boot · Maven · JHipster | ✅ Listo |
| `reusable-pr-check-angular.yml` | Angular · Karma · Jasmine | ✅ Listo |
| `reusable-docs-coverage.yml` | Doc Coverage · Python · GitHub API | ✅ Listo |

> **Prerequisitos ya configurados en la org:** `SONAR_TOKEN` (secret de org) y `SONAR_HOST_URL` (variable de org). No configurar por repo.

### Cómo activar el CI en un repo nuevo — 3 pasos

**Paso 1 — Crear el archivo de workflow** en `.github/workflows/pr-check-<servicio>.yml` con ~25 líneas:

```yaml
# Ejemplo: backend Python
name: PR Check — Backend

on:
  workflow_dispatch:
  pull_request:
    branches: [develop, main, 'release/**']
    paths: ['backend/**']

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: backend
      sonar-project-key: Proyecto:NombreServicio   # crear primero en SonarQube
      sonar-project-name: Nombre Legible
      python-version: '3.14'
      requirements-file: requirements-dev.txt       # ver nota abajo
      has-tests: true
    secrets: inherit
```

```yaml
# Ejemplo: frontend React/Vite
name: PR Check — Frontend

on:
  workflow_dispatch:
  pull_request:
    branches: [develop, main, 'release/**']
    paths: ['frontend/**']

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-node.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: frontend
      sonar-project-key: Proyecto:NombreServicio-Frontend
      sonar-project-name: Nombre Legible Frontend
      node-version: '20'
      has-tests: true
    secrets: inherit
```

```yaml
# Ejemplo: microservicio Java/Spring Boot (JHipster)
name: PR Check — Microservicio Java

on:
  workflow_dispatch:
  pull_request:
    branches: [develop, main, 'release/**']

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-maven.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: .
      sonar-project-key: Proyecto:NombreServicio
      sonar-project-name: Nombre Legible
      java-version: '17'
      has-tests: true
      # runner: self-hosted   # ← descomentar para usar la flota Jarvis (sin costo de minutos)
    secrets: inherit
```

```yaml
# Ejemplo: frontend Angular
name: PR Check — Frontend Angular

on:
  workflow_dispatch:
  pull_request:
    branches: [develop, main, 'release/**']

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-angular.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: .
      sonar-project-key: Proyecto:NombreServicio-Front
      sonar-project-name: Nombre Legible Frontend
      node-version: '20'
      has-tests: true
      # runner: self-hosted   # ← descomentar para usar la flota Jarvis (sin costo de minutos)
    secrets: inherit
```

**Paso 2 — Crear el proyecto en SonarQube** (`docs.trycore.co:9000`) con el mismo `sonar-project-key` del workflow.

**Paso 3 — Push y verificar:** hacer commit, push a una rama, abrir PR hacia `develop` y confirmar que el check aparece en la pestaña **Checks** del PR.

### Advertencias frecuentes

> **⚠️ El bloque `permissions:` es obligatorio.** Sin él, GitHub falla con `startup_failure` sin mostrar ningún log de error.

> **⚠️ Python con `pyproject.toml`:** el reusable ejecuta `pip install -r <requirements-file>`. Si el proyecto no tiene `requirements.txt`, crear `backend/requirements-dev.txt` con el contenido `-e .[dev]` y pasar `requirements-file: requirements-dev.txt`.

> **⚠️ Directorio de tests:** el reusable ejecuta `pytest tests/unit/`. Los tests deben estar en `<service-dir>/tests/unit/`. Si están en `tests/` directamente, moverlos y actualizar `testpaths` en `pyproject.toml`.

### Implementación real — TRYCORE IA HUB (monorepo Python + React)

El repo [`trycore-ia-hub`](https://github.com/trycore-co/trycore-ia-hub) tiene dos wrappers, uno por servicio, con paths independientes para que solo se dispare el check del servicio que cambió:

- [`.github/workflows/pr-check-backend.yml`](https://github.com/trycore-co/trycore-ia-hub/blob/develop/.github/workflows/pr-check-backend.yml) — Python 3.14 · pytest · SonarQube · Trivy
- [`.github/workflows/pr-check-frontend.yml`](https://github.com/trycore-co/trycore-ia-hub/blob/develop/.github/workflows/pr-check-frontend.yml) — React 19 · Vitest · tsc · SonarQube · Trivy

### Guías completas

- [Implementar Pipeline en un repo](https://github.com/trycore-co/.github/blob/main/docs/IMPLEMENTAR-PIPELINE.md) — árbol de decisión · prompts listos para IA · errores frecuentes · crear job Jenkins
- [Guía técnica de Buenas Prácticas CI/CD](https://github.com/trycore-co/.github/blob/main/docs/BUENAS-PRACTICAS-PIPELINE.md) — referencia completa de todos los stacks
- [Código como Conocimiento](https://github.com/trycore-co/.github/blob/main/docs/CODIGO-COMO-CONOCIMIENTO.md) — auditoría automática de docs↔código: PR gate, merge audit con IA y audit trimestral

---

## Conocimiento vivo (Auditoría automática de docs)

> En proyectos donde el desarrollo lo aceleran agentes de IA, el código crece más rápido de lo que la documentación puede seguirlo manualmente. Esta capa lo resuelve automáticamente.

**El principio:** si un cambio no está en Git, no existe. Si está en Git, está verificado.

Tres capas automáticas que corren sobre el runner Jarvis:

| Cuándo corre | Qué hace | ¿Bloquea el pipeline? |
|---|---|---|
| Cada PR | Verifica que el código llegue con sus docs (Python, sin IA, <30s) | ✅ Sí |
| Cada merge a `main` | Analiza coherencia docs↔código con IA · Guarda knowledge snapshot | ❌ Abre issue |
| Primer día de cada trimestre | Audita ADRs, HUs y specs de API vs código real | ❌ Abre issue |

### Lo que ve el equipo

- **En el PR:** si falta documentación, el bot comenta con instrucciones claras. No es un error críptico — es una conversación.
- **Tras el merge:** Claude Haiku revisa el diff y reporta si los docs son coherentes con el código que llegó.
- **Trimestralmente:** Claude Sonnet revisa si las decisiones de arquitectura (ADRs), historias de usuario y contratos de API siguen siendo verdad en el código actual.

### Activar en un repo nuevo — 3 pasos

**1.** Copiar `scripts/ci/docs-coverage-check.py` al repo del proyecto.

**2.** Agregar el workflow usando el reusable de la org:

```yaml
# .github/workflows/docs-coverage-check.yml
name: Doc Coverage — PR Gate
on:
  pull_request:
    branches: [develop, main]
    paths: ['src/**', 'docs/**', 'openspec/**']
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
      code_zones: 'src/'
      doc_zones: 'docs/,openspec/'
    secrets: inherit
```

**3.** Agregar `ANTHROPIC_API_KEY` como secret del repo (para Capas 2 y 3) y activar `Doc Coverage Check` como required status check en branch protection.

> 📖 **Guía completa:** [Código como Conocimiento](https://github.com/trycore-co/.github/blob/main/docs/CODIGO-COMO-CONOCIMIENTO.md) — implementación paso a paso, preguntas frecuentes y costos estimados.

---

## Despliegue continuo con Jenkins (on-premise)

### Arquitectura del despliegue

```
GitHub Actions (runners públicos)        Jenkins (servidor interno)
────────────────────────────────         ─────────────────────────
Trigger: PR abierto                      Trigger: Poll SCM cada 2 min
Tests + SonarQube + Trivy                Checkout → Build Docker →
Gate de calidad = obligatorio            Deploy → Health check (4 min)
para hacer merge                         Rollback automático si falla
                                         Notifica Google Chat
```

Jenkins opera en la red interna del cliente **sin webhooks entrantes** — solo conexiones salientes. No puede reportar su resultado en GitHub, pero notifica a Google Chat en cada build.

### Qué necesita un repo para el despliegue automático

Cuatro artefactos en el repo y un paso manual en el servidor:

| Artefacto | Descripción |
|---|---|
| `Jenkinsfile` | Pipeline declarativo con los stages de build, deploy, health check y rollback |
| `docker-compose.dev.yml` | Define la red Docker aislada, volúmenes y el servicio de base de datos |
| `Dockerfile` (backend) | Build de la imagen del servicio |
| `Dockerfile.frontend` (si aplica) | Build multi-stage: bundler → nginx para la SPA |

Más un paso manual **previo al primer build**: crear el archivo `.env.dev` en el servidor con las variables de entorno del proyecto (ver abajo).

### Estructura del `Jenkinsfile`

```groovy
def GCHAT_CRED_ID = 'gchat-webhook-<proyecto>'
def APP_NAME      = '<nombre-app>'

pipeline {
    agent any
    options { timeout(time: 30, unit: 'MINUTES'); disableConcurrentBuilds() }
    environment {
        API_URL  = 'http://127.0.0.1:<puerto-backend>'
        ENV_FILE = '/home/trycore/Repositorios/<repo>/.env.dev'
        NETWORK  = '<proyecto>-dev-net'
    }
    stages {
        stage('Notificar inicio')           { /* gchatNotify */ }
        stage('Checkout rama')              { /* checkout SCM */ }
        stage('Infraestructura (postgres)') { /* docker compose up -d postgres */ }
        stage('Guardar imagen de rollback') { /* docker tag :latest :rollback */ }
        stage('Build backend')              { /* docker build -t ...:latest */ }
        stage('Build frontend')             { /* docker build --build-arg VITE_API_BASE_URL */ }
        stage('Desplegar')                  { /* docker rm -f + docker run -d */ }
        stage('Verificar salud')            { /* curl /health × 24 intentos (4 min) */ }
    }
    post {
        success { /* gchatNotify ✅ */ }
        failure { /* rollback automático + gchatNotify ❌ */ }
    }
}
```

### Variables de entorno en el servidor

El `.env.dev` vive en `/home/trycore/Repositorios/<repo>/.env.dev` en el servidor. **No se versiona** — se crea manualmente una vez antes del primer build. Usar el `.env.example` del repo como referencia.

Contenido mínimo para arrancar:

```env
ENVIRONMENT=development
AUTH_DEV_LOGIN=true                          # sin Google SSO en dev
CORS_ORIGINS=["http://<IP-servidor>:<puerto-frontend>"]
PUBLIC_API_BASE_URL=http://<IP-servidor>:<puerto-backend>
NOTIFICATIONS_ENABLED=false
```

Los secretos (`DATABASE_URL`, credenciales OIDC, SMTP) se pasan como `-e VAR=valor` en el `docker run` dentro del Jenkinsfile — **nunca** en el `.env.dev`.

### Crear el job en Jenkins — pasos

1. Navegar al **folder del proyecto** en Jenkins
2. **New Item** → nombre del job (ej: `deploy-ia-hub`) → **Pipeline** → OK
3. Configurar:
   - **Build Triggers:** Poll SCM → `H/2 * * * *`
   - **Pipeline → Definition:** Pipeline script from SCM
   - **SCM:** Git → URL del repo → credencial GitHub del servidor
   - **Branches:** `*/develop` (añadir `*/release/*`, `*/main` si aplica)
   - **Script Path:** `Jenkinsfile`
4. **Save** → **Build with Parameters** para el primer build manual

> ⚠️ **No declarar `triggers { pollSCM }` en el Jenkinsfile** si ya está configurado en la UI — genera builds duplicados.

### Credenciales necesarias en Jenkins

Crear en **Manage Jenkins → Credentials** antes del primer build:

| ID | Tipo | Descripción |
|---|---|---|
| *(credencial GitHub del servidor)* | Username/Password | Clonar repos privados de GitHub |
| `gchat-webhook-<proyecto>` | Secret Text | URL completa del webhook de Google Chat |

> Si la creación de credenciales por API falla con 403/500, usar **Manage Jenkins → Script Console** (Groovy) como alternativa sin CSRF. Ver la [política Jenkins](https://github.com/trycore-co/.github/blob/main/docs/jenkins-cicd-policy.md#34-crear-la-credencial-de-google-chat--trampa-del-csrf) para el snippet completo.

### Implementación real — TRYCORE IA HUB

El repo [`trycore-ia-hub`](https://github.com/trycore-co/trycore-ia-hub) está desplegado en `192.168.1.100` con este stack:

| Contenedor | Puerto | Imagen |
|---|---|---|
| `ia-hub-dev-postgres` | 5437 | `postgres:16-alpine` |
| `ia-hub-dev-backend` | 8100 | `ia-hub-backend-dev:latest` (Python 3.14 + FastAPI) |
| `ia-hub-dev-frontend` | 8101 | `ia-hub-frontend-dev:latest` (React 19 + nginx) |

Archivos de referencia:
- [`Jenkinsfile`](https://github.com/trycore-co/trycore-ia-hub/blob/develop/Jenkinsfile) — pipeline completo con rollback y notificaciones Google Chat
- [`docker-compose.dev.yml`](https://github.com/trycore-co/trycore-ia-hub/blob/develop/docker-compose.dev.yml) — red `ia-hub-dev-net` y volúmenes
- [`Dockerfile.frontend`](https://github.com/trycore-co/trycore-ia-hub/blob/develop/Dockerfile.frontend) — build multi-stage Vite → nginx
- [`backend/.env.example`](https://github.com/trycore-co/trycore-ia-hub/blob/develop/backend/.env.example) — referencia de todas las variables de entorno

### Guía completa

- [Jenkins CI/CD — Política de despliegue continuo](https://github.com/trycore-co/.github/blob/main/docs/jenkins-cicd-policy.md) — rollback, notificaciones, checklist completo, solución a errores frecuentes

---

## Stack habitual

- **Backend:** Python (FastAPI), Java (Spring Boot / JHipster), Node.js
- **BPM:** Bonita BPM
- **CI/CD:** GitHub Actions + SonarQube + Trivy · Jenkins on-premise
- **Infra:** Docker, Kubernetes, AWS, GCP

## Contacto

[trycore.com.co](https://trycore.com.co) · infraestructura@trycore.com
