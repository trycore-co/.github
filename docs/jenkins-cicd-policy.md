# Jenkins CI/CD — Política de despliegue continuo
> **Aplica a:** proyectos Trycore donde Jenkins opera on-premise en la red del cliente.  
> **Complementa:** [Guía de Buenas Prácticas CI/CD](BUENAS-PRACTICAS-PIPELINE.md) — leer primero esa guía para GitHub Actions, SonarQube, Trivy y Jenkinsfile variables.  
> **Última actualización:** 2026-06-17

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

### 3.1 Job de pipeline principal — parámetros

| Parámetro Jenkins | Valor |
|-------------------|-------|
| Tipo de item | **Pipeline** |
| Build Triggers | **Poll SCM**: `H/2 * * * *` |
| Pipeline definition | **Pipeline script from SCM** |
| SCM | Git, con la credencial GitHub del servidor Jenkins (ver §3.2) |
| Branches | `*/develop`, `*/release/*`, `*/main` |
| Script Path | `Jenkinsfile` (raíz del repo) |

> ⚠️ Si el Poll SCM ya está configurado en la UI, **no** agregarlo también en el Jenkinsfile con `triggers { pollSCM }` — causa builds duplicados. Ver [§11.5 de la Guía de Buenas Prácticas](BUENAS-PRACTICAS-PIPELINE.md#115-no-definir-triggers-en-el-jenkinsfile-si-ya-están-en-la-ui).

### 3.2 Credenciales requeridas en Jenkins

Crear en **Manage Jenkins → Credentials → System → Global credentials** antes de ejecutar cualquier pipeline:

| ID de credencial | Tipo | Descripción |
|-----------------|------|-------------|
| *(ver §3.3 para obtener el ID real)* | Username/Password | GitHub — clonar repos privados |
| `github-pat-<proyecto>` | Secret Text | GitHub PAT (scope: `repo`) — comentarios en commits |
| `gchat-webhook-<proyecto>` | Secret Text | URL completa del webhook de Google Chat del proyecto |
| `sonarqube` | SonarQube server config | Configurado en Manage Jenkins → Configure System |

El PAT de GitHub **no** es el mismo token que `SONAR_TOKEN` de GitHub Actions. Es un PAT separado con scope `repo` para que Jenkins pueda escribir comentarios en commits.

### 3.3 Crear el job en Jenkins — paso a paso en la UI

> Este proceso se hace **una vez por proyecto**, desde la UI de Jenkins.

> ⚠️ **Crear siempre dentro del folder correcto.** En Jenkins la ruta del job forma parte de su URL y de los reportes. Si el job se crea en el folder equivocado (ej: directamente en `Trycore/` en vez de `Trycore/DocflySaaS/`), hay que recrearlo — los jobs no se mueven, solo se eliminan y vuelven a crear. Ver §9.1.

1. Entrar a Jenkins y navegar al **folder del proyecto** (ej: `Trycore → DocflySaaS`)
2. Click en **"New Item"** (panel izquierdo)
3. Escribir el nombre del job (ej: `deploy-ia-hub`) → seleccionar **"Pipeline"** → OK
4. Configurar:
   - **General → Description:** descripción breve
   - **Build Triggers:** marcar **"Poll SCM"** → campo Schedule: `H/2 * * * *`
   - **Pipeline → Definition:** `Pipeline script from SCM`
   - **SCM:** `Git`
   - **Repository URL:** URL HTTPS del repo (ej: `https://github.com/trycore-co/<repo>.git`)
   - **Credentials:** seleccionar la credencial GitHub existente en el servidor (ir a Manage Jenkins → Credentials para ver los IDs disponibles)
   - **Branches to build:** `*/develop` — añadir `*/release/*` y `*/main` si aplica
   - **Script Path:** `Jenkinsfile`
5. **Save** → verificar con un build manual: **Build with Parameters** → ejecutar

> ⚠️ Los IDs de credencial del Jenkinsfile deben coincidir **exactamente** con los IDs registrados en Jenkins. Si copias un Jenkinsfile de otro proyecto, revisa el ID de la credencial de GitHub y el de Google Chat antes del primer build.
>
> ⚠️ **Crear las credenciales ANTES del primer build.** Si `gchat-webhook-<proyecto>` o `github-pat-<proyecto>` no existen cuando corre el pipeline, el bloque `post { failure }` falla silenciosamente al intentar notificar — el pipeline reporta error pero no queda claro el motivo. La sección de notificaciones tiene `try/catch` para que no tumbe el resultado, pero el build ya se marcó como fallo antes. Ver §9.2.

### 3.4 Crear la credencial de Google Chat — trampa del CSRF

La API REST de Jenkins usa **CSRF tokens (crumb) vinculados a la sesión HTTP**. Si obtienes el crumb en un request y lo usas en otro sin compartir la cookie de sesión, Jenkins devuelve 403 o 500 sin mensaje útil.

**Opción A — curl con sesión compartida (flags `-c` y `-b`):**

```bash
# Paso 1: obtener crumb Y guardar la cookie de sesión
CRUMB=$(curl -s -u "admin:PASSWORD" -c /tmp/j.txt \
  "http://<jenkins>/crumbIssuer/api/json" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['crumb'])")

# Paso 2: crear la credencial usando LA MISMA cookie
curl -s -u "admin:PASSWORD" \
  -b /tmp/j.txt -c /tmp/j.txt \
  -H "Jenkins-Crumb: $CRUMB" \
  -X POST "http://<jenkins>/credentials/store/system/domain/_/createCredentials" \
  --data-urlencode 'json={
    "": "0",
    "credentials": {
      "scope": "GLOBAL",
      "id": "gchat-webhook-<proyecto>",
      "secret": "https://chat.googleapis.com/v1/spaces/...",
      "description": "Google Chat webhook — <proyecto>",
      "$class": "org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl"
    }
  }'
```

**Opción B — Script Console de Groovy (más confiable, sin CSRF):**

Jenkins → **Manage Jenkins → Script Console** → ejecutar:

```groovy
import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.*
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import hudson.util.Secret

def cred = new StringCredentialsImpl(
    CredentialsScope.GLOBAL,
    'gchat-webhook-<proyecto>',
    'Google Chat webhook — <proyecto>',
    Secret.fromString('https://chat.googleapis.com/v1/spaces/...')
)
SystemCredentialsProvider.getInstance()
    .getStore()
    .addCredentials(Domain.global(), cred)
println "OK"
```

Verificar en **Manage Jenkins → Credentials** que la nueva credencial aparece antes de ejecutar el pipeline.

### 3.5 Archivo `.env` en el servidor — configuración previa al primer deploy

El `Jenkinsfile` de cada proyecto apunta a un archivo de variables de entorno en el servidor de desarrollo. **Este archivo no se crea automáticamente** — debe crearse manualmente en el servidor antes del primer build.

Ubicación estándar:
```
/home/trycore/Repositorios/<nombre-repo>/.env.dev
```

Crear el directorio y el archivo en el servidor:

```bash
ssh trycore@<IP-servidor>
mkdir -p /home/trycore/Repositorios/<nombre-repo>
nano /home/trycore/Repositorios/<nombre-repo>/.env.dev
```

Contenido mínimo para que el backend arranque en modo desarrollo:

```env
ENVIRONMENT=development
AUTH_DEV_LOGIN=true
CORS_ORIGINS=["http://<IP-servidor>:<puerto-frontend>"]
PUBLIC_API_BASE_URL=http://<IP-servidor>:<puerto-backend>
ATTACHMENTS_DIR=/data/attachments
NOTIFICATIONS_ENABLED=false
```

> Las variables secretas (`DATABASE_URL`, credenciales Google OIDC, SMTP) se pasan directamente como `-e VAR=valor` en el `docker run` del Jenkinsfile, **no** en el `.env.dev`. Así los secretos nunca tocan el sistema de archivos del servidor.
>
> Usar el `.env.example` del repo como referencia completa de todas las variables disponibles.

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

**Preparación previa (hacer antes de tocar Jenkins):**
- [ ] El repo tiene `Jenkinsfile` en la raíz con los stages correctos
- [ ] El repo tiene `docker-compose.dev.yml` con la red y los volúmenes del proyecto
- [ ] El repo tiene `Dockerfile` (backend) y `Dockerfile.frontend` (si aplica) en la raíz o en el directorio del servicio
- [ ] Crear el archivo `.env.dev` en el servidor (ver §3.5) con las variables mínimas de arranque

**En Jenkins:**
- [ ] Crear credencial GitHub (Username/Password) si no existe para este servidor (ver §3.2)
- [ ] Crear credencial `gchat-webhook-<proyecto>` (Secret Text) con el webhook de Google Chat (ver §3.4)
- [ ] Crear el job Pipeline dentro del folder del proyecto (ver §3.3)
- [ ] Configurar Poll SCM `H/2 * * * *` en el job
- [ ] Ejecutar el primer build manualmente con **Build with Parameters**
- [ ] Verificar que el build llega al stage "Verificar salud" y el health check responde `ok`
- [ ] Verificar que Google Chat recibe la notificación de éxito

**Validación post-activación:**
- [ ] Hacer un push a `develop` y confirmar que Jenkins detecta el cambio en ≤ 2 min (Poll SCM)
- [ ] Verificar que el rollback automático funciona: forzar un fallo en el health check y confirmar que el pipeline restaura la imagen anterior y notifica
- [ ] Crear proyecto en SonarQube (`docs.trycore.co:9000`) si el Jenkinsfile incluye análisis de calidad

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

## 9. Errores frecuentes y soluciones

Esta sección recoge errores reales ocurridos en despliegues Trycore. Cada caso incluye síntoma, causa raíz y solución.

---

### 9.1 Job creado en la carpeta incorrecta

**Síntoma:** El job existe pero está en una ruta diferente a la esperada (ej: `Trycore/deploy-docfly-core` en vez de `Trycore/DocflySaas/deploy-docfly-core`). Los reportes de Poll SCM y las URLs de notificación apuntan a la ruta incorrecta.

**Causa:** Se creó el item con "New Item" estando en el folder padre en vez del subfolder del proyecto.

**Solución:** Los jobs en Jenkins no se pueden mover. Hay que:
1. Anotar la configuración del job incorrecto (URL del repo, credencial, Script Path, ramas)
2. Eliminarlo: entrar al job → panel izquierdo → **"Delete Pipeline"**
3. Crear el job nuevo desde el folder correcto siguiendo §3.3

---

### 9.2 Pipeline falla con error de checkout en el primer build (o tras múltiples commits rápidos)

**Síntoma:** El stage `Checkout` falla con `ERROR: Error fetching remote repo 'origin'` o exit code 128. Builds posteriores al mismo commit también fallan.

**Causa A — Poll SCM disparó múltiples builds simultáneos:** Si se hacen varios commits en poco tiempo, el Poll SCM puede encolar varios builds. Con `disableConcurrentBuilds()`, los builds se ejecutan en secuencia, pero si el primer build está haciendo `git fetch` cuando arranca el segundo, GitHub puede responder con rate-limit (exit code 128).

**Causa B — Repositorio privado sin credencial configurada:** La credencial GitHub no está asignada al job o el ID no coincide con el del Jenkinsfile.

**Solución:**
- Verificar que el Jenkinsfile tiene `disableConcurrentBuilds()` en el bloque `options {}`.
- Esperar que los builds en cola terminen y lanzar un build manual limpio con **Build with Parameters**.
- Si persiste, revisar que la credencial GitHub del job (campo *Credentials* en la configuración) existe en Jenkins y que su ID coincide con `GH_CRED_ID` en el Jenkinsfile.

---

### 9.3 Credenciales de notificación no existen — pipeline falla en `post`

**Síntoma:** El deploy y el health check pasan correctamente, pero el pipeline termina en `FAILURE`. En el console log aparece algo como `org.jenkinsci.plugins.credentialsbinding.impl.CredentialNotFoundException` en el bloque `post`.

**Causa:** Las credenciales `gchat-webhook-<proyecto>` y/o `github-pat-<proyecto>` no fueron creadas en Jenkins antes del primer build.

**Solución:** Crear ambas credenciales siguiendo §3.4 (Script Console de Groovy es el método más confiable). Verificar en **Manage Jenkins → Credentials** que aparecen con el ID exacto que usa el Jenkinsfile. Luego relanzar el build.

---

### 9.4 Contenedores PostgreSQL salen inmediatamente (exit code 1) con postgres:17+

**Síntoma:** Los contenedores de PostgreSQL arrancan y mueren en segundos. `docker logs <contenedor>` muestra:
```
initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
```
o simplemente el contenedor sale sin mensaje de error.

**Causa:** A partir de **postgres:17**, el directorio de datos por defecto dentro del contenedor cambió de `/var/lib/postgresql/data` a `/var/lib/postgresql`. Los volúmenes del `docker-compose.yml` que apuntan a `/var/lib/postgresql/data` dejan de funcionar con estas imágenes.

**Solución:** Actualizar el mount del volumen en el `docker-compose.yml`:

```yaml
# ❌ Incorrecto para postgres:17+
volumes:
  - pg_data:/var/lib/postgresql/data

# ✅ Correcto para postgres:17+
volumes:
  - pg_data:/var/lib/postgresql
```

Si ya existen volúmenes con datos del stack anterior, es necesario eliminarlos antes de recrear los contenedores (previa confirmación de que los datos son recuperables o prescindibles en DEV):
```bash
docker volume rm <proyecto>_gateway_pg_data <proyecto>_core_pg_data ...
```

---

### 9.5 Build del gateway falla con `GLIBC_2.28 not found` — Node.js en servidores Ubuntu 18.04

**Síntoma:** El stage `Build imagen (Jib)` falla durante `npm install` con:
```
/path/to/node: /lib/x86_64-linux-gnu/libc.so.6: version 'GLIBC_2.28' not found
```

**Causa:** El servidor Jenkins corre Ubuntu 18.04 LTS (glibc 2.27). A partir de Node.js 18, los binarios oficiales de `nodejs.org` se compilan contra RHEL 8 (glibc 2.28) — ninguna versión de Node.js 18, 20 o 24 puede ejecutarse directamente en Ubuntu 18.04. El `frontend-maven-plugin` descarga el binario oficial de Node y lo ejecuta en el host, encontrando la incompatibilidad.

**Solución:** Ejecutar el build Maven completo dentro de un contenedor con glibc reciente, usando `jib:buildTar` en vez de `jib:dockerBuild` (buildTar no necesita el socket Docker — genera un tar que se carga con `docker load`):

```groovy
stage('Build imagen (Jib)') {
  steps {
    dir("${env.SERVICE_DIR}") {
      sh '''
        chmod +x mvnw
        docker run --rm \
          -v "$(pwd)":/workspace \
          -v /var/lib/jenkins/.m2:/root/.m2 \
          -w /workspace \
          eclipse-temurin:21-jdk-jammy \
          ./mvnw -ntp -B -Pprod package -DskipTests jib:buildTar
        LOADED=$(docker load -i target/jib-image.tar | awk '/Loaded image/{print $NF}')
        docker tag "$LOADED" "${APP_NAME}:latest"
      '''
    }
  }
}
```

`eclipse-temurin:21-jdk-jammy` usa Ubuntu 22.04 (glibc 2.35) y soporta cualquier versión de Node.js. El cache Maven del host (`/var/lib/jenkins/.m2`) se monta para no re-descargar dependencias en cada build.

> **Nota:** si en el stage de rollback se usa `jib:dockerBuild` en otro proyecto del mismo servidor, también deberá migrar a este patrón.

---

### 9.6 Timezone de contenedores en UTC — logs y timestamps incorrectos

**Síntoma:** Los logs de los contenedores muestran timestamps en UTC aunque el servidor está en `America/Bogota`. Esto dificulta correlacionar logs con eventos reportados por usuarios.

**Causa:** Docker no hereda el timezone del host. Por defecto todos los contenedores usan UTC.

**Solución:** Agregar estos dos volúmenes a **todos** los servicios del `docker-compose.yml`:

```yaml
volumes:
  - /etc/timezone:/etc/timezone:ro
  - /etc/localtime:/etc/localtime:ro
```

Recrear los contenedores después del cambio:
```bash
docker compose -p <proyecto> -f docker-compose.yml up -d --force-recreate
```

Verificar: `docker exec <contenedor> date` debe mostrar la hora en la zona correcta.

---

### 9.7 Keycloak no reimporta el realm al reiniciar — usuarios sin roles

**Síntoma (aplica a proyectos JHipster):** El realm existe y los usuarios pueden autenticarse, pero al intentar acceder a la aplicación aparece *"No tiene permisos para acceder a la página"*. Los usuarios del realm no tienen grupos (`ROLE_ADMIN`, `ROLE_USER`) asignados aunque el `realm.json` del repo sí los define.

**Causa:** Keycloak con `start-dev --import-realm` usa estrategia `SKIP` por defecto: si el realm ya existe en el volumen interno, **no reimporta**. Si el contenedor fue recreado desde una imagen o volumen anterior donde los grupos no estaban configurados, la asignación de grupos no se aplica.

**Solución inmediata** (sin reiniciar Keycloak):
```bash
# Obtener el ID del usuario
USER_ID=$(docker exec <keycloak-container> /opt/keycloak/bin/kcadm.sh \
  config credentials --server http://localhost:9080 --realm master \
  --user admin --password admin 2>/dev/null && \
  docker exec <keycloak-container> /opt/keycloak/bin/kcadm.sh \
  get users -r jhipster -q username=admin | python3 -c \
  "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# Agregar al grupo Admins (ajustar el ID del grupo al del realm)
docker exec <keycloak-container> /opt/keycloak/bin/kcadm.sh \
  update users/$USER_ID/groups/<group-id> -r jhipster
```

**Solución permanente:** Verificar que el `realm.json` del repo ya tiene los usuarios con el campo `"groups": ["/Admins", "/Users"]`. Si es correcto, el problema solo ocurre con volúmenes de instancias anteriores — un ambiente DEV fresco desde cero importará correctamente.

Para forzar reimportación: eliminar el volumen interno de Keycloak (`dev-file`) y recrear el contenedor.

---

*Documento mantenido por el equipo de infraestructura Trycore. Para cambios o excepciones, abrir una discusión en este repositorio.*
