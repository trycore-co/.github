# Jenkins CI/CD — Política de despliegue continuo
> **Aplica a:** proyectos Trycore donde Jenkins opera on-premise en la red del cliente.  
> **Complementa:** [Guía de Buenas Prácticas CI/CD](BUENAS-PRACTICAS-PIPELINE.md) — leer primero esa guía para GitHub Actions, SonarQube, Trivy y Jenkinsfile variables.  
> **Última actualización:** 2026-06-09

---

## 1. Por qué Jenkins + GitHub Actions

La arquitectura completa está documentada en [§1 de la Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md#1-arquitectura-del-pipeline). Resumen:

- **GitHub Actions** → validación en PRs (compile, unit tests, SonarQube, Trivy). Corre en runners públicos sin VPN.
- **Jenkins** → build Docker, deploy, health check, rollback. Corre on-premise en la red del cliente, **sin webhooks entrantes** — usa Poll SCM.

Jenkins nunca recibe webhooks de GitHub. Solo genera conexiones salientes (GitHub API para comentarios en commits, Google Chat webhook, SonarQube).

---

## 2. Modelo de ramas y deploys automáticos

| Rama | Ambiente | Reviews mínimos requeridos | Deploy automático Jenkins |
|------|----------|---------------------------|--------------------------|
| `feature/TICKET-descripcion` | — | — | No |
| `develop` | DEV | 1 líder técnico | Sí (Poll SCM) |
| `release/x.y.z` | QA / Cliente | 1 líder técnico | Sí (Poll SCM) |
| `main` | PROD | 2 líderes técnicos | Sí (Poll SCM) |

Configurar branch protection con estos reviewer mínimos. El único status check requerido para merge es el de GitHub Actions — Jenkins no es alcanzable desde GitHub para reportar su resultado. Ver [§12 de la Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md#12-checklist-para-un-proyecto-nuevo) para la configuración completa de branch protection.

---

## 3. Configuración del job en Jenkins

### 3.1 Job de pipeline principal

| Parámetro Jenkins | Valor |
|-------------------|-------|
| Tipo de item | **Pipeline** |
| Build Triggers | **Poll SCM**: `H/2 * * * *` |
| Pipeline definition | **Pipeline script from SCM** |
| SCM | Git, con credencial `dc32b146-e91d-4c10-8aac-acc1187846e2` |
| Branches | `*/develop`, `*/release/*`, `*/main` |
| Script Path | `Jenkinsfile` (raíz del repo) |

> ⚠️ Si el Poll SCM ya está configurado en la UI, **no** agregarlo también en el Jenkinsfile con `triggers { pollSCM }` — causa builds duplicados. Ver [§11.5 de la Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md#115-no-definir-triggers-en-el-jenkinsfile-si-ya-están-en-la-ui).

### 3.2 Credenciales requeridas en Jenkins

Crear en **Manage Jenkins → Credentials** antes de ejecutar cualquier pipeline:

| ID de credencial | Tipo | Descripción |
|-----------------|------|-------------|
| `dc32b146-e91d-4c10-8aac-acc1187846e2` | Username/Password | GitHub — clonar repos privados |
| `github-pat-<proyecto>` | Secret Text | GitHub PAT (scope: `repo`) — comentarios en commits |
| `gchat-webhook-<proyecto>` | Secret Text | URL webhook Google Chat del espacio del proyecto |
| `sonarqube` | SonarQube server config | Configurado en Manage Jenkins → Configure System |

El PAT de GitHub **no** es el mismo token que `SONAR_TOKEN` de GitHub Actions. Es un PAT separado con scope `repo` para que Jenkins pueda escribir comentarios en commits.

---

## 4. Estructura del Jenkinsfile

Las variables a ajustar por microservicio están documentadas en [§11.1 de la Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md#111-variables-a-ajustar-por-microservicio). El flujo de stages que todo Jenkinsfile Trycore debe tener:

```
Checkout SCM
  ↓
Unit Tests + reportes JUnit
  ↓
SonarQube analysis  (bloqueante: Quality Gate fallido detiene el pipeline)
  ↓
Build Docker image  (Jib para Maven, docker build para otros stacks)
  ↓
Guardar imagen como :rollback  ← siempre antes del deploy
  ↓
Deploy (docker compose up)
  ↓
Health check (24 × 10s = 4 min máximo)
  ├── PASS → Notificación éxito (Google Chat + comentario en commit)
  └── FAIL → Auto-rollback → Notificación fallo
```

> **Tests en Jenkins**: los tests ya corrieron en GitHub Actions durante el PR. No repetirlos en Jenkins en cada deploy a `develop` — solo ejecutar unit tests cuando el trigger es un merge nuevo o un build manual. Los tests de integración que requieren infraestructura (BD real, Kafka, etc.) sí pueden correr en Jenkins si el ambiente DEV los soporta.

---

## 5. Estrategia de rollback

### 5.1 Rollback automático (integrado en el Jenkinsfile)

Antes de cada deploy, guardar la imagen actual:

```groovy
sh "docker tag ${APP_NAME}:latest ${APP_NAME}:rollback 2>/dev/null || true"
```

Si el health check falla después del deploy, el pipeline restaura automáticamente:

```groovy
sh """
  docker stop ${APP_NAME} || true
  docker rm ${APP_NAME} || true
  docker tag ${APP_NAME}:rollback ${APP_NAME}:latest
  docker compose -f docker-compose.yml up -d ${APP_NAME}
"""
```

El deploy se marca `FAILURE` y se envía notificación con el motivo.

### 5.2 Rollback manual rápido — imagen `:rollback`

Job Jenkins separado: `<proyecto>-rollback-<servicio>`. Restaura la imagen `:rollback` sin reconstruir. Tiempo: segundos.

Usar cuando: el pipeline automático no completó el rollback, o se necesita revertir manualmente tras un deploy exitoso que el cliente rechaza.

### 5.3 Rollback profundo — SHA de commit

Mismo job de rollback con parámetro `GIT_SHA`. Reconstruye la imagen desde ese commit específico. Tiempo: 10–15 minutos.

Usar cuando: la imagen `:rollback` no está disponible (servidor reiniciado, Docker purgado).

### 5.4 Limitación crítica — migraciones de BD

> **El rollback de imagen NO revierte la base de datos.**

Las migraciones Liquibase/Flyway deben ser **aditivas**: nunca eliminar una columna en el mismo deploy que la reemplaza. Si un deploy incluye eliminación de columnas, el rollback de BD debe planificarse como operación separada con el DBA.

---

## 6. Notificaciones

Todo pipeline debe notificar al terminar (éxito o fallo) en dos canales:

### 6.1 Google Chat

Via webhook configurado en Jenkins credentials (`gchat-webhook-<proyecto>`). El mensaje debe incluir: nombre del servicio, rama desplegada, resultado (✅/❌), URL del build Jenkins.

```groovy
def message = "${result == 'SUCCESS' ? '✅' : '❌'} *${APP_NAME}* — rama `${env.BRANCH_NAME}` — ${result}\n${env.BUILD_URL}"
sh "curl -s -X POST '${GCHAT_WEBHOOK}' -H 'Content-Type: application/json' -d '{\"text\": \"${message}\"}'"
```

Para la configuración del webhook ver `integrations/google-chat-setup.md`.

### 6.2 Comentario en el commit de GitHub

Via GitHub API usando el PAT (`github-pat-<proyecto>`). Permite trazabilidad directa desde el historial de commits al resultado del build.

```groovy
def commitSha = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
def body = "{\"body\": \"CI/CD: ${result} — [Ver build](${env.BUILD_URL})\"}"
sh "curl -s -X POST -H 'Authorization: token ${GH_PAT}' https://api.github.com/repos/${GITHUB_REPO}/commits/${commitSha}/comments -d '${body}'"
```

---

## 7. Checklist — activar Jenkins CI/CD en un proyecto nuevo

- [ ] Crear job Pipeline en Jenkins (ver §3.1)
- [ ] Crear credenciales en Jenkins: GitHub credential, GitHub PAT, Google Chat webhook, SonarQube (ver §3.2)
- [ ] Crear job de rollback separado por servicio (ver §5.2)
- [ ] Copiar template de Jenkinsfile según stack (Maven/Angular/Go) y ajustar variables (ver [§11 de la Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md#11-jenkinsfile--reglas-generales))
- [ ] Crear proyecto en SonarQube (`docs.trycore.co:9000`) con el project key del Jenkinsfile
- [ ] Verificar primera notificación a Google Chat en el build inicial
- [ ] Verificar que el comentario aparece en el commit de GitHub tras el build
- [ ] Verificar que el rollback automático funciona: hacer un deploy fallido a propósito en DEV y confirmar que revierte

---

## 8. Templates

Los Jenkinsfiles listos por tecnología están en el repositorio de estrategia CI/CD de cada proyecto (`templates/jenkins/`):

| Archivo | Stack |
|---------|-------|
| `Jenkinsfile.maven` | Java/Spring Boot (JHipster) |
| `Jenkinsfile.angular` | Frontend Angular |
| `Jenkinsfile.go` | Servicios Go |
| `Jenkinsfile.rollback` | Job de rollback manual (dos estrategias) |

---

*Documento mantenido por el equipo de infraestructura Trycore. Para cambios o excepciones, abrir una discusión en este repositorio.*
