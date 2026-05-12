# Buenas Prácticas — Pipelines CI/CD
**Referencia:** Lecciones aprendidas en los proyectos COBRA Contratos (primer piloto) y DocFly Páginas.
**Aplica a:** Todos los microservicios y frontends con GitHub Actions + SonarQube + Trivy.

---

## Guía para IA — Cómo generar un workflow desde este documento

> **Contexto org trycore-co:** `SONAR_TOKEN` y `SONAR_HOST_URL` ya están configurados como secret y variable de organización respectivamente — **no se configuran por repo**. Para nuevos proyectos Python en la org, usar el wrapper de §16.4 (20 líneas) en lugar de copiar el template completo de §5. Para otros stacks (Java, React, Angular) seguir usando los templates de §4/§6/§7 por ahora — los reusable workflows para esos stacks están pendientes.
>
> **¿Vas a implementar el pipeline en un repo nuevo o a migrar uno existente?** Usa la [Guía de Implementación](IMPLEMENTAR-PIPELINE.md) — tiene los prompts listos para darle a una IA y el árbol de decisión para saber qué caso aplica.

Antes de generar el workflow, responde estas preguntas y sustituye los valores en el template:

| Pregunta | Variable en el template |
|---|---|
| ¿Cuál es el nombre del servicio? | `NombreServicio` |
| ¿Es un repo de org trycore-co con stack Python? | Sí → usar wrapper §16.4 (no copiar template completo) |
| ¿Cuál es el stack? | Elige §4 Java, §5 Python, §6 React/Vite, §7 Angular — si es monorepo ver §15 |
| ¿Cuál es el project key en SonarQube CI? | `SONAR_PROJECT_KEY` (formato: `Proyecto:NombreServicio`) |
| ¿Qué ramas disparan el check? | `branches:` en el trigger |
| ¿El test runner produce XML de JUnit? | Ruta en `report_paths` del step mikepenz |
| ¿El proyecto genera cobertura? | Tipo y ruta del reporte (ver §tabla abajo) |
| ¿Hay archivos legítimos a excluir de cobertura? | Ver §3.5 |
| ¿Qué dirs ignorar en Trivy? | Ver §9.1 |

**Tabla rápida por stack:**

| Stack | Test command | XML path | Coverage command | Coverage report para Sonar |
|---|---|---|---|---|
| Java/Maven | `./mvnw -B test sonar:sonar` | `**/target/surefire-reports/*.xml` | Jacoco (integrado en Maven) | `-Dsonar.coverage.jacoco.xmlReportPaths=target/site/**/jacoco*.xml` |
| Python/pytest | `pytest tests/unit/ --junitxml=test-results.xml --cov=src --cov-report=xml` | `test-results.xml` | `--cov-report=xml:coverage.xml` | `-Dsonar.python.coverage.reportPaths=coverage.xml` |
| React/Vitest | `npm run test -- --reporter=junit --outputFile=test-results.xml --coverage --pool=vmForks` | `test-results.xml` | `--coverage` (istanbul, genera `coverage/lcov.info`) | `-Dsonar.javascript.lcov.reportPaths=coverage/lcov.info` |
| Angular/Karma | `npm test -- --watch=false --browsers=ChromeHeadless --code-coverage` | `reports/junit.xml` | `--code-coverage` (genera `coverage/lcov.info`) | `-Dsonar.javascript.lcov.reportPaths=coverage/lcov.info` |

**Regla de sustitución en templates:**
- Reemplaza `NombreServicio` con el nombre real (ej: `Páginas Backend`)
- Reemplaza `Proyecto:NombreServicio` con el project key real (ej: `Docfly:Paginas-Backend`)
- Reemplaza `DIRS_TRIVY` con los dirs de la tabla de §9.1
- Los bloques marcados como `# ── Bloque Sonar Summary (§3.2) ──` deben copiarse literalmente de §3.2

---

## Índice

1. [Arquitectura del pipeline](#1-arquitectura-del-pipeline)
2. [GitHub Actions — Reglas generales](#2-github-actions--reglas-generales)
3. [Patrones ricos del PR Summary](#3-patrones-ricos-del-pr-summary)
4. [Stack: Java / Maven / JHipster](#4-stack-java--maven--jhipster)
5. [Stack: Python / FastAPI / pytest](#5-stack-python--fastapi--pytest)
6. [Stack: React / Vite / Vitest](#6-stack-react--vite--vitest)
7. [Stack: Angular / Node.js](#7-stack-angular--nodejs)
8. [SonarQube — Configuración](#8-sonarqube--configuración)
9. [Trivy SCA — Configuración](#9-trivy-sca--configuración)
10. [sonar-project.properties](#10-sonar-projectproperties)
11. [Jenkinsfile — Reglas generales](#11-jenkinsfile--reglas-generales)
12. [Checklist para un proyecto nuevo](#12-checklist-para-un-proyecto-nuevo)
13. [Tests E2E — Playwright vs Cypress](#13-tests-e2e--playwright-vs-cypress)
14. [OWASP Top 10 — Cobertura por el pipeline](#14-owasp-top-10--cobertura-por-el-pipeline)
15. [Monorepo con múltiples microservicios](#15-monorepo-con-múltiples-microservicios)
16. [Distribución org-level y reusable workflows](#16-distribución-org-level--repo-trycore-cogithub)
    - [16.6.2 Regla — nunca poner env vars de proyecto en un reusable](#1662-regla--nunca-poner-env-vars-de-proyecto-en-un-reusable-workflow)
    - [16.6.3 Regla — Quality Gate continue-on-error nunca en el reusable](#1663-regla--quality-gate-continue-on-error-nunca-en-el-reusable)
    - [16.6.4 Tabla — qué va en el reusable vs en el wrapper caller](#1664-tabla--qué-va-en-el-reusable-vs-en-el-wrapper-caller)
    - [16.6.5 Lección aprendida — Quality Gate UNKNOWN por whitespace en SONAR_HOST_URL](#1665-lección-aprendida--quality-gate-unknown-por-whitespace-en-sonar_host_url)
    - [16.7 Migración de repo existente al wrapper reusable](#167-migración-de-un-repo-existente-al-wrapper-reusable)
17. [Monorepo front + backend](#17-monorepo-front--backend)

---

## 1. Arquitectura del pipeline

```
GitHub Actions (runners públicos)     Jenkins (servidor interno — VPN)
─────────────────────────────────     ────────────────────────────────
Trigger: PR abierto                   Trigger: Poll SCM H/2 * * * *
                                       (NO webhooks — Jenkins no es público)
  Compile + Unit Tests                  Checkout
  SonarQube Quality Gate                Build imagen Docker (Jib / Docker build)
  Trivy SCA                             Deploy (docker compose up)
                                        Health check (24 × 10s)
Gate de calidad = obligatorio           Rollback automático si falla
para hacer merge                        Notifica Google Chat + GitHub
                                        [opcional] E2E Tests post-deploy
                                        (Playwright o Cypress vs staging)
```

**Regla fundamental:** GitHub Actions es el guardián de calidad. Jenkins solo despliega. Los tests nunca se repiten en Jenkins — ya corrieron en el PR.

**Tests E2E:** No corren en el PR check de GitHub Actions porque requieren la app levantada completa (frontend + backend + BD). Se ejecutan en dos momentos: localmente por el desarrollador antes de hacer PR, y/o en Jenkins post-deploy contra el ambiente de staging. Ver §13.

---

## 2. GitHub Actions — Reglas generales

### 2.1 Trigger correcto

```yaml
on:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
```

No usar `push` para los checks de calidad. El `push` a `release/CI_CD` es solo para desarrollo del pipeline mismo — quitarlo cuando el proyecto esté en producción.

**No agregar `feature/**` ni `feat/**` al trigger.** El PR check solo debe correr cuando el código va a integrarse a una rama estable (`develop`, `release/**`, `main`). Correrlo en cada push a ramas de feature consume minutos de GitHub Actions innecesariamente y genera ruido — los developers deben correr los tests localmente mientras desarrollan.

Algunos backends necesitan `workflow_dispatch` además del `pull_request` para poder correr manualmente:

```yaml
on:
  workflow_dispatch:
  pull_request:
    branches: [...]
```

### 2.2 Separar jobs por responsabilidad

Cada check debe ser un job independiente para que en el PR se vea claramente qué pasó y qué falló:

| Job | Nombre del check | Bloquea merge |
|---|---|---|
| `build-test-sonar` | `Build, Tests & SonarQube` o `Tests & SonarQube` | Sí |
| `sca-trivy` | `SCA — Trivy` | Sí (cuando esté maduro) |

### 2.3 Permisos explícitos siempre

Sin esto, `mikepenz/action-junit-report` falla con 403:

```yaml
jobs:
  build-test-sonar:
    permissions:
      checks: write      # Requerido para publicar resultados de tests en el PR
      contents: read
```

El job de Trivy necesita:

```yaml
  sca-trivy:
    permissions:
      security-events: write   # Para subir SARIF a GitHub Security
      actions: read
      contents: read
```

### 2.4 Timeouts siempre

```yaml
timeout-minutes: 30   # build-test-sonar (incluye SonarQube)
timeout-minutes: 10   # sca-trivy
```

Sin timeout, un runner colgado consume minutos de GitHub Actions indefinidamente.

### 2.5 Variables de entorno globales del workflow

Declarar las variables que se repiten en múltiples steps a nivel `env:` del workflow:

```yaml
env:
  SONAR_PROJECT_KEY: 'Proyecto:NombreServicio'
```

Así los steps usan `${{ env.SONAR_PROJECT_KEY }}` en lugar de repetir el valor.

---

## 3. Patrones ricos del PR Summary

El PR mostrará un resumen en la pestaña **Summary** del workflow. Se construye con 4 bloques. El resultado visible es:

```
┌─────────────────────────────────────────────────────┐
│  🧪 Unit Tests — NombreServicio                     │
│     ✅ 172 passed / 0 failed                        │
│  🔍 SonarQube — ✅ PASSED                           │
│     Coverage: 82.3%  Bugs: 0  Vulnerabilidades: 0   │
│     [📊 Ver análisis completo en SonarQube]         │
│  🛡️ SCA — Trivy — ✅ Sin vulnerabilidades CRITICAL  │
│     🔴 Critical: 0  🟠 High: 0  🟡 Medium: 3        │
└─────────────────────────────────────────────────────┘
```

### 3.1 Bloque: JUnit test report (mikepenz)

Siempre agregar un encabezado manual antes de la acción `mikepenz`, que agrega la tabla de tests automáticamente:

```yaml
- name: Encabezado Unit Tests en summary
  if: always()
  run: |
    echo "## 🧪 Unit Tests — NombreServicio" >> "$GITHUB_STEP_SUMMARY"
    echo "" >> "$GITHUB_STEP_SUMMARY"

- name: Publicar resultados de tests
  uses: mikepenz/action-junit-report@v4
  if: always()
  with:
    report_paths: 'RUTA_XML'               # ver tabla rápida al inicio
    check_name: 'Unit Tests — NombreServicio'
```

El `if: always()` es obligatorio — si los tests fallan, el paso siguiente no se ejecutaría sin él.

### 3.2 Bloque: SonarQube metrics summary

Después del análisis, consultar la API de SonarQube para obtener las métricas reales y pintarlas en el summary. SonarQube tarda ~30s en procesar — el loop de polling espera hasta 60s.

> **Nota:** La ruta `.scannerwork/report-task.txt` es la misma para todos los stacks — el scanner la genera siempre en el mismo lugar.

```yaml
- name: Resumen SonarQube en Actions
  if: always()
  env:
    SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
    SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
  run: |
    REPORT=".scannerwork/report-task.txt"
    if [ ! -f "$REPORT" ]; then
      echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
      echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
      exit 0
    fi

    DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
    CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)

    for i in $(seq 1 12); do
      TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
        "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
      if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
        break
      fi
      sleep 5
    done

    QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
      "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ env.SONAR_PROJECT_KEY }}" 2>/dev/null || echo "{}")
    QG_STATUS=$(echo "$QG_JSON" | python3 -c \
      "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")

    METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
      "$SONAR_HOST_URL/api/measures/component?component=${{ env.SONAR_PROJECT_KEY }}&metricKeys=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots" 2>/dev/null || echo "{}")

    parse_metric() {
      echo "$METRICS_JSON" | python3 -c \
        "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
    }

    COVERAGE=$(parse_metric coverage)
    DUPLICATIONS=$(parse_metric duplicated_lines_density)
    BUGS=$(parse_metric bugs)
    VULNERABILITIES=$(parse_metric vulnerabilities)
    CODE_SMELLS=$(parse_metric code_smells)
    SEC_HOTSPOTS=$(parse_metric security_hotspots)

    if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
    elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
    else                                  QG_BADGE="⚠️ $QG_STATUS"
    fi

    cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
    ## 🔍 SonarQube — $QG_BADGE

    | Métrica | Valor | Umbral |
    |---------|-------|--------|
    | Quality Gate | $QG_BADGE | — |
    | Coverage | ${COVERAGE}% | ≥ 80% |
    | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
    | Bugs | $BUGS | 0 críticos |
    | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
    | Code Smells | $CODE_SMELLS | — |
    | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

    [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
    SUMMARY
```

### 3.3 Bloque: Trivy SCA con conteo por severidad

El job `sca-trivy` instala trivy manualmente (más confiable que la action) y cuenta por severidad usando JSON. El job completo (listo para copiar):

```yaml
  sca-trivy:
    name: SCA — Trivy
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      security-events: write
      actions: read
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Trivy — escanear y guardar tabla
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

          trivy fs . \
            --severity CRITICAL,HIGH,MEDIUM \
            --ignore-unfixed \
            --skip-dirs 'DIRS_TRIVY' \
            --format table \
            --output trivy-table.txt 2>/dev/null || true

          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs 'DIRS_TRIVY' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs 'DIRS_TRIVY' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs 'DIRS_TRIVY' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")

          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then
            SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"
          else
            SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"
          fi

          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-${{ github.run_id }}
          path: trivy-table.txt
          retention-days: 30
```

### 3.4 Tests con errores conocidos — continue-on-error

Si hay tests fallando por bugs conocidos del código (no del pipeline), agregar `continue-on-error: true` de forma temporal con comentario explicativo:

```yaml
- name: Run tests
  run: <comando de tests>
  # TEMPORAL — continue-on-error: true: tests corren y reportan pero no bloquean.
  # Quitar cuando <dev> corrija <descripción del test fallido>.
  # (<motivo del fallo — ej: toHaveStyle falla en jsdom/CI por diferencia de ambiente>)
  continue-on-error: true
```

### 3.5 Exclusiones de cobertura — cuándo son legítimas

`-Dsonar.coverage.exclusions` excluye archivos de la métrica de cobertura (siguen apareciendo en el análisis de bugs/code smells). Usarlo solo cuando el archivo no puede ser testeado unitariamente por razones de arquitectura, no para ocultar código sin testear.

**Exclusiones legítimas:**

| Tipo de archivo | Ejemplo | Motivo |
|---|---|---|
| Entry point | `src/main.tsx`, `main.py` | Solo bootstrapping — no hay lógica testeable |
| Raíz del app | `src/App.tsx` | Routing/providers raíz — se testea via E2E |
| Configuración | `config.py`, `src/theme.ts`, `src/auth/firebase.ts` | Valores de entorno o init de SDK, no lógica |
| Routers/Controllers | `src/routers/*.py` | Necesitan TestClient/integration test con emulador — no disponible en PR check |
| Pages (temporal) | `src/clients/ClientsPage.tsx` | Solo mientras el dev escribe los tests — quitar la exclusión cuando los agrega |

**Exclusiones abusivas (nunca hacer):**

| Ejemplo | Motivo |
|---|---|
| `src/**` (todo el código) | Anula la métrica completamente |
| `src/services/**` | Los servicios tienen lógica de negocio — deben testearse |
| Excluir para "pasar" el QG sin tests | Infla la cobertura artificialmente |

**Cómo descubrir qué excluir:**

Consultar la API de SonarQube para ver los archivos con 0% ordenados por tipo:

```bash
curl -sf -u "$SONAR_TOKEN:" \
  "https://docs.trycore.co:9000/api/measures/component_tree?component=SONAR_PROJECT_KEY&metricKeys=coverage,uncovered_lines,lines_to_cover&qualifiers=FIL&ps=50&s=metric&asc=true&metricSort=coverage" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in d.get('components', []):
    path = c['key'].replace('SONAR_PROJECT_KEY:', '')
    measures = {m['metric']: m.get('value', '?') for m in c.get('measures', [])}
    print(f\"{measures.get('coverage','?'):>6}%  uncov={measures.get('uncovered_lines','?'):>3}  {path}\")
"
```

Revisar los archivos en 0% y clasificarlos: ¿son infraestructura/config? → excluir. ¿Son lógica de negocio sin tests? → escribir tests.

**Ejemplo real — DocFly Páginas Backend (FastAPI):**

```yaml
-Dsonar.coverage.exclusions=src/routers/**,config.py
# Routers: necesitan Firestore emulator (integration tests) — no disponible en PR check
# config.py: configuración de la app (env vars, settings)
# Resultado: cobertura 78.1% → 93.5% ✅
```

**Ejemplo real — DocFly Páginas Frontend (React/Vitest):**

```yaml
-Dsonar.coverage.exclusions=src/main.tsx,src/App.tsx,src/theme.ts,src/auth/firebase.ts,src/clients/ClientDetailPage.tsx,src/clients/ClientForm.tsx,src/clients/ClientsPage.tsx,src/transactions/hooks.ts,src/subscriptions/SubscriptionHistory.tsx,src/subscriptions/SubscriptionOverviewPage.tsx
# Primeros 4: infraestructura. Últimos 6: pages sin tests (TEMPORAL — Kevin escribe tests)
# Resultado: cobertura 72.6% → 80.8% ✅
```

---

## 4. Stack: Java / Maven / JHipster

### Template completo

```yaml
name: PR Check — NombreServicio

on:
  pull_request:
    branches: [develop, main, 'release/**']

env:
  JAVA_VERSION: '17'
  SONAR_PROJECT_KEY: 'Proyecto:NombreServicio'

jobs:
  build-test-sonar:
    name: Compile, Tests & SonarQube
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Java 17
        uses: actions/setup-java@v4
        with:
          java-version: ${{ env.JAVA_VERSION }}
          distribution: 'zulu'
          cache: 'maven'

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Dar permisos de ejecución a mvnw
        run: chmod +x mvnw

      - name: Build, Tests & SonarQube Analysis
        # Si hay tests fallando por bugs conocidos, agregar: -Dmaven.test.failure.ignore=true
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          ./mvnw -B test sonar:sonar \
            -DskipITs \
            -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }} \
            -Dsonar.projectName='NombreServicio' \
            -Dsonar.qualitygate.wait=false

      - name: Encabezado Unit Tests en summary
        if: always()
        run: |
          echo "## 🧪 Unit Tests — NombreServicio" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: '**/target/surefire-reports/*.xml'
          check_name: 'Unit Tests — NombreServicio'

      # ── Bloque Sonar Summary (§3.2) — copiar literalmente ──
      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          REPORT=".scannerwork/report-task.txt"
          if [ ! -f "$REPORT" ]; then
            echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
            echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi
          DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
          CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)
          for i in $(seq 1 12); do
            TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
              "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
            if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
              break
            fi
            sleep 5
          done
          QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ env.SONAR_PROJECT_KEY }}" 2>/dev/null || echo "{}")
          QG_STATUS=$(echo "$QG_JSON" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
          METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/measures/component?component=${{ env.SONAR_PROJECT_KEY }}&metricKeys=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots" 2>/dev/null || echo "{}")
          parse_metric() {
            echo "$METRICS_JSON" | python3 -c \
              "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
          }
          COVERAGE=$(parse_metric coverage)
          DUPLICATIONS=$(parse_metric duplicated_lines_density)
          BUGS=$(parse_metric bugs)
          VULNERABILITIES=$(parse_metric vulnerabilities)
          CODE_SMELLS=$(parse_metric code_smells)
          SEC_HOTSPOTS=$(parse_metric security_hotspots)
          if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
          elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
          else                                  QG_BADGE="⚠️ $QG_STATUS"
          fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔍 SonarQube — $QG_BADGE

          | Métrica | Valor | Umbral |
          |---------|-------|--------|
          | Quality Gate | $QG_BADGE | — |
          | Coverage | ${COVERAGE}% | ≥ 80% |
          | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
          | Bugs | $BUGS | 0 críticos |
          | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
          | Code Smells | $CODE_SMELLS | — |
          | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

          [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
          SUMMARY

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        continue-on-error: true   # quitar cuando el QG pase limpio
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}

  # ── Job Trivy — copiar el bloque §3.3 y reemplazar DIRS_TRIVY con: .git,.mvn,target ──
  sca-trivy:
    name: SCA — Trivy
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      security-events: write
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Trivy — escanear y guardar tabla
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
          trivy fs . --severity CRITICAL,HIGH,MEDIUM --ignore-unfixed --skip-dirs '.git,.mvn,target' --format table --output trivy-table.txt 2>/dev/null || true
          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs '.git,.mvn,target' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs '.git,.mvn,target' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs '.git,.mvn,target' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"; else SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"; fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-${{ github.run_id }}
          path: trivy-table.txt
          retention-days: 30
```

### Notas Java-específicas

- **mvnw**: `chmod +x mvnw` siempre — no tiene permisos en el runner de GitHub.
- **Tests + Sonar en un solo comando**: La cobertura la genera Jacoco durante los tests. Si se separan en dos pasos, SonarQube recibe 0% de cobertura.
- **`-DskipITs`**: Solo tests unitarios en PR. Los tests de integración corren solo en Jenkins.

---

## 5. Stack: Python / FastAPI / pytest

### Template completo

```yaml
name: PR Check — NombreServicio

on:
  workflow_dispatch:
  pull_request:
    branches: [develop, main, 'release/**']

env:
  SONAR_PROJECT_KEY: 'Proyecto:NombreServicio'

jobs:
  build-test-sonar:
    name: Tests & SonarQube
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Install dependencies
        run: pip install -r requirements-test.txt

      # Si los tests de integración requieren emuladores (Firestore, Redis, etc.),
      # solo correr tests/unit/ en el PR check.
      - name: Run unit tests with coverage
        env:
          # Ajustar según las variables que necesita el proyecto
          DEV_AUTH: "true"
        run: |
          pytest tests/unit/ -v \
            --cov=src \
            --cov-report=xml:coverage.xml \
            --cov-report=term-missing \
            --junitxml=test-results.xml \
            --tb=short

      - name: Encabezado Unit Tests en summary
        if: always()
        run: |
          echo "## 🧪 Unit Tests — NombreServicio" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: 'test-results.xml'
          check_name: 'Unit Tests — NombreServicio'

      - name: SonarQube Scan
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          args: >
            -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
            -Dsonar.projectName="NombreServicio"
            -Dsonar.sources=src,config.py
            -Dsonar.exclusions=**/__pycache__/**,**/venv/**,**/*.pyc,**/tests/**,main.py
            -Dsonar.tests=tests
            -Dsonar.test.inclusions=**/test_*.py
            -Dsonar.python.coverage.reportPaths=coverage.xml
            -Dsonar.python.version=3.12
            -Dsonar.qualitygate.wait=false
            -Dsonar.coverage.exclusions=src/routers/**,config.py

      # ── Bloque Sonar Summary (§3.2) — copiar literalmente ──
      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          REPORT=".scannerwork/report-task.txt"
          if [ ! -f "$REPORT" ]; then
            echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
            echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi
          DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
          CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)
          for i in $(seq 1 12); do
            TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
              "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
            if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
              break
            fi
            sleep 5
          done
          QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ env.SONAR_PROJECT_KEY }}" 2>/dev/null || echo "{}")
          QG_STATUS=$(echo "$QG_JSON" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
          METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/measures/component?component=${{ env.SONAR_PROJECT_KEY }}&metricKeys=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots" 2>/dev/null || echo "{}")
          parse_metric() {
            echo "$METRICS_JSON" | python3 -c \
              "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
          }
          COVERAGE=$(parse_metric coverage)
          DUPLICATIONS=$(parse_metric duplicated_lines_density)
          BUGS=$(parse_metric bugs)
          VULNERABILITIES=$(parse_metric vulnerabilities)
          CODE_SMELLS=$(parse_metric code_smells)
          SEC_HOTSPOTS=$(parse_metric security_hotspots)
          if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
          elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
          else                                  QG_BADGE="⚠️ $QG_STATUS"
          fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔍 SonarQube — $QG_BADGE

          | Métrica | Valor | Umbral |
          |---------|-------|--------|
          | Quality Gate | $QG_BADGE | — |
          | Coverage | ${COVERAGE}% | ≥ 80% |
          | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
          | Bugs | $BUGS | 0 críticos |
          | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
          | Code Smells | $CODE_SMELLS | — |
          | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

          [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
          SUMMARY

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        continue-on-error: true
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}

  sca-trivy:
    name: SCA — Trivy
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      security-events: write
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Trivy — escanear y guardar tabla
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
          trivy fs . --severity CRITICAL,HIGH,MEDIUM --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format table --output trivy-table.txt 2>/dev/null || true
          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"; else SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"; fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-${{ github.run_id }}
          path: trivy-table.txt
          retention-days: 30
```

### Notas Python-específicas

- **requirements-test.txt**: Separar dependencias de test de las de producción. Instalar solo las de test en el runner.
- **tests/unit/ vs tests/integration/**: Los tests de integración que requieren emuladores (Firestore, Redis, Pub/Sub) NO corren en el PR check — requieren infraestructura que no está disponible en el runner público de GitHub.
- **--junitxml**: Obligatorio para `mikepenz/action-junit-report`. No viene por defecto en pytest.
- **coverage.xml**: Generado con `--cov-report=xml`. SonarQube lo usa con `-Dsonar.python.coverage.reportPaths`.
- **sonar.sources**: Si hay un `config.py` en la raíz, incluirlo explícitamente: `-Dsonar.sources=src,config.py`. Agregar también a `sonar.coverage.exclusions` ya que es configuración.
- **coverage.exclusions para routers**: Los routers de FastAPI siempre van en `sonar.coverage.exclusions` porque solo se testean con integration tests (requieren emulador). Ver §3.5.

---

## 6. Stack: React / Vite / Vitest

### Configuración requerida en vite.config.ts

Antes de implementar el workflow, verificar que `vite.config.ts` tiene la configuración de cobertura:

```typescript
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test/setup.ts',
  css: false,
  coverage: {
    provider: 'istanbul',            // no usar 'v8' — da segfault en Linux CI
    reporter: ['lcov', 'text-summary'],   // lcov es el formato que lee SonarQube
    include: ['src/**/*.{ts,tsx}'],
    exclude: ['src/test/**', 'src/**/*.test.{ts,tsx}', 'src/**/*.d.ts'],
  },
},
```

Instalar el provider: `npm install -D @vitest/coverage-istanbul`

### Template completo

```yaml
name: PR Check — NombreServicio

on:
  pull_request:
    branches: [develop, main, 'release/**']

env:
  SONAR_PROJECT_KEY: 'Proyecto:NombreServicio-Frontend'

jobs:
  build-test-sonar:
    name: Build, Tests & SonarQube
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Node 20
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Install dependencies
        run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      # --pool=vmForks: evita el segfault (exit 139) de istanbul en runners Linux con jsdom
      # Si un test falla por ambiente CI/jsdom, ver §3.4 para agregar continue-on-error
      - name: Run tests with coverage
        run: npm run test -- --reporter=verbose --reporter=junit --outputFile=test-results.xml --coverage --pool=vmForks
        continue-on-error: true   # quitar cuando todos los tests pasen limpio en CI

      - name: Encabezado Unit Tests en summary
        if: always()
        run: |
          echo "## 🧪 Unit Tests — NombreServicio" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: 'test-results.xml'
          check_name: 'Unit Tests — NombreServicio'

      - name: SonarQube Scan
        if: always()
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          args: >
            -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
            -Dsonar.projectName="NombreServicio Frontend"
            -Dsonar.sources=src
            -Dsonar.exclusions=src/test/**,**/*.test.{ts,tsx}
            -Dsonar.javascript.lcov.reportPaths=coverage/lcov.info
            -Dsonar.qualitygate.wait=false
            -Dsonar.coverage.exclusions=src/main.tsx,src/App.tsx,src/theme.ts,src/auth/firebase.ts

      # ── Bloque Sonar Summary (§3.2) — copiar literalmente ──
      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          REPORT=".scannerwork/report-task.txt"
          if [ ! -f "$REPORT" ]; then
            echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
            echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi
          DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
          CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)
          for i in $(seq 1 12); do
            TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
              "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
            if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
              break
            fi
            sleep 5
          done
          QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ env.SONAR_PROJECT_KEY }}" 2>/dev/null || echo "{}")
          QG_STATUS=$(echo "$QG_JSON" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
          METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/measures/component?component=${{ env.SONAR_PROJECT_KEY }}&metricKeys=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots" 2>/dev/null || echo "{}")
          parse_metric() {
            echo "$METRICS_JSON" | python3 -c \
              "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
          }
          COVERAGE=$(parse_metric coverage)
          DUPLICATIONS=$(parse_metric duplicated_lines_density)
          BUGS=$(parse_metric bugs)
          VULNERABILITIES=$(parse_metric vulnerabilities)
          CODE_SMELLS=$(parse_metric code_smells)
          SEC_HOTSPOTS=$(parse_metric security_hotspots)
          if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
          elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
          else                                  QG_BADGE="⚠️ $QG_STATUS"
          fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔍 SonarQube — $QG_BADGE

          | Métrica | Valor | Umbral |
          |---------|-------|--------|
          | Quality Gate | $QG_BADGE | — |
          | Coverage | ${COVERAGE}% | ≥ 80% |
          | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
          | Bugs | $BUGS | 0 críticos |
          | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
          | Code Smells | $CODE_SMELLS | — |
          | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

          [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
          SUMMARY

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        continue-on-error: true
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}

  sca-trivy:
    name: SCA — Trivy
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      security-events: write
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Trivy — escanear y guardar tabla
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
          trivy fs . --severity CRITICAL,HIGH,MEDIUM --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format table --output trivy-table.txt 2>/dev/null || true
          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"; else SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"; fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-${{ github.run_id }}
          path: trivy-table.txt
          retention-days: 30
```

### Notas Vitest/React-específicas

- **`--pool=vmForks`**: Evita el segfault (exit 139) de istanbul en runners Linux con jsdom. Siempre incluirlo cuando se usa coverage en CI. No confundir con `--pool=forks` (diferente, también puede fallar).
- **JUnit output en vitest**: Usar `--reporter=verbose --reporter=junit --outputFile=test-results.xml`. El flag `--reporter` se puede repetir para múltiples formatos en paralelo.
- **lcov.info**: La cobertura queda en `coverage/lcov.info`. SonarQube la lee con `-Dsonar.javascript.lcov.reportPaths=coverage/lcov.info`. El reporter en vite.config.ts debe incluir `'lcov'`.
- **toHaveStyle en jsdom**: Los tests de estilos CSS con `toHaveStyle` frecuentemente fallan en jsdom/CI pero pasan localmente. Usar `continue-on-error: true` temporal (ver §3.4).
- **Type check separado**: `npx tsc --noEmit` antes de los tests detecta errores de tipos sin compilar el bundle completo. Bloquea el PR si hay errores TS.
- **`if: always()` en Sonar**: Agregar cuando los tests tienen `continue-on-error: true` — así el análisis corre aunque los tests reporten fallo.

---

## 7. Stack: Angular / Node.js

### Configuración adicional requerida

Angular usa Karma + karma-junit-reporter para generar el XML de tests. Instalar y configurar en `karma.conf.js`:

```bash
npm install -D karma-junit-reporter
```

```javascript
// karma.conf.js
reporters: ['progress', 'junit'],
junitReporter: {
  outputDir: 'reports',
  outputFile: 'junit.xml',
  useBrowserName: false
}
```

### Template completo

```yaml
name: PR Check — NombreServicio

on:
  pull_request:
    branches: [develop, main, 'release/**']

env:
  SONAR_PROJECT_KEY: 'Proyecto:NombreServicio-Frontend'

jobs:
  build-test-sonar:
    name: Build, Tests & SonarQube
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Node 22
        uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Install dependencies
        run: npm ci --prefer-offline

      - name: Type check
        run: npx tsc --noEmit

      - name: Run unit tests with coverage
        run: |
          npm test -- \
            --watch=false \
            --browsers=ChromeHeadless \
            --code-coverage
        env:
          CHROME_BIN: /usr/bin/google-chrome

      - name: Encabezado Unit Tests en summary
        if: always()
        run: |
          echo "## 🧪 Unit Tests — NombreServicio" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: 'reports/junit.xml'
          check_name: 'Unit Tests — NombreServicio'

      - name: SonarQube Scan
        if: always()
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          args: >
            -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
            -Dsonar.projectName="NombreServicio Frontend"
            -Dsonar.sources=src/main
            -Dsonar.exclusions=src/test/**,**/*.spec.ts
            -Dsonar.javascript.lcov.reportPaths=coverage/lcov.info
            -Dsonar.qualitygate.wait=false

      # ── Bloque Sonar Summary (§3.2) — copiar literalmente ──
      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          REPORT=".scannerwork/report-task.txt"
          if [ ! -f "$REPORT" ]; then
            echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
            echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi
          DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
          CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)
          for i in $(seq 1 12); do
            TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
              "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
            if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
              break
            fi
            sleep 5
          done
          QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ env.SONAR_PROJECT_KEY }}" 2>/dev/null || echo "{}")
          QG_STATUS=$(echo "$QG_JSON" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
          METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/measures/component?component=${{ env.SONAR_PROJECT_KEY }}&metricKeys=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots" 2>/dev/null || echo "{}")
          parse_metric() {
            echo "$METRICS_JSON" | python3 -c \
              "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
          }
          COVERAGE=$(parse_metric coverage)
          DUPLICATIONS=$(parse_metric duplicated_lines_density)
          BUGS=$(parse_metric bugs)
          VULNERABILITIES=$(parse_metric vulnerabilities)
          CODE_SMELLS=$(parse_metric code_smells)
          SEC_HOTSPOTS=$(parse_metric security_hotspots)
          if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
          elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
          else                                  QG_BADGE="⚠️ $QG_STATUS"
          fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔍 SonarQube — $QG_BADGE

          | Métrica | Valor | Umbral |
          |---------|-------|--------|
          | Quality Gate | $QG_BADGE | — |
          | Coverage | ${COVERAGE}% | ≥ 80% |
          | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
          | Bugs | $BUGS | 0 críticos |
          | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
          | Code Smells | $CODE_SMELLS | — |
          | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

          [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
          SUMMARY

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        continue-on-error: true
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}

  sca-trivy:
    name: SCA — Trivy
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      security-events: write
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Trivy — escanear y guardar tabla
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
          trivy fs . --severity CRITICAL,HIGH,MEDIUM --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format table --output trivy-table.txt 2>/dev/null || true
          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs '.git,node_modules,dist' --format json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"; else SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"; fi
          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-${{ github.run_id }}
          path: trivy-table.txt
          retention-days: 30
```

---

## 8. SonarQube — Configuración

**Servidor:** `https://docs.trycore.co:9000` (DigitalOcean NYC1 — acceso público)

### 8.1 SONAR_HOST_URL va como Variable global de organización

Es una URL pública — no tiene sentido ocultarla ni repetirla en cada repo. Configurarla **una sola vez a nivel de organización** en GitHub para que todos los proyectos la hereden automáticamente:

**Configuración (una vez, la hace el dueño de la org):**
- `GitHub Org → Settings → Secrets and variables → Actions → Variables → New organization variable`
- Nombre: `SONAR_HOST_URL`
- Valor: `https://docs.trycore.co:9000`
- Visibilidad: `All repositories` (o `Selected repositories` si se prefiere restringir)

**En proyectos nuevos:** no configurar nada — la variable ya existe heredada de la organización.

**Verificar:** en cualquier repo ir a `Settings → Secrets and variables → Actions` y ver la pestaña `Variables` — debe aparecer `SONAR_HOST_URL` como variable heredada de la organización.

El `SONAR_TOKEN` sí va como **Secret** por repo (o también puede ser secret de organización si todos los proyectos comparten el mismo token de CI):

```yaml
env:
  SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
  SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}    # heredada de la org
```

> Si un proyecto necesita apuntar a un servidor Sonar diferente, puede sobreescribir
> la variable a nivel de repo — tiene prioridad sobre la de organización.

> ⚠️ **Whitespace invisible:** si el Quality Gate aparece como `UNKNOWN` tras configurar correctamente la variable, verificar que el valor no tiene saltos de línea ni espacios ocultos (frecuente cuando se crea la variable via script o copia/pega desde terminal). Ver §16.6.5 para el diagnóstico completo y el workaround defensivo aplicado en los reusable workflows.

### 8.2 Dos proyectos por microservicio

| Proyecto | Uso | Project Key |
|---|---|---|
| CI/CD | Pipeline GitHub Actions — métricas del equipo | `Proyecto:NombreServicio` |
| Developers | SonarLint Connected Mode en VS Code | `proyecto-nombreservicio-dev` |

El pipeline siempre usa el proyecto `Proyecto:*`. El `sonar-project.properties` en el repo apunta al proyecto `-dev` (para SonarLint).

**Prefijos por cliente/proyecto:**

| Contexto | Prefijo CI/CD | Prefijo Dev |
|---|---|---|
| COBRA | `Cobra:` | `cobra-` |
| DocFly | `Docfly:` | `docfly-` |
| Proyecto nuevo | `<Cliente>:` | `<cliente>-` |

### 8.3 `-Dsonar.qualitygate.wait=false`

**Siempre agregar `-Dsonar.qualitygate.wait=false`** al scanner. Sin este flag, el scanner espera el Quality Gate y el job falla antes de que el step de resumen tenga datos. Separar el esperar del Quality Gate en su propio step (`sonarqube-quality-gate-action`).

### 8.4 Quality Gate action — continue-on-error temporal

Si hay bugs conocidos que aún no fueron corregidos por el equipo de desarrollo:

```yaml
- uses: sonarsource/sonarqube-quality-gate-action@master
  continue-on-error: true    # TEMPORAL — quitar cuando Quality Gate pase limpio
  timeout-minutes: 5
  env:
    SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
    SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
```

### 8.5 Umbrales configurados en el Quality Gate

El Quality Gate **Trycore (Default)** tiene condiciones en dos capas (configuración validada como "recommended by Sonar" — mayo 2026):

**Código Nuevo** — bloquea el PR si el código introducido en el PR viola alguna de estas condiciones:

| Métrica | Operador | Valor |
|---|---|---|
| Issues (bugs + vulnerabilidades + smells) | mayor que | 0 |
| Security Hotspots Reviewed | menor que | 100% |
| Coverage | menor que | 80% |
| Duplicated Lines (%) | mayor que | 3% |

**Overall Code** — refleja el estado del proyecto completo (histórico). Un PR puede pasar el gate incluso si Overall Code falla — esto permite resolver deuda técnica gradualmente sin bloquear el trabajo nuevo:

| Métrica | Operador | Valor |
|---|---|---|
| Bugs | mayor que | 0 |
| Vulnerabilities | mayor que | 0 |
| Code Smells | mayor que | 10 |
| Coverage | menor que | 80% |
| Duplicated Lines (%) | mayor que | 3% |
| Security Hotspots Reviewed | menor que | 100% |
| Security Rating | peor que | A |

> **Por qué dos capas:** Overall Code evalúa la salud del proyecto acumulada; New Code garantiza que cada PR no empeore la calidad. Para proyectos con deuda técnica pre-existente, Overall Code puede fallar sin bloquear el merge — el equipo lo corrige iterativamente. New Code sí bloquea si el PR introduce nuevos problemas.

---

## 9. Trivy SCA — Configuración

### 9.1 Directorios a excluir por stack

| Stack | --skip-dirs |
|---|---|
| Java / Maven | `.git,.mvn,target` |
| Python | `.git,__pycache__,venv,.venv` |
| React / Vite | `.git,node_modules,dist` |
| Angular | `.git,node_modules,dist` |

### 9.2 Modo informativo vs bloqueante

Durante la fase inicial de un proyecto, usar modo informativo (no bloquea el merge). Cuando las vulnerabilidades CRITICAL estén resueltas, activar modo bloqueante:

```yaml
# Modo informativo (fase inicial):
trivy fs . --severity CRITICAL,HIGH,MEDIUM --ignore-unfixed ... || true

# Modo bloqueante (proyecto maduro):
# Quitar el || true — trivy retorna exit code 1 si hay CRITICAL/HIGH
trivy fs . --severity CRITICAL,HIGH --ignore-unfixed ...
```

### 9.3 En repos privados sin GitHub Advanced Security

El SARIF no se puede subir a la pestaña Security de GitHub en repos privados sin licencia Advanced Security. Usar tabla en artefacto en lugar de SARIF:

```yaml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: trivy-sca-report-${{ github.run_id }}
    path: trivy-table.txt
    retention-days: 30
```

---

## 10. sonar-project.properties

### 10.1 Propósito del archivo

El `sonar-project.properties` en el repo es **solo para desarrolladores** con SonarLint en VS Code. El pipeline CI/CD **no lo usa** — inyecta el host y token vía variables de entorno que tienen mayor prioridad.

### 10.2 Propiedades permitidas vs prohibidas

| Propiedad | ¿Va en el archivo? | Motivo |
|---|---|---|
| `sonar.projectKey` | ✅ Sí (proyecto `-dev`) | Para SonarLint local |
| `sonar.projectName` | ✅ Sí | Para SonarLint local |
| `sonar.sources` | ✅ Sí | Para SonarLint local |
| `sonar.host.url` | ✅ Sí (solo para SonarLint) | El CI/CD lo sobreescribe con env var |
| `sonar.token` | ✅ Sí (token personal del dev) | Token del dev, no el del CI |
| `sonar.qualitygate.wait` | ❌ No | Solo para el CI — lo maneja el workflow |
| `sonar.coverage.exclusions` | ❌ No | Las exclusiones de cobertura las define el pipeline, no el dev local |
| `sonar.skip` | ❌ No | Salta el análisis completo |

### 10.3 Estructura mínima — Python

```properties
sonar.projectKey=proyecto-nombreservicio-dev
sonar.projectName=NombreServicio (Dev — SonarLint)
sonar.projectVersion=1.0.0

sonar.sources=src,config.py
sonar.exclusions=**/node_modules/**,**/__pycache__/**,**/venv/**,**/*.pyc,**/*test*.py,**/tests/**,main.py
sonar.tests=tests
sonar.test.inclusions=**/test_*.py,**/*_test.py

sonar.python.coverage.reportPaths=coverage.xml
sonar.sourceEncoding=UTF-8

# Conexión local para SonarLint (no usada por CI/CD — env vars tienen prioridad)
sonar.host.url=https://docs.trycore.co:9000
sonar.token=sqp_TOKEN_PERSONAL_DEL_DESARROLLADOR
```

### 10.4 Estructura mínima — Java

```properties
sonar.projectKey=proyecto-nombreservicio-dev
sonar.projectName=NombreServicio (Dev — SonarLint)

sonar.sources=src/main/java
sonar.tests=src/test/java

sonar.coverage.jacoco.xmlReportPaths=target/site/**/jacoco*.xml
sonar.java.codeCoveragePlugin=jacoco
sonar.junit.reportPaths=target/surefire-reports,target/failsafe-reports
sonar.sourceEncoding=UTF-8

sonar.exclusions=src/main/webapp/content/**/*.*,target/**/*.*
```

---

## 11. Jenkinsfile — Reglas generales

### 11.1 Variables a ajustar por microservicio

```groovy
def APP_NAME     = 'contratos'        // nombre del servicio (minúsculas)
def GITHUB_REPO  = 'trycore-co/OP...' // org/repo en GitHub
def REPO_URL     = 'https://github.com/trycore-co/OP....git'
def JAVA_HOME_17 = '/usr/lib/jvm/jdk-17.0.12-oracle-x64'
def SERVER_PORT  = '6087'             // puerto donde corre el servicio
```

### 11.2 Parámetro BRANCH — checkout scm vs git step

El parámetro `BRANCH` es opcional para permitir despliegue manual de ramas específicas. Si está vacío, usar `checkout scm`. Si tiene valor, usar `git` step:

```groovy
script {
    if (params.BRANCH?.trim()) {
        git branch: params.BRANCH,
            credentialsId: GH_CRED_ID,
            url: REPO_URL
    } else {
        checkout scm    // ← Obligatorio cuando BRANCH está vacío
    }
}
```

**No usar `git branch: params.BRANCH` cuando BRANCH puede ser null/vacío** — causará `refs/remotes/origin/null` en el checkout.

### 11.3 Parámetro LIQUIDBASE — siempre false por default

```groovy
booleanParam(
    name: 'LIQUIDBASE',
    defaultValue: false,    // ← false siempre. Activar solo cuando hay migraciones nuevas
    description: 'Ejecutar migraciones Liquibase al levantar el contenedor'
)
```

Convertir a string explícitamente:

```groovy
def liquidbaseVal = params.LIQUIDBASE ? 'true' : 'false'
sh "sed -i 's/liquidbase_status/${liquidbaseVal}/g' docker-compose.yml"
```

### 11.4 Health check — tiempo suficiente para Liquibase

```groovy
// 24 intentos × 10s = 240s (4 minutos)
for (int i = 1; i <= 24; i++) {
    sleep 10
    def status = sh(
        script: "curl -sf http://localhost:${SERVER_PORT}/management/health | grep -c '\"status\":\"UP\"'",
        returnStatus: true
    )
    ...
}
```

**Endpoint correcto para JHipster:** `/management/health` (no `/actuator/health`).

### 11.5 No definir triggers en el Jenkinsfile si ya están en la UI

Si el Poll SCM está configurado en la UI de Jenkins, no agregarlo también en el `Jenkinsfile` con `triggers { pollSCM }` — causa doble trigger y builds duplicados.

---

## 12. Checklist para un proyecto nuevo

### Preparación (una vez por proyecto)

**Credenciales — org trycore-co:**
- [ ] `SONAR_TOKEN` → **ya existe como secret de organización** — no configurar por repo (ver §16.1)
- [ ] `SONAR_HOST_URL` → **ya existe como variable de organización** — no configurar por repo (ver §8.1 y §16.1)

**Credenciales — org externa o proyecto fuera de trycore-co:**
- [ ] Generar token de CI en SonarQube → Mi Cuenta → Seguridad (tipo: CI)
- [ ] En GitHub: `Settings → Secrets → Actions` → agregar `SONAR_TOKEN` con el token de CI
- [ ] En GitHub: `Settings → Variables → Actions` → agregar `SONAR_HOST_URL` con la URL del servidor Sonar

**SonarQube (aplica siempre):**
- [ ] Si se usa auto-provisioning (token Global Analysis): el proyecto se crea automáticamente en el primer scan — no hacer nada
- [ ] Si se usa token de proyecto específico: crear proyecto en SonarQube con el `project key` antes de correr el scan
- [ ] Crear proyecto SonarLint para devs: `proyecto-nombreservicio-dev` + token personal (ver §10)

### Archivos a crear en el repositorio

**Para repos Python en org trycore-co — usar el wrapper (§16.4):**
- [ ] `.github/workflows/pr-check-<nombre>.yml` — copiar el wrapper de §16.4 y ajustar 4 parámetros
- [ ] `sonar-project.properties` — usar la estructura mínima de §10 (solo para SonarLint local)

**Para otros stacks o repos fuera de la org — usar el template completo:**
- [ ] `.github/workflows/pr-check.yml` — usar el template de la sección correspondiente al stack (§4/§5/§6/§7)
- [ ] `sonar-project.properties` — usar la estructura mínima de §10 y ajustar project key/name

### Configuración en GitHub (Branch Protection)

- [ ] `Settings → Branches → Add rule` para `develop` y `main`
- [ ] Activar **Require status checks to pass before merging**
- [ ] Agregar como required: el nombre del job del workflow (ej: `check`, `build-test-sonar`, `sca-trivy`)
- [ ] Activar **Require a pull request before merging** (1 aprobación para `develop`, 2 para `main`)

### Verificación final

- [ ] Abrir un PR de prueba hacia `develop` — verificar que GitHub Actions corre
- [ ] Verificar que el proyecto aparece en SonarQube con métricas reales (no 0%)
- [ ] Verificar que el PR Summary muestra la tabla de tests y la tabla de SonarQube
- [ ] Verificar que el PR Summary muestra los conteos de Trivy por severidad
- [ ] Si coverage < 80%, consultar la API de SonarQube (comando en §3.5) para identificar archivos a excluir vs tests a escribir

---

## 13. Tests E2E — Playwright vs Cypress

### 13.1 ¿Cuál usar?

Ambas herramientas hacen lo mismo — automatizar un navegador real para probar flujos completos de la app. No son complementarias ni se usan juntas; se elige una por proyecto.

| Criterio | Playwright | Cypress |
|---|---|---|
| **Mantenedor** | Microsoft | Cypress.io |
| **Multi-browser** | ✅ Chromium, Firefox, WebKit (Safari) | ❌ Solo Chromium/Firefox (WebKit experimental) |
| **TypeScript nativo** | ✅ Sin config extra | ⚠️ Requiere configuración |
| **Velocidad en CI** | ✅ Más rápido (paralelo real, headless puro) | ⚠️ Más lento (arquitectura distinta) |
| **Debugging DX** | Trace viewer, video, screenshots integrados | Time-travel UI muy visual, fácil para devs nuevos |
| **Componentes** | `@playwright/experimental-ct-react` (experimental) | ✅ Cypress Component Testing maduro |
| **Dashboard / Cloud** | ✅ Gratuito (HTML report local) | ⚠️ Dashboard de grabaciones es pago |
| **Ecosistema** | Creciendo rápido (est. superó a Cypress en 2024) | Maduro, muchos plugins disponibles |
| **Precio** | Gratis (open source Microsoft) | Gratis para E2E básico; Dashboard es pago |

**Regla de decisión por proyecto:**

```
¿El proyecto ya usa Cypress?
  Sí → mantener Cypress, no migrar
  No → usar Playwright (es el estándar para proyectos nuevos desde 2024)

¿El proyecto necesita testing de componentes aislados (Component Testing)?
  Sí y ya tiene React/Vue/Angular → evaluar Cypress Component Testing
  (Playwright CT aún es experimental)

¿El equipo es nuevo en E2E?
  Playwright: curva algo más técnica pero TypeScript nativo ayuda
  Cypress: interfaz visual más amigable para empezar
```

**Conclusión para proyectos nuevos Trycore:** usar **Playwright**. Es lo que implementó Kevin en DocFly Páginas. Multi-browser, TypeScript nativo, gratuito sin limitaciones, y ya es el más usado en proyectos nuevos del ecosistema.

---

### 13.2 Cuándo correr los E2E

Los tests E2E **no corren en el PR check** de GitHub Actions porque requieren el stack completo levantado (frontend + backend + base de datos). Su lugar en el pipeline es:

| Momento | Quién los corre | Cómo |
|---|---|---|
| **Desarrollo local** | El desarrollador, antes de hacer PR | `npm run e2e` con docker-compose levantado |
| **Post-deploy staging** | Jenkins, después de desplegar | Step adicional en el Jenkinsfile |
| **CI opcional** | GitHub Actions (workflow separado) | Solo si hay un ambiente de staging permanente con URL pública |

**No incluir E2E en el job `build-test-sonar`** — no hay backend disponible en el runner de GitHub Actions.

> **Nota DocFly Páginas Frontend:** el `pr-check.yml` del frontend tiene un job `e2e-tests` que intenta correr Playwright contra `localhost:5173` sin levantar ningún servidor. Ese job siempre falla en CI porque no hay frontend arrancado. Mientras no exista un ambiente de staging con URL pública accesible desde los runners, el job de E2E en el PR check debe eliminarse o marcarse con `continue-on-error: true`. Los E2E deben moverse al Jenkinsfile post-deploy (ver §13.5).

---

### 13.3 Setup de Playwright (React/Vite — referencia DocFly Páginas)

#### Instalación

```bash
npm install -D @playwright/test
npx playwright install chromium   # solo chromium para CI; agregar más browsers si se necesita
```

#### playwright.config.ts

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,        // false mientras el backend no soporte concurrencia en dev
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 30_000,

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Agregar firefox y webkit cuando se quiera cobertura multi-browser:
    // { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    // { name: 'webkit',  use: { ...devices['Desktop Safari']  } },
  ],
});
```

#### Scripts en package.json

```json
{
  "scripts": {
    "e2e": "playwright test",
    "e2e:ui": "playwright test --ui",
    "e2e:debug": "playwright test --debug",
    "e2e:report": "playwright show-report"
  }
}
```

#### Estructura de carpetas

```
proyecto/
├── e2e/
│   ├── helpers.ts          ← funciones compartidas (login, waitForLoad, etc.)
│   ├── auth.spec.ts        ← tests de autenticación
│   ├── dashboard.spec.ts   ← tests del dashboard
│   ├── clients.spec.ts     ← tests por feature/módulo
│   └── *.spec.ts
├── playwright.config.ts
└── package.json
```

---

### 13.4 Patrones de implementación

#### Helper de autenticación con DEV_AUTH

Cuando el backend tiene modo DEV_AUTH (`DEV_AUTH=true`), se puede crear un helper que autentica sin Firebase para correr los E2E localmente sin credenciales reales:

```typescript
// e2e/helpers.ts
import { type Page } from '@playwright/test';

export async function devLogin(page: Page) {
  await page.goto('/login');
  const token = await page.evaluate(async () => {
    const res = await fetch('/api/auth/dev-login', { method: 'POST' });
    const data = await res.json();
    sessionStorage.setItem('dev-token', data.token);
    return data.token;
  });
  expect(token).toBeTruthy();
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
}

export async function waitForPageLoad(page: Page) {
  // Ant Design: esperar a que desaparezcan los spinners
  await page.waitForFunction(() =>
    document.querySelectorAll('.ant-spin-spinning').length === 0,
    { timeout: 10_000 }
  );
}
```

> **Para apps sin DEV_AUTH:** crear un usuario de test en el ambiente de staging y
> guardar sus credenciales en las variables de entorno del runner CI.

#### Convención de nombres — igual que unit tests

```typescript
test('test_ac01_login_page_renders', ...)
test('test_ac02_login_form_validates_empty', ...)
test('test_ac03_login_form_validates_invalid_email', ...)
```

Misma convención `test_ac0N_*` que los tests unitarios — facilita trazabilidad con criterios de aceptación.

#### Usar roles y text locators, no clases CSS de frameworks

```typescript
// ✅ Robusto — no depende de la versión de Ant Design
await page.getByRole('button', { name: 'Iniciar sesión' }).click();
await page.getByPlaceholder('usuario@empresa.com').fill('user@test.com');
await page.getByText('Clientes').click();

// ⚠️ Frágil — se rompe si Ant Design cambia la clase
await page.locator('.ant-btn-primary').click();
```

Cuando no hay opción (tablas de Ant Design sin accesibilidad), usar `data-testid`:

```typescript
// En el componente React:
<Table data-testid="clients-table" ... />

// En el test:
await page.locator('[data-testid="clients-table"]').waitFor();
```

---

### 13.5 Integración en Jenkins (post-deploy)

Agregar al Jenkinsfile después del health check, **solo en el ambiente de staging**:

```groovy
stage('E2E Tests') {
    when {
        branch 'develop'    // solo en staging, no en prod
    }
    steps {
        script {
            sh '''
                cd frontend/
                npm ci
                npx playwright install chromium
                BASE_URL=http://localhost:5173 npm run e2e -- --reporter=list
            '''
        }
    }
    post {
        always {
            // Archivar el HTML report
            archiveArtifacts artifacts: 'frontend/playwright-report/**', allowEmptyArchive: true
        }
        failure {
            // No hacer rollback automático por E2E — son tests de humo, no de regresión
            echo 'E2E tests fallaron — revisar playwright-report'
        }
    }
}
```

> Los E2E en CI/CD son tests de **humo** (smoke tests): verifican que los flujos
> principales no están rotos después del deploy. No son la red de seguridad principal —
> esa es la suite de unit tests que ya corrió en el PR.

---

### 13.6 Exclusión de los E2E en SonarQube

La carpeta `e2e/` no debe analizarse como código de producción en Sonar. Agregar a las exclusiones del scan:

```yaml
# En el workflow de GitHub Actions
-Dsonar.exclusions=src/test/**,**/*.test.{ts,tsx},e2e/**
```

```properties
# En sonar-project.properties (para SonarLint local)
sonar.exclusions=node_modules/**,dist/**,e2e/**,src/test/**
```

---

### 13.7 Checklist E2E para un proyecto nuevo

```
[ ] Decidir herramienta: Playwright (nuevo proyecto) o Cypress (si ya existe)
[ ] npm install -D @playwright/test && npx playwright install chromium
[ ] Crear playwright.config.ts (copiar de §13.3 y ajustar baseURL y testDir)
[ ] Agregar scripts e2e / e2e:ui / e2e:debug en package.json
[ ] Crear e2e/helpers.ts con devLogin() y waitForPageLoad()
[ ] Escribir specs para los flujos principales: auth, dashboard, módulo principal
[ ] Agregar e2e/** a sonar.exclusions en el workflow y en sonar-project.properties
[ ] Documentar en el README cómo levantar el stack y correr los E2E localmente
[ ] (Opcional) Agregar stage E2E en Jenkinsfile post-deploy en staging
```

---

*Documento mantenido por el equipo de DevOps — camilo.piza@trycore.com*

---

## 14. OWASP Top 10 — Cobertura por el pipeline

Este documento describe cómo el pipeline CI/CD (SonarQube + Trivy + npm audit) mapea a las 10 categorías de riesgo del OWASP Top 10 (2021). El objetivo es que cada PR que pase el Quality Gate tenga evidencia verificable frente a auditorías externas.

### 14.1 Mapa de herramientas vs. OWASP

| Categoría OWASP | Qué detecta en el pipeline | Herramienta |
|---|---|---|
| **A01 — Broken Access Control** | Security Hotspots de control de acceso, rutas sin autenticación | SonarQube |
| **A02 — Cryptographic Failures** | Secretos hardcodeados, algoritmos débiles (MD5, SHA1) | SonarQube |
| **A03 — Injection** | SQL/NoSQL injection, XSS, path traversal en código | SonarQube |
| **A05 — Security Misconfiguration** | Debug activo en prod, CORS abierto, configs inseguras | SonarQube |
| **A06 — Outdated Components** | CVEs en dependencias (Python, Java, npm, sistema) | **Trivy** + **npm audit** |
| **A07 — Auth Failures** | Contraseñas hardcodeadas, lógica de auth incorrecta | SonarQube |
| **A08 — Data Integrity Failures** | Dependencias no pinneadas que permiten supply chain attacks | **Trivy** (lockfile audit) |
| **A09 — Logging Failures** | Código con manejo silencioso de excepciones (catch vacío) | SonarQube |
| **A04/A10 — SSRF / Insecure Design** | Parcialmente detectable — requiere revisión manual en PR | Code Review |

**Categorías que el pipeline NO cubre automáticamente:**
- A04 (Insecure Design): requiere revisión de arquitectura, no análisis estático
- A10 (SSRF): detectable solo si se usa análisis dinámico (DAST) — no implementado

---

### 14.2 Paso adicional para proyectos Node.js/React: npm audit

Trivy detecta CVEs en dependencias Node.js pero **npm audit** es más preciso para el ecosistema npm porque consume directamente el advisory database de npm. Agregar al template de React/Angular (§6, §7):

```yaml
- name: npm audit (seguridad de dependencias)
  run: |
    npm audit --audit-level=high --json > npm-audit.json || true

    CRITICAL=$(python3 -c "
    import sys, json
    d = json.load(open('npm-audit.json'))
    vulns = d.get('vulnerabilities', {})
    print(sum(1 for v in vulns.values() if v.get('severity') == 'critical'))
    " 2>/dev/null || echo "0")

    HIGH=$(python3 -c "
    import sys, json
    d = json.load(open('npm-audit.json'))
    vulns = d.get('vulnerabilities', {})
    print(sum(1 for v in vulns.values() if v.get('severity') == 'high'))
    " 2>/dev/null || echo "0")

    cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
    ## 🔒 npm audit — Dependencias

    | Severidad | Vulnerabilidades |
    |-----------|-----------------|
    | 🔴 Critical | $CRITICAL |
    | 🟠 High | $HIGH |

    > Correr \`npm audit fix\` localmente si hay HIGH o CRITICAL.
    SUMMARY

    if [ "$CRITICAL" -gt "0" ]; then
      echo "❌ npm audit encontró vulnerabilidades CRITICAL. Actualizar dependencias antes de hacer merge."
      exit 1
    fi
```

**Regla:** Critical bloquea el pipeline. High es informativo — el developer debe correrlo localmente y actualizar.

**Diferencia Trivy vs npm audit:**
- Trivy escanea el filesystem completo (incluye imagen Docker, SO, binarios)
- npm audit es más preciso para CVEs del ecosistema npm (usa el registro oficial de npm)
- Usar ambos para cobertura máxima

---

### 14.3 Configuración de SonarQube para maximizar cobertura OWASP

El Quality Gate de SonarQube debe incluir estos umbrales para cubrir OWASP:

```properties
# sonar-project.properties — umbrales recomendados
sonar.qualitygate.conditions=\
  new_vulnerabilities=0,\
  new_security_hotspots_reviewed=100,\
  new_coverage>=80,\
  new_duplicated_lines_density<=3
```

Los **Security Hotspots** en SonarQube corresponden directamente a categorías OWASP:

| SonarQube Hotspot Category | OWASP |
|---|---|
| `sql-injection`, `command-injection`, `ldap-injection` | A03 |
| `weak-cryptography` | A02 |
| `auth` | A07 |
| `insecure-conf` | A05 |
| `log-injection` | A09 |
| `xxe`, `ssrf` | A10 |
| `cross-site-scripting` | A03 |

Un PR no debe hacer merge si hay Security Hotspots sin revisar y marcar como "Safe" o "Fixed".

---

### 14.4 Checklist OWASP para un PR de seguridad

Cuando se hace un PR que toca autenticación, autorización, o manejo de secretos, el reviewer debe verificar manualmente:

```
[ ] A01: ¿El endpoint nuevo tiene decorador de autorización (@require_view_action o ProtectedRoute)?
[ ] A01: ¿El usuario solo puede acceder a sus propios recursos (RLS)?
[ ] A02: ¿No hay secretos hardcodeados? ¿Los logs no imprimen credenciales?
[ ] A03: ¿Los inputs de usuario se validan con schema/regex antes de usarlos en queries?
[ ] A05: ¿Los endpoints dev/debug están detrás de un guard de ambiente?
[ ] A06: ¿Se corrió `npm audit` o `pip-audit` y no hay CVEs HIGH/CRITICAL sin fix?
[ ] A07: ¿Los JWTs se validan con la librería oficial (Firebase Admin SDK, etc.)?
[ ] A09: ¿Las operaciones sensibles (crear usuario, cambiar rol, borrar) quedan en el audit log?
```

Este checklist es el mínimo para que el CTO pueda responder "sí, cumplimos OWASP" a una auditoría externa.

---

### 14.5 Lección aprendida — DocFly Páginas (mayo 2026)

Durante la revisión de seguridad pre-producción de `docfly-paginas-fronted`:

- **Hallazgo:** `axios@1.7.9` tenía 3 CVEs HIGH (prototype pollution + header injection, CVSS 7.4).
- **Detección:** npm audit en el pipeline lo habría detectado automáticamente.
- **Fix:** `npm install axios@1.15.2` — operación de 2 minutos.
- **Lección:** Trivy no detectó estos CVEs porque eran vulnerabilidades npm registradas después del último update de la base de datos. npm audit los sí los detectó. Usar ambas herramientas es obligatorio para proyectos Node.js.

---

## 15. Monorepo con múltiples microservicios

**Referencia:** Implementación CI para `templaris-bpm-backend-ms` (mayo 2026) — monorepo con 6 microservicios Python/FastAPI independientes.

Este patrón aplica cuando un repositorio contiene varios servicios en subdirectorios separados, cada uno con su propio `requirements.txt`, suite de tests, y llave SonarQube.

---

### 15.1 Estrategia: un workflow por servicio

**Opción elegida:** un archivo `.yml` por microservicio con filtro `paths:`.

```
.github/workflows/
├── pr-check-validation-service.yml
├── pr-check-batch-loader-service.yml
├── pr-check-pdf-generator-service.yml
├── pr-check-ms-file-management.yml
├── pr-check-adapter-service.yml
└── pr-check-ms-observability.yml
```

**Ventajas frente a un único workflow con matrix:**
- Cada servicio evoluciona su pipeline de forma independiente (si un servicio agrega integration tests, no afecta a los demás)
- Los checks en el PR son por servicio — se ve exactamente cuál servicio falla
- Ejecución paralela natural: si el PR toca 2 servicios, los 2 workflows corren en paralelo sin configuración extra
- Más fácil de depurar: el log de un workflow tiene scope de un solo servicio

**Filtro `paths:`** — clave para no disparar todos los workflows en cada PR:

```yaml
on:
  workflow_dispatch:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
    paths:
      - 'validation-service/**'   # ← solo cambios dentro de este directorio
```

**Regla:** `workflow_dispatch:` siempre incluido para poder lanzar el análisis manualmente sin necesidad de hacer un commit.

---

### 15.2 Working directory en monorepo

Tres lugares donde se debe especificar el directorio del servicio:

| Dónde | Configuración | Para qué |
|---|---|---|
| `defaults.run.working-directory` | `working-directory: validation-service` | Todos los steps `run:` usan ese dir como base |
| `sonarqube-scan-action` | `projectBaseDir: validation-service` | El scanner sabe dónde está el código fuente |
| `sonarqube-quality-gate-action` | `scanMetadataReportFile: validation-service/.scannerwork/report-task.txt` | El QG lee el reporte correcto |
| `mikepenz/action-junit-report` | `report_paths: 'validation-service/test-results.xml'` | Los resultados de tests se publican con ruta absoluta desde la raíz del repo |
| `actions/upload-artifact` | `path: validation-service/trivy-table.txt` | El artefacto Trivy usa ruta absoluta desde raíz |

**Nota:** `defaults.run.working-directory` aplica solo a steps `run:`. Los steps que usan `uses:` (actions externas) ignoran este default — por eso `projectBaseDir`, `scanMetadataReportFile`, `report_paths`, y `path` deben especificarse con la ruta completa desde la raíz del repo.

---

### 15.3 Un solo job por workflow (no separar SCA)

**Problema original:** separar Trivy en un segundo job generaba 10 checks en el PR (2 por servicio × 5 servicios con tests). Con un job único son 5 checks — uno por servicio.

**Solución:** fusionar el step de Trivy en el job principal. Requiere agregar permisos que antes solo tenía el job de SCA:

```yaml
jobs:
  build-test-sonar:
    permissions:
      checks: write
      contents: read
      security-events: write    # ← necesario para Trivy SARIF upload (si aplica)
      actions: read             # ← necesario para mikepenz/action-junit-report
```

**Orden de steps en el job fusionado:**
1. `actions/checkout@v4` (con `fetch-depth: 0`)
2. Setup Python + Cache SonarQube
3. Install dependencies
4. Run unit tests (`continue-on-error: true` si hay tests conocidos rotos — ver §15.5)
5. Publicar resultados de tests (`if: always()`, mikepenz)
6. SonarQube Scan (`if: always()` — corre aunque pytest falle)
7. Resumen SonarQube en summary (`if: always()`)
8. Quality Gate — **sin** `continue-on-error` (bloquea el PR si falla)
9. Trivy scan + resumen (`if: always()` — corre aunque QG falle)
10. Upload artefacto Trivy (`if: always()`)

El `if: always()` en Trivy es crítico: si el Quality Gate bloquea, el step de Trivy igualmente corre y deja el reporte de vulnerabilidades disponible.

---

### 15.4 SonarQube en monorepo — auto-provisioning

**No crear proyectos manualmente en SonarQube.** Con un token de tipo *Global Analysis* los proyectos se crean automáticamente en el primer scan.

**Project keys simples** (sin prefijo de organización):

```yaml
env:
  SONAR_PROJECT_KEY: 'validation-service'   # ✅ simple, auto-creado
  # SONAR_PROJECT_KEY: 'Templaris:Validation-Service'  # ❌ requiere proyecto pre-existente
```

**Args de Sonar para un servicio Python con tests y cobertura:**

```yaml
args: >
  -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
  -Dsonar.projectName="Validation Service"
  -Dsonar.sources=app
  -Dsonar.exclusions=**/__pycache__/**,**/venv/**,**/.venv/**,**/*.pyc,**/tests/**
  -Dsonar.tests=tests
  -Dsonar.test.inclusions=**/test_*.py
  -Dsonar.python.coverage.reportPaths=coverage.xml
  -Dsonar.python.version=3.11
  -Dsonar.qualitygate.wait=false
  -Dsonar.coverage.exclusions=app/api/**,app/main.py,app/config.py
```

**Args para un servicio sin suite de tests** (ver §15.6):

```yaml
args: >
  -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
  -Dsonar.projectName="Adapter Service"
  -Dsonar.sources=app
  -Dsonar.exclusions=**/__pycache__/**,**/venv/**,**/.venv/**,**/*.pyc
  -Dsonar.python.version=3.11
  -Dsonar.qualitygate.wait=false
  # sin -Dsonar.python.coverage.reportPaths — no hay cobertura que reportar
```

**`sonar.qualitygate.wait=false`** — el scanner no espera el resultado del análisis. El step siguiente (`sonarqube-quality-gate-action`) se encarga de esperar y evaluar el QG. Esto permite que el resumen del summary muestre métricas correctas mientras el QG corre en paralelo en el servidor Sonar.

---

### 15.5 Servicios con tests rotos o cobertura insuficiente (TEMPORAL)

Durante la primera implementación del pipeline puede haber tests que fallan por deuda técnica preexistente (modelos eliminados, argumentos faltantes, cobertura < 80%). La estrategia es **no bloquear el pipeline por deuda existente, pero sí reportarla**:

```yaml
- name: Run unit tests with coverage
  # TEMPORAL — continue-on-error: true: el test falla por <razón específica>.
  # Quitar cuando se corrija <test> y la cobertura suba a 80%.
  continue-on-error: true
  run: |
    pytest tests/unit/ -v \
      --cov=app \
      --cov-report=xml:coverage.xml \
      --cov-report=term-missing \
      --junitxml=test-results.xml \
      --tb=short
```

**Reglas:**
- `continue-on-error: true` solo en el step de pytest, nunca en el Quality Gate
- Documentar el motivo exacto en el comentario (`# TEMPORAL — ...`)
- El equipo de desarrollo es responsable de eliminar el `continue-on-error` cuando corrija el test
- El paso de Sonar lleva `if: always()` para que corra aunque pytest falle y envíe la cobertura parcial

**El Quality Gate SÍ puede fallar** (y bloquear el PR) si la cobertura parcial no cumple el umbral configurado en Sonar — eso es el comportamiento correcto. Si el equipo necesita desbloquear temporalmente, debe ajustar el Quality Gate en el servidor Sonar, no en el workflow.

---

### 15.6 Servicios sin suite de tests

Algunos servicios solo tienen análisis estático (sin pytest, sin JUnit, sin cobertura). El workflow es más simple:

```yaml
jobs:
  sonar:                          # nombre del job: "sonar" en lugar de "build-test-sonar"
    name: SonarQube
    # (sin Setup Python, sin Install deps, sin pytest, sin mikepenz)
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: SonarQube Scan
        uses: sonarsource/sonarqube-scan-action@master
        # sin -Dsonar.python.coverage.reportPaths
        # sin -Dsonar.tests

      # Resumen SonarQube + Quality Gate + Trivy (igual que §15.3)
```

El resumen en el summary debe reflejar que no hay cobertura:

```bash
> ℹ️ Sin cobertura — este servicio no tiene suite de unit tests aún.
```

---

### 15.7 Template completo — servicio Python con tests (monorepo)

```yaml
name: PR Check — NombreServicio

on:
  workflow_dispatch:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
    paths:
      - 'nombre-servicio/**'

env:
  SONAR_PROJECT_KEY: 'nombre-servicio'

jobs:
  build-test-sonar:
    name: Tests & SonarQube
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    defaults:
      run:
        working-directory: nombre-servicio

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio httpx

      - name: Run unit tests with coverage
        continue-on-error: true  # quitar cuando todos los tests pasen y cobertura ≥ 80%
        run: |
          pytest tests/unit/ -v \
            --cov=app \
            --cov-report=xml:coverage.xml \
            --cov-report=term-missing \
            --junitxml=test-results.xml \
            --tb=short

      - name: Encabezado Unit Tests en summary
        if: always()
        run: |
          echo "## 🧪 Unit Tests — NombreServicio" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: 'nombre-servicio/test-results.xml'
          check_name: 'Unit Tests — NombreServicio'

      - name: SonarQube Scan
        if: always()
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          projectBaseDir: nombre-servicio
          args: >
            -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
            -Dsonar.projectName="NombreServicio"
            -Dsonar.sources=app
            -Dsonar.exclusions=**/__pycache__/**,**/venv/**,**/.venv/**,**/*.pyc,**/tests/**
            -Dsonar.tests=tests
            -Dsonar.test.inclusions=**/test_*.py
            -Dsonar.python.coverage.reportPaths=coverage.xml
            -Dsonar.python.version=3.11
            -Dsonar.qualitygate.wait=false
            -Dsonar.coverage.exclusions=app/api/**,app/main.py,app/config.py

      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          REPORT=".scannerwork/report-task.txt"
          if [ ! -f "$REPORT" ]; then
            echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
            echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi

          DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
          CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)

          for i in $(seq 1 12); do
            TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
              "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
            if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
              break
            fi
            sleep 5
          done

          QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ env.SONAR_PROJECT_KEY }}" 2>/dev/null || echo "{}")
          QG_STATUS=$(echo "$QG_JSON" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")

          METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/measures/component?component=${{ env.SONAR_PROJECT_KEY }}&metricKeys=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots" 2>/dev/null || echo "{}")

          parse_metric() {
            echo "$METRICS_JSON" | python3 -c \
              "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
          }

          COVERAGE=$(parse_metric coverage)
          DUPLICATIONS=$(parse_metric duplicated_lines_density)
          BUGS=$(parse_metric bugs)
          VULNERABILITIES=$(parse_metric vulnerabilities)
          CODE_SMELLS=$(parse_metric code_smells)
          SEC_HOTSPOTS=$(parse_metric security_hotspots)

          if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
          elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
          else                                  QG_BADGE="⚠️ $QG_STATUS"
          fi

          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔍 SonarQube — $QG_BADGE

          | Métrica | Valor | Umbral |
          |---------|-------|--------|
          | Quality Gate | $QG_BADGE | — |
          | Coverage | ${COVERAGE}% | ≥ 80% |
          | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
          | Bugs | $BUGS | 0 críticos |
          | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
          | Code Smells | $CODE_SMELLS | — |
          | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

          [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
          SUMMARY

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          scanMetadataReportFile: nombre-servicio/.scannerwork/report-task.txt

      - name: Trivy — escanear y guardar tabla
        if: always()
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

          trivy fs . \
            --severity CRITICAL,HIGH,MEDIUM \
            --ignore-unfixed \
            --skip-dirs '.git,__pycache__,venv,.venv' \
            --format table \
            --output trivy-table.txt 2>/dev/null || true

          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")

          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then
            SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"
          else
            SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"
          fi

          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-nombre-servicio-${{ github.run_id }}
          path: nombre-servicio/trivy-table.txt
          retention-days: 30
```

**Variables a reemplazar:** `NombreServicio` → nombre legible, `nombre-servicio` → nombre del directorio (kebab-case), `3.11` → versión Python del servicio.

---

### 15.8 Checklist para agregar un nuevo microservicio al monorepo

```
[ ] Crear .github/workflows/pr-check-<nombre-servicio>.yml copiando §15.7
[ ] Reemplazar todas las ocurrencias de "nombre-servicio" y "NombreServicio"
[ ] Ajustar python-version al valor del servicio (buscar en el Dockerfile o pyproject.toml)
[ ] Si el servicio NO tiene tests: usar el template simplificado de §15.6
[ ] Si el servicio SÍ tiene tests pero hay tests rotos: agregar continue-on-error: true con comentario explicativo
[ ] Verificar que requirements.txt existe en el directorio del servicio
[ ] Verificar que tests/unit/ existe (o ajustar la ruta de pytest)
[ ] En el primer PR que toque el servicio: revisar que el proyecto se auto-creó en SonarQube
[ ] Confirmar que el Quality Gate del nuevo proyecto en Sonar tiene los umbrales correctos (coverage ≥ 80%, duplications ≤ 3%, vulnerabilities = 0)
[ ] Verificar que aparece exactamente 1 check en el PR (no 2 — si aparecen 2 hay un job sobrante)
```

---

### 15.9 Lección aprendida — Templaris BPM Backend (mayo 2026)

**Contexto:** monorepo con 6 microservicios Python/FastAPI. Primera implementación de CI en un repo que ya tenía código productivo pero sin pipeline.

**Hallazgos clave:**

1. **Tests desactualizados bloquean el pipeline más que el código:** `validation-service` tenía `ImportError: cannot import name 'BatchLoad' from 'app.database.models'` — el modelo fue eliminado del código pero los tests no se actualizaron. El pipeline lo detectó; el equipo no lo sabía. Fix: `continue-on-error: true` temporal + ticket al equipo de dev.

2. **El mensaje "no generó reporte (posible fallo de conexión)" es engañoso:** la causa real era que pytest fallaba con exit code 1 y el step de SonarQube era `skipped` (no tenía `if: always()`). El scanner nunca corrió, nunca creó `.scannerwork/report-task.txt`. Fix: agregar `if: always()` al step de Sonar.

3. **`workflow_dispatch` solo funciona desde la rama default:** si los workflows solo existen en una rama feature, no aparecen en el menú de "Run workflow" hasta que esa rama sea la default o los workflows se mergeen a main/develop. Para testear, temporalmente cambiar la rama default del repo o hacer merge directo.

4. **La Quality Gate marca verde aunque Sonar falle si hay `continue-on-error: true`:** el step sale con exit 0 aunque internamente el QG esté en ERROR. Quitar siempre `continue-on-error` del step Quality Gate.

5. **Trivy corre 3 veces en el script original (una por severidad + una combinada):** es redundante pero funcional. Si el tiempo de CI es crítico, consolidar en un único scan JSON y filtrar por severidad en Python.

6. **`paths:` en el trigger no funciona con `workflow_dispatch`:** al lanzar manualmente, el workflow corre sin importar qué archivos cambiaron. Es el comportamiento esperado y correcto para lanzamientos manuales de análisis.

7. **Convención de nombres de rama:** el equipo usa `feature/` no `feat/`. Definir la convención en el CLAUDE.md del repo desde el inicio para que la IA no genere nombres incorrectos.

8. **Al migrar a reusable workflows, el caller debe declarar los mismos `permissions` que el reusable:** si el reusable workflow tiene `permissions: checks: write, security-events: write` en su job y el wrapper caller no los declara, GitHub falla con `startup_failure` antes de crear cualquier job. El síntoma es idéntico al de un error de YAML — 1-3 segundos, sin logs. Ver §16.6.1 para el diagnóstico completo y el fix.

---

## 16. Distribución org-level — repo `trycore-co/.github`

GitHub reconoce un repositorio especial llamado `.github` dentro de una organización. Sirve para tres cosas: centralizar la guía de estándares, definir reusable workflows que todos los repos de la org pueden invocar, y mostrar community health files (CONTRIBUTING, SECURITY, etc.) automáticamente en todos los repos.

---

### 16.1 Secrets y variables a nivel de organización

El primer paso es mover `SONAR_TOKEN` y `SONAR_HOST_URL` de nivel de repositorio a nivel de organización. Así no hay que configurarlos en cada repo nuevo.

**SONAR_TOKEN (secret):**

1. Ir a `github.com/organizations/trycore-co/settings/secrets/actions`
2. Click en **New organization secret**
3. Name: `SONAR_TOKEN`
4. Value: el token de SonarQube (`squ_...`)
5. Repository access: **All repositories**
6. Save

**SONAR_HOST_URL (variable — no es un secreto):**

1. Ir a `github.com/organizations/trycore-co/settings/variables/actions`
2. Click en **New organization variable**
3. Name: `SONAR_HOST_URL`
4. Value: `https://docs.trycore.co:9000`
5. Repository access: **All repositories**
6. Save

Después de esto, `${{ secrets.SONAR_TOKEN }}` y `${{ vars.SONAR_HOST_URL }}` funcionan en cualquier workflow de cualquier repo de la org, sin configuración adicional. Los valores definidos a nivel de repo tienen precedencia si se define el mismo nombre — pero si solo existen a nivel org, se heredan automáticamente.

---

### 16.2 Estructura del repo `trycore-co/.github`

```
trycore-co/.github/
├── profile/
│   └── README.md                          # Página pública de la org en GitHub
├── docs/
│   └── BUENAS-PRACTICAS-PIPELINE.md       # Fuente de verdad de esta guía
├── CONTRIBUTING.md                         # Aparece en todos los repos de la org
├── SECURITY.md                             # Política de reporte de vulnerabilidades
└── .github/
    └── workflows/
        ├── reusable-pr-check-python.yml    # §16.3 — para servicios Python
        └── reusable-pr-check-node.yml      # §16.4 — para frontends Node.js
```

**La guía vive en `trycore-co/.github/docs/BUENAS-PRACTICAS-PIPELINE.md`.** Cada repo individual enlaza desde su README:

```markdown
## Pipeline CI/CD
Ver [Buenas Prácticas — Pipelines](https://github.com/trycore-co/.github/blob/main/docs/BUENAS-PRACTICAS-PIPELINE.md)
```

---

### 16.3 Reusable workflow — Python (todo en uno)

Este workflow encapsula el 100% de la lógica: pytest, cobertura, publicación de resultados, SonarQube Scan, Resumen, Quality Gate y Trivy. Los repos individuales solo definen el trigger y los parámetros del servicio.

**Archivo:** `trycore-co/.github/.github/workflows/reusable-pr-check-python.yml`

```yaml
name: Reusable — PR Check Python Service

on:
  workflow_call:
    inputs:
      service-dir:
        description: 'Directorio del servicio desde la raíz del repo (ej: validation-service)'
        required: true
        type: string
      sonar-project-key:
        required: true
        type: string
      sonar-project-name:
        required: true
        type: string
      python-version:
        required: false
        type: string
        default: '3.11'
      has-tests:
        description: 'true si el servicio tiene suite de unit tests'
        required: false
        type: boolean
        default: true
      tests-continue-on-error:
        description: 'TEMPORAL: true cuando hay tests rotos siendo corregidos'
        required: false
        type: boolean
        default: false
      coverage-exclusions:
        description: 'Patrones Sonar para excluir de cobertura'
        required: false
        type: string
        default: 'app/api/**,app/main.py,app/config.py'
    secrets:
      SONAR_TOKEN:
        required: true

jobs:
  check:
    name: ${{ inputs.has-tests && 'Tests & SonarQube' || 'SonarQube' }}
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    defaults:
      run:
        working-directory: ${{ inputs.service-dir }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        if: ${{ inputs.has-tests }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ inputs.python-version }}
          cache: 'pip'

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Install dependencies
        if: ${{ inputs.has-tests }}
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio httpx

      - name: Run unit tests with coverage
        if: ${{ inputs.has-tests }}
        continue-on-error: ${{ inputs.tests-continue-on-error }}
        run: |
          pytest tests/unit/ -v \
            --cov=app \
            --cov-report=xml:coverage.xml \
            --cov-report=term-missing \
            --junitxml=test-results.xml \
            --tb=short

      - name: Encabezado Unit Tests en summary
        if: ${{ inputs.has-tests }}
        run: |
          echo "## 🧪 Unit Tests — ${{ inputs.sonar-project-name }}" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: ${{ inputs.has-tests }}
        with:
          report_paths: '${{ inputs.service-dir }}/test-results.xml'
          check_name: 'Unit Tests — ${{ inputs.sonar-project-name }}'

      - name: Preparar sonar-project.properties
        if: always()
        run: |
          cat > sonar-project.properties << EOF
          sonar.projectKey=${{ inputs.sonar-project-key }}
          sonar.projectName=${{ inputs.sonar-project-name }}
          sonar.sources=app
          sonar.python.version=${{ inputs.python-version }}
          sonar.qualitygate.wait=false
          EOF

          if [ "${{ inputs.has-tests }}" = "true" ]; then
            cat >> sonar-project.properties << EOF
          sonar.exclusions=**/__pycache__/**,**/venv/**,**/.venv/**,**/*.pyc,**/tests/**
          sonar.tests=tests
          sonar.test.inclusions=**/test_*.py
          sonar.python.coverage.reportPaths=coverage.xml
          sonar.coverage.exclusions=${{ inputs.coverage-exclusions }}
          EOF
          else
            cat >> sonar-project.properties << EOF
          sonar.exclusions=**/__pycache__/**,**/venv/**,**/.venv/**,**/*.pyc
          EOF
          fi

      - name: SonarQube Scan
        if: always()
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          projectBaseDir: ${{ inputs.service-dir }}

      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          REPORT=".scannerwork/report-task.txt"
          if [ ! -f "$REPORT" ]; then
            echo "## 🔍 SonarQube" >> "$GITHUB_STEP_SUMMARY"
            echo "⚠️ El análisis no generó reporte (posible fallo de conexión)." >> "$GITHUB_STEP_SUMMARY"
            exit 0
          fi

          DASHBOARD_URL=$(grep "^dashboardUrl=" "$REPORT" | cut -d= -f2-)
          CE_TASK_ID=$(grep "^ceTaskId=" "$REPORT" | cut -d= -f2-)

          for i in $(seq 1 12); do
            TASK_STATUS=$(curl -sf -u "$SONAR_TOKEN:" \
              "$SONAR_HOST_URL/api/ce/task?id=$CE_TASK_ID" \
              | python3 -c "import sys,json; print(json.load(sys.stdin)['task']['status'])" 2>/dev/null || echo "PENDING")
            if [ "$TASK_STATUS" = "SUCCESS" ] || [ "$TASK_STATUS" = "FAILED" ] || [ "$TASK_STATUS" = "CANCELLED" ]; then
              break
            fi
            sleep 5
          done

          HAS_TESTS="${{ inputs.has-tests }}"
          METRIC_KEYS="duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots"
          [ "$HAS_TESTS" = "true" ] && METRIC_KEYS="coverage,$METRIC_KEYS"

          QG_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=${{ inputs.sonar-project-key }}" 2>/dev/null || echo "{}")
          QG_STATUS=$(echo "$QG_JSON" | python3 -c \
            "import sys,json; print(json.load(sys.stdin).get('projectStatus',{}).get('status','UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")

          METRICS_JSON=$(curl -sf -u "$SONAR_TOKEN:" \
            "$SONAR_HOST_URL/api/measures/component?component=${{ inputs.sonar-project-key }}&metricKeys=$METRIC_KEYS" 2>/dev/null || echo "{}")

          parse_metric() {
            echo "$METRICS_JSON" | python3 -c \
              "import sys,json; m={x['metric']:x.get('value','N/A') for x in json.load(sys.stdin).get('component',{}).get('measures',[])}; print(m.get('$1','N/A'))" 2>/dev/null || echo "N/A"
          }

          COVERAGE=$(parse_metric coverage)
          DUPLICATIONS=$(parse_metric duplicated_lines_density)
          BUGS=$(parse_metric bugs)
          VULNERABILITIES=$(parse_metric vulnerabilities)
          CODE_SMELLS=$(parse_metric code_smells)
          SEC_HOTSPOTS=$(parse_metric security_hotspots)

          if   [ "$QG_STATUS" = "OK" ];    then QG_BADGE="✅ PASSED"
          elif [ "$QG_STATUS" = "ERROR" ]; then QG_BADGE="❌ FAILED"
          else                                  QG_BADGE="⚠️ $QG_STATUS"
          fi

          if [ "$HAS_TESTS" = "true" ]; then
            COVERAGE_ROW="| Coverage | ${COVERAGE}% | ≥ 80% |"
          else
            COVERAGE_ROW="> ℹ️ Sin cobertura — este servicio no tiene suite de unit tests aún."
          fi

          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔍 SonarQube — $QG_BADGE

          | Métrica | Valor | Umbral |
          |---------|-------|--------|
          | Quality Gate | $QG_BADGE | — |
          $COVERAGE_ROW
          | Duplicaciones | ${DUPLICATIONS}% | ≤ 3% |
          | Bugs | $BUGS | 0 críticos |
          | Vulnerabilidades | $VULNERABILITIES | 0 críticas |
          | Code Smells | $CODE_SMELLS | — |
          | Security Hotspots | $SEC_HOTSPOTS | 0 sin revisar |

          [📊 Ver análisis completo en SonarQube]($DASHBOARD_URL)
          SUMMARY

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          scanMetadataReportFile: ${{ inputs.service-dir }}/.scannerwork/report-task.txt

      - name: Trivy — escanear y guardar tabla
        if: always()
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin

          trivy fs . \
            --severity CRITICAL,HIGH,MEDIUM \
            --ignore-unfixed \
            --skip-dirs '.git,__pycache__,venv,.venv' \
            --format table \
            --output trivy-table.txt 2>/dev/null || true

          CRITICAL=$(trivy fs . --severity CRITICAL --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          HIGH=$(trivy fs . --severity HIGH --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")
          MEDIUM=$(trivy fs . --severity MEDIUM --ignore-unfixed --skip-dirs '.git,__pycache__,venv,.venv' --format json 2>/dev/null \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))" 2>/dev/null || echo "0")

          if [ "$CRITICAL" = "0" ] && [ "$HIGH" = "0" ]; then
            SCA_STATUS="✅ Sin vulnerabilidades CRITICAL/HIGH"
          else
            SCA_STATUS="⚠️ Vulnerabilidades encontradas (modo informativo)"
          fi

          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🛡️ SCA — Trivy — $SCA_STATUS

          | Severidad | Vulnerabilidades encontradas |
          |-----------|----------------------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |
          | 🟡 Medium | $MEDIUM |

          > Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
          SUMMARY

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-${{ inputs.service-dir }}-${{ github.run_id }}
          path: ${{ inputs.service-dir }}/trivy-table.txt
          retention-days: 30
```

---

### 16.4 Wrapper por servicio — lo que queda en cada repo

Una vez que el reusable workflow existe en `trycore-co/.github`, cada archivo de workflow por servicio se reduce a esto:

```yaml
name: PR Check — Validation Service

on:
  workflow_dispatch:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
    paths:
      - 'validation-service/**'

jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: validation-service
      sonar-project-key: validation-service
      sonar-project-name: Validation Service
      python-version: '3.11'
      has-tests: true
      tests-continue-on-error: true   # TEMPORAL — remover cuando se corrijan los tests
    secrets: inherit
```

> ⚠️ **`permissions:` es obligatorio en el caller.** Cuando el reusable workflow declara `permissions:` a nivel de job, GitHub exige que el caller también declare esos mismos permisos — de lo contrario falla con `startup_failure` antes de crear cualquier job. Ver §16.6.1 para el detalle.

**`secrets: inherit`** — pasa TODOS los secrets del repo/org al reusable workflow, incluyendo `SONAR_TOKEN`. No hay que declararlos explícitamente.

**`vars.SONAR_HOST_URL`** — las variables de organización son accesibles directamente en el reusable workflow sin pasarlas como input. GitHub las resuelve en el contexto de la org del caller.

**Parámetros por servicio en este monorepo:**

| Servicio | `has-tests` | `python-version` | `tests-continue-on-error` |
|---|---|---|---|
| `validation-service` | `true` | `3.11` | `true` (TEMPORAL) |
| `batch-loader-service` | `true` | `3.11` | `true` (TEMPORAL) |
| `pdf-generator-service` | `true` | `3.11` | `true` (TEMPORAL) |
| `ms-observability` | `true` | `3.12` | `false` |
| `ms-file-management` | `false` | `3.11` | — |
| `adapter-service` | `false` | `3.11` | — |

---

### 16.5 Guía de migración — de copy-paste a reusable

**Paso 1 — Crear el repo org:**
```
GitHub → New repository → Owner: trycore-co → Name: .github → Public → Create
```

**Paso 2 — Subir la guía:**
```bash
git clone git@github.com:trycore-co/.github.git
mkdir -p docs .github/workflows
cp BUENAS-PRACTICAS-PIPELINE.md docs/
# pegar el contenido de §16.3 en .github/workflows/reusable-pr-check-python.yml
git add . && git commit -m "feat: reusable PR check workflow + guía de buenas prácticas"
git push origin main
```

**Paso 3 — Mover secrets/variables a nivel org (§16.1)**

**Paso 4 — Actualizar los workflows en cada repo:**
- Reemplazar el contenido de cada `pr-check-*.yml` por el wrapper de §16.4
- Los wrappers usan `uses: trycore-co/.github/...@main` — funcionan porque el reusable workflow ya está en main del org repo

**Paso 5 — Eliminar secrets/variables duplicados a nivel de repo** (los org-level ya los cubren)

**Para repos futuros:** solo copiar el wrapper de §16.4, cambiar 4 parámetros, listo.

---

### 16.6 Cuándo NO usar el reusable workflow

- El servicio usa un stack diferente (Java, Node.js) — crear un reusable workflow específico para ese stack
- El servicio tiene un proceso de instalación muy distinto (ej. LibreOffice para pdf-generator) — puede valer la pena un input extra o un workflow propio
- Se necesita mayor control sobre cada step para depurar un problema — temporalmente volver al workflow expandido hasta resolver

---

### 16.6.1 Lección aprendida — `startup_failure` por permissions en reusable workflows

**Síntoma:** todos los workflows fallan en 1-3 segundos con `startup_failure`. `gh run view` muestra `jobs: []` — ningún job se crea.

**Causa:** GitHub valida en startup que el **caller** tenga declarados los mismos `permissions` que el reusable workflow solicita a nivel de job. Si el reusable workflow tiene:

```yaml
jobs:
  check:
    permissions:
      checks: write
      security-events: write
      ...
```

…y el caller no declara esos permisos en su job, GitHub rechaza la ejecución antes de crear cualquier job. No hay logs de error disponibles — solo `startup_failure`.

**Fix:** declarar los mismos permisos en el job del **caller**:

```yaml
jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main
    permissions:          # ← OBLIGATORIO cuando el reusable declara permissions
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      ...
    secrets: inherit
```

**Regla:** si el reusable workflow tiene `permissions:` en el job, el caller siempre debe tenerlos también. El bloque del wrapper crece de 20 a 25 líneas, pero es obligatorio.

**Cómo diagnosticar `startup_failure` en general:**

```bash
# Ver si se crearon jobs
gh api repos/<org>/<repo>/actions/runs/<run-id>/jobs | python3 -c "import sys,json; print(json.load(sys.stdin)['total_count'])"
# Si es 0 → startup_failure real (GitHub rechazó el workflow antes de empezar)

# Ver qué SHA del reusable se usó
gh api repos/<org>/<repo>/actions/runs/<run-id> | python3 -c "import sys,json; [print(w) for w in json.load(sys.stdin).get('referenced_workflows',[])]"
```

Si `total_count: 0`, el problema está en la **definición** del workflow (YAML inválido, permissions faltantes en el caller, o expresión en lugar de valor literal en un campo que no lo admite como `defaults.run.working-directory`).

---

---

### 16.6.2 Regla — nunca poner env vars de proyecto en un reusable workflow

Un reusable workflow es **infraestructura compartida** — lo usan todos los repos de la org. Cualquier variable de entorno que se agregue al reusable se inyecta en absolutamente todos los proyectos que lo invocan, aunque esos proyectos no usen esa tecnología.

**Está prohibido:**

```yaml
# ❌ MAL — en reusable-pr-check-python.yml
- name: Run unit tests with coverage
  env:
    FIREBASE_PROJECT_ID: "mi-proyecto"      # config específica de un proyecto
    FIRESTORE_EMULATOR_HOST: "localhost:8686"
    REDIS_HOST: "localhost"
```

Aunque se use fallback con variables de org (`${{ vars.ALGO || 'default' }}`), el problema persiste: la variable se inyecta en todos los proyectos con un valor por defecto que puede interferir con sus tests o enmascarar errores de configuración.

**La solución correcta: env vars del proyecto van en el wrapper del repo del proyecto**

```yaml
# ✅ BIEN — en .github/workflows/pr-check-mi-servicio.yml (en el repo del proyecto)
jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: mi-servicio
      sonar-project-key: mi-servicio
      sonar-project-name: Mi Servicio
      python-version: '3.11'
      has-tests: true
    secrets: inherit
    # Las env vars propias del proyecto se manejan como GitHub repository variables/secrets
    # y se referencian directamente desde el código de tests — no se pasan al reusable
```

Si el proyecto necesita variables de entorno para correr sus tests localmente o en CI, la solución es:

1. Definirlas como **GitHub repository variables** (`Settings → Secrets and variables → Variables`) en el repo del proyecto
2. El código de tests las lee con `os.getenv("MI_VAR")` — sin necesidad de declararlas en el workflow

Si son secretos (tokens, passwords): usar **GitHub repository secrets** y pasarlos con `secrets: inherit`.

**Señal de alerta:** si al modificar el reusable workflow sientes que necesitas agregar una `env:` con un valor específico de tu proyecto, es una señal de que la configuración va en el wrapper del repo, no en el reusable.

---

### 16.6.3 Regla — Quality Gate `continue-on-error` nunca en el reusable

`continue-on-error: true` en el step de Quality Gate significa que el PR **nunca** puede ser bloqueado por calidad — el job siempre reporta verde, independientemente del resultado del análisis. Es una decisión de negocio que corresponde a cada equipo en su propio repo, no algo que deba estar fijo para toda la organización.

**Está prohibido en el reusable:**

```yaml
# ❌ MAL — en reusable-pr-check-python.yml o reusable-pr-check-node.yml
- name: Quality Gate
  uses: sonarsource/sonarqube-quality-gate-action@v1.1.0
  continue-on-error: true    # ← prohíbe que el QG bloquee PRs en TODOS los repos de la org
```

Cuando esto está en el reusable, todos los proyectos de la org pierden la capacidad de bloquear merges por calidad insuficiente, sin importar lo que configuren en su wrapper. No hay forma de contrarrestarlo desde el caller.

**La solución: exponerlo como input y dejarlo en manos del wrapper**

El reusable ya provee el input `tests-continue-on-error` para tests. Si un proyecto necesita desbloquear temporalmente el Quality Gate, tiene dos opciones:

1. **Preferido:** ajustar el umbral directamente en el servidor SonarQube para ese proyecto (más transparente, auditable)
2. **Alternativo temporal:** el reusable puede exponer un input `qg-continue-on-error: boolean` (default `false`) y el wrapper lo activa solo si el equipo lo decide explícitamente

```yaml
# ✅ BIEN — en el reusable: nunca hardcodeado, siempre false por defecto
- name: Quality Gate
  uses: sonarsource/sonarqube-quality-gate-action@v1.1.0
  # sin continue-on-error — si se necesita, agregar input qg-continue-on-error
```

```yaml
# ✅ BIEN — si el equipo decide temporalmente no bloquear, lo declara en su wrapper
jobs:
  check:
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-python.yml@main
    with:
      ...
      # No hay forma de pasar continue-on-error al reusable por diseño
      # Si el QG está fallando, ajustar los umbrales en SonarQube
```

**Por qué esto importa:** §8.4 describe `continue-on-error: true` como medida **TEMPORAL** en workflows de proyecto. Esa temporalidad desaparece si se fija en el reusable — se convierte en permanente para toda la org sin que nadie lo note.

**Señal de alerta:** si al revisar o escribir un reusable workflow ves `continue-on-error: true` en el step de Quality Gate, es un error — retíralo siempre, sin excepción.

---

### 16.6.4 Tabla — qué va en el reusable vs en el wrapper caller

Esta tabla resume las responsabilidades de cada capa para evitar que lógica de proyecto contamine el reusable, o que el reusable quede incompleto.

| Elemento | Reusable workflow | Wrapper caller (repo del proyecto) |
|---|---|---|
| Lógica completa del análisis (pytest, sonar scan, trivy) | ✅ Aquí | ❌ No duplicar |
| `permissions:` del job | ✅ Aquí (declarar siempre) | ✅ Aquí también (obligatorio — §16.6.1) |
| `on: workflow_call:` con `inputs:` y `secrets:` | ✅ Aquí | ❌ No aplica |
| `on: pull_request:` con `branches:` y `paths:` | ❌ No aplica | ✅ Aquí |
| `service-dir`, `sonar-project-key`, `python-version` | Declarar como input | Pasar el valor concreto |
| `has-tests`, `tests-continue-on-error` | Declarar como input (default `false`) | Pasar `true` si aplica |
| `env:` con vars de entorno específicas del proyecto | ❌ Prohibido (§16.6.2) | ✅ Aquí, o como repo variables/secrets |
| `continue-on-error` en Quality Gate | ❌ Prohibido (§16.6.3) | Solo si el equipo lo decide y lo documenta |
| URLs, tokens, endpoints de infraestructura propia | ❌ Prohibido (§16.6.2) | Pasar vía `secrets: inherit` o repo vars |
| Step de resumen (GitHub Step Summary) | ✅ Aquí — todos ven el mismo formato | ❌ No sobreescribir |
| `workflow_dispatch:` para tests manuales | ❌ No aplica | ✅ Agregar siempre |
| Jobs específicos del proyecto (E2E, smoke tests, migraciones) | ❌ No agregar al reusable | ✅ Definir como job adicional en el wrapper |

**Regla general:** el reusable define el **cómo** (pasos, herramientas, formato de reporte). El wrapper define el **qué** (qué servicio, qué rama, qué parámetros de proyecto).

**El wrapper puede tener más de un job.** Si un proyecto necesita un paso que no existe en el reusable (E2E con Playwright, smoke test contra staging, migración de DB), se agrega como job adicional en el propio wrapper — no en el reusable. Esto evita que lógica específica de un proyecto afecte a los demás:

```yaml
# .github/workflows/pr-check-mi-proyecto.yml
jobs:
  check:                                # ← llama al reusable estándar
    uses: trycore-co/.github/.github/workflows/reusable-pr-check-node.yml@main
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    with:
      service-dir: mi-servicio
      sonar-project-key: mi-servicio
      sonar-project-name: Mi Servicio
    secrets: inherit

  e2e-tests:                            # ← job propio del proyecto, con su propia lógica
    name: E2E — Playwright
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
        working-directory: mi-servicio
      - name: Run E2E tests
        working-directory: mi-servicio
        env:
          VITE_DEV_AUTH: "true"
          VITE_FIREBASE_PROJECT_ID: ${{ vars.FIREBASE_PROJECT_ID }}
        run: npx playwright test
```

Si ese patrón E2E eventualmente es común a varios proyectos Node, se puede crear un segundo reusable (`reusable-e2e-playwright-node.yml`) genérico y sin vars hardcodeadas — pero solo cuando haya dos o más proyectos que compartan exactamente la misma lógica.

### 16.6.5 Lección aprendida — Quality Gate UNKNOWN por whitespace en SONAR_HOST_URL

**Proyecto:** Diagramador BPMN (mayo 2026). Detectado por Freyder Cárdenas.

**Síntoma:** el Quality Gate aparece como `⚠️ UNKNOWN` en el Step Summary, aunque el SonarQube Scan completa sin errores. El step `sonarqube-quality-gate-action` también pasa (con `continue-on-error: true`), pero la métrica no refleja el estado real del proyecto.

**Causa:** la variable de organización `SONAR_HOST_URL` tenía un carácter de whitespace invisible (salto de línea `\n` o espacio) al inicio o al final del valor. Al usarla directamente con `${{ vars.SONAR_HOST_URL }}` en el `env:` del step de Sonar, la URL resultante era inválida y las llamadas curl a la API de SonarQube fallaban silenciosamente.

**Diagnóstico rápido:**
```bash
# En el log del step "Resumen SonarQube", buscar esta línea:
curl -sf -u "$SONAR_TOKEN:" "$SONAR_HOST_URL/api/qualitygates/project_status?..."

# Si SONAR_HOST_URL tiene whitespace, la URL llega malformada y el curl
# retorna vacío → el python3 -c parser devuelve "UNKNOWN"
```

**Fix aplicado en los reusable workflows (Node y Python):**

En lugar de pasar `vars.SONAR_HOST_URL` directo al `env:` de cada step, se sanitiza **una sola vez** al inicio del job y se exporta a `$GITHUB_ENV`:

```yaml
- name: Sanitizar project key y variables de Sonar
  id: artifact
  run: |
    echo "key=$(echo '${{ inputs.sonar-project-key }}' | tr ':' '-')" >> "$GITHUB_OUTPUT"
    echo "SONAR_HOST_URL=$(echo '${{ vars.SONAR_HOST_URL }}' | tr -d '[:space:]')" >> "$GITHUB_ENV"
```

Todos los steps siguientes usan `${{ env.SONAR_HOST_URL }}` en lugar de `${{ vars.SONAR_HOST_URL }}`.

**Fix en la variable de org (corrección en la fuente):**

El workaround del `tr -d '[:space:]'` es defensivo y debe mantenerse, pero también conviene corregir la variable en la fuente para evitar confusión futura:

1. Ir a `GitHub Org (trycore-co) → Settings → Secrets and variables → Actions → Variables`
2. Editar `SONAR_HOST_URL`
3. Borrar el contenido completo del campo y volver a escribir solo: `https://docs.trycore.co:9000`  (sin espacios, sin saltos de línea)
4. Guardar

> **Nota:** el textarea de GitHub no muestra saltos de línea invisibles — un `\n` al final del valor se ve igual que un valor limpio. Si la variable fue creada via script o copia/pega desde una terminal, es frecuente que arrastre un newline.

**Impacto:** afecta cualquier reusable workflow que use `${{ vars.SONAR_HOST_URL }}` directamente en un `env:` sin sanitizar. Al migrar a `env.SONAR_HOST_URL` (seteado desde `$GITHUB_ENV`), el fix aplica automáticamente a todos los repos que usen el reusable — no requiere cambios en los wrappers de cada proyecto.

**Repos afectados (confirmados):**
- `trycore-co/diagramador-bpmn-draw-my-process` — primer repo en migrar a reusable Node
- `trycore-co/docfly-paginas-backend` — usa reusable Python
- `trycore-co/templaris-bpm-backend-ms` — 6 workflows usando reusable Python


---

## 16.7 Migración de un repo existente al wrapper reusable

> **Prerequisito:** `trycore-co/.github` ya tiene el reusable workflow (`§16.3`) y los secrets/variables ya son de organización (`§16.1`). Si no es así, hacer esos pasos primero.

Esta sección describe cómo tomar un repo que ya tiene un workflow inline de ~170 líneas y convertirlo al wrapper de 25 líneas, sin perder ningún informe ni funcionalidad.

---

### 16.7.1 Antes de empezar — inventariar el workflow actual

Leer el archivo `.github/workflows/pr-check-*.yml` existente y anotar:

| Parámetro | Dónde mirarlo | Ejemplo |
|---|---|---|
| `service-dir` | `working-directory:` en los steps `run:` | `validation-service` |
| `sonar-project-key` | `-Dsonar.projectKey=` o `sonar-project.properties` | `validation-service` |
| `sonar-project-name` | `-Dsonar.projectName=` | `Validation Service` |
| `python-version` | `python-version:` en setup-python | `3.11` |
| `has-tests` | ¿Hay un step de pytest? `true` / `false` | `true` |
| `tests-continue-on-error` | ¿El step de pytest tiene `continue-on-error: true`? | `false` |
| `coverage-exclusions` | `sonar.coverage.exclusions=` en properties | `app/api/**,app/main.py` |

Si el workflow existente tiene `SONAR_TOKEN` o `SONAR_HOST_URL` como secrets/variables de repo, verificar que ya existen a nivel org antes de borrarlos del repo:

```bash
# Verificar que el secret de org llega al repo
gh secret list --repo trycore-co/<nombre-repo>   # debe aparecer SONAR_TOKEN como "org" source
```

---

### 16.7.2 Paso a paso

**Paso 1 — Reemplazar el contenido del workflow**

```bash
# Dentro del repo a migrar, en la rama donde vas a trabajar
cat > .github/workflows/pr-check-<nombre-servicio>.yml << 'EOF'
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
      sonar-project-key: <sonar-project-key>
      sonar-project-name: <Sonar Project Name>
      python-version: '3.11'
      has-tests: true
      tests-continue-on-error: false
    secrets: inherit
EOF
```

Ajustar los 6 valores marcados con `<>` usando el inventario del §16.7.1. Si el servicio no tiene tests: `has-tests: false` y eliminar `tests-continue-on-error`.

**Paso 2 — Eliminar el workflow viejo** (si el archivo era uno solo y se reemplazó in-place, este paso no aplica)

```bash
git rm .github/workflows/pr-check-<nombre>-old.yml   # solo si había un archivo separado
```

**Paso 3 — Commit y push a la rama feature**

```bash
git add .github/workflows/pr-check-<nombre-servicio>.yml
git commit -m "ci: migrar pr-check a reusable workflow de org"
git push origin <rama>
```

**Paso 4 — Validar que no hay `startup_failure`**

```bash
# Esperar 5 segundos para que GitHub indexe el nuevo workflow
gh workflow run pr-check-<nombre-servicio>.yml --ref <rama>
sleep 10
gh run list --workflow=pr-check-<nombre-servicio>.yml --limit=1
```

Si el resultado es `startup_failure` en menos de 5 segundos: revisar §16.6.1. Los dos culpables más comunes son `permissions:` faltante en el job caller o que el reusable workflow no está en `main` del org repo.

Si el resultado es `in_progress`: el wrapper está corriendo correctamente. Esperar a que termine.

**Paso 5 — Opcional: limpiar secrets/variables de repo**

Si `SONAR_TOKEN` existía a nivel de repo, eliminarlo para no tener duplicados (el org-level lo cubre):

```
GitHub → <repo> → Settings → Secrets and variables → Actions → eliminar SONAR_TOKEN de repo
```

---

### 16.7.3 Informes que genera el pipeline — qué esperar ver

Una vez migrado, cada ejecución produce tres bloques de informes en la pestaña **Summary** del workflow run y una anotación en el PR.

**1 — Unit Tests (JUnit)**

Generado por `mikepenz/action-junit-report@v4`. Aparece como check independiente en el PR ("Unit Tests — \<Nombre\>") con el detalle de tests pasados/fallidos.

```
✓ 42 tests passed
✗  3 tests failed
  └── test_event_producer.py::test_publish_timeout — AssertionError
```

Solo aparece si `has-tests: true`. Si el paso de pytest falla y `tests-continue-on-error: false`, este check marca el PR como bloqueado.

**2 — SonarQube Summary**

Aparece en el Step Summary de Actions con esta tabla:

```markdown
## 🔍 SonarQube — ✅ PASSED

| Métrica            | Valor  | Umbral       |
|--------------------|--------|--------------|
| Quality Gate       | ✅ PASSED | —          |
| Coverage           | 87.3%  | ≥ 80%       |
| Duplicaciones      | 1.2%   | ≤ 3%        |
| Bugs               | 0      | 0 críticos  |
| Vulnerabilidades   | 0      | 0 críticas  |
| Code Smells        | 4      | —           |
| Security Hotspots  | 0      | 0 sin revisar|

[📊 Ver análisis completo en SonarQube](https://...)
```

Si `has-tests: false`, la fila de Coverage **no aparece en la tabla** — en su lugar aparece una nota informativa debajo de ella. El Quality Gate aparece como `❌ FAILED` si algún umbral se supera, lo que bloquea el merge.

> ⚠️ **No insertar texto libre dentro del bloque de tabla markdown.** Un blockquote (`> texto`) dentro de un HEREDOC que contiene una tabla quiebra el renderizado — las filas siguientes se muestran como texto plano. La solución es usar `echo` statements condicionales para construir la tabla y agregar elementos opcionales fuera de ella.

**3 — Trivy SCA**

Aparece en el Step Summary justo después de SonarQube:

```markdown
## 🛡️ SCA — Trivy — ✅ Sin vulnerabilidades CRITICAL/HIGH

| Severidad     | Vulnerabilidades encontradas |
|---------------|------------------------------|
| 🔴 Critical   | 0                            |
| 🟠 High       | 0                            |
| 🟡 Medium     | 3                            |

> Solo aplica a dependencias con fix disponible. Modo informativo — no bloquea el pipeline.
```

El reporte completo en formato tabla se sube como artefacto (`trivy-sca-report-<service-dir>-<run-id>`) disponible por 30 días en la pestaña **Artifacts** del run.

**Artefactos descargables:**

| Artefacto | Contenido | Retención |
|---|---|---|
| `trivy-sca-report-<servicio>-<run-id>` | Tabla de vulnerabilidades con CVE, paquete afectado y versión con fix | 30 días |

---

### 16.7.4 Checklist de migración

```
[ ] Inventariar parámetros del workflow viejo (§16.7.1)
[ ] Verificar que SONAR_TOKEN existe como secret de organización
[ ] Reemplazar el archivo con el wrapper de §16.7.2
[ ] Incluir el bloque permissions: en el job check (obligatorio — ver §16.6.1)
[ ] Push a rama feature y ejecutar workflow_dispatch manual
[ ] Confirmar que NO aparece startup_failure (debe ser in_progress o success)
[ ] Confirmar que los 3 bloques de informes aparecen en el Step Summary
[ ] Confirmar que el artefacto trivy-sca-report-* se generó en Artifacts
[ ] Si SONAR_TOKEN existía en repo: eliminarlo (el de org lo cubre)
[ ] Merge a develop/main cuando el primer run sea exitoso
```

---

## 17. Monorepo front + backend

Patrón para un repositorio que contiene un frontend (React/Vite o Angular) y un backend (Python/FastAPI o Java) en subdirectorios separados.

```
mi-proyecto/
├── frontend/          # React + Vite + Vitest
├── backend/           # Python + FastAPI + pytest
└── .github/
    └── workflows/
        ├── pr-check-frontend.yml
        └── pr-check-backend.yml
```

### 17.1 Un workflow por capa

Igual que el monorepo de microservicios (§15), cada capa tiene su propio workflow con `paths:`:

```yaml
# pr-check-frontend.yml
on:
  pull_request:
    paths:
      - 'frontend/**'

# pr-check-backend.yml
on:
  pull_request:
    paths:
      - 'backend/**'
```

**Resultado en el PR:**
- PR que toca solo `frontend/` → dispara solo `PR Check — Frontend`
- PR que toca solo `backend/` → dispara solo `PR Check — Backend`
- PR full-stack → dispara ambos en paralelo

### 17.2 Template — Frontend React/Vite (en monorepo)

Diferencias clave vs §6 (repo dedicado):
- `defaults.run.working-directory: frontend`
- `projectBaseDir: frontend` en sonarqube-scan-action
- `scanMetadataReportFile: frontend/.scannerwork/report-task.txt`
- `report_paths: 'frontend/test-results.xml'`
- `path: frontend/trivy-table.txt`

```yaml
name: PR Check — Frontend

on:
  workflow_dispatch:
  pull_request:
    branches:
      - develop
      - main
      - 'release/**'
    paths:
      - 'frontend/**'

env:
  SONAR_PROJECT_KEY: 'mi-proyecto-frontend'

jobs:
  build-test-sonar:
    name: Tests & SonarQube
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      checks: write
      contents: read
      security-events: write
      actions: read
    defaults:
      run:
        working-directory: frontend

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Cache SonarQube
        uses: actions/cache@v4
        with:
          path: ~/.sonar/cache
          key: ${{ runner.os }}-sonar
          restore-keys: ${{ runner.os }}-sonar

      - name: Install dependencies
        run: npm ci

      - name: Run unit tests with coverage
        run: |
          npm run test -- \
            --reporter=junit \
            --outputFile=test-results.xml \
            --coverage \
            --pool=vmForks

      - name: Encabezado Unit Tests en summary
        if: always()
        run: |
          echo "## 🧪 Unit Tests — Frontend" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"

      - name: Publicar resultados de tests
        uses: mikepenz/action-junit-report@v4
        if: always()
        with:
          report_paths: 'frontend/test-results.xml'
          check_name: 'Unit Tests — Frontend'

      - name: npm audit (seguridad de dependencias)
        if: always()
        run: |
          npm audit --audit-level=high --json > npm-audit.json || true

          CRITICAL=$(python3 -c "
          import json
          d = json.load(open('npm-audit.json'))
          vulns = d.get('vulnerabilities', {})
          print(sum(1 for v in vulns.values() if v.get('severity') == 'critical'))
          " 2>/dev/null || echo "0")

          HIGH=$(python3 -c "
          import json
          d = json.load(open('npm-audit.json'))
          vulns = d.get('vulnerabilities', {})
          print(sum(1 for v in vulns.values() if v.get('severity') == 'high'))
          " 2>/dev/null || echo "0")

          cat >> "$GITHUB_STEP_SUMMARY" << SUMMARY
          ## 🔒 npm audit — Dependencias Frontend

          | Severidad | Vulnerabilidades |
          |-----------|-----------------|
          | 🔴 Critical | $CRITICAL |
          | 🟠 High | $HIGH |

          > Correr \`npm audit fix\` localmente si hay HIGH o CRITICAL.
          SUMMARY

          if [ "$CRITICAL" -gt "0" ]; then
            echo "❌ npm audit encontró vulnerabilidades CRITICAL."
            exit 1
          fi

      - name: SonarQube Scan
        if: always()
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          projectBaseDir: frontend
          args: >
            -Dsonar.projectKey=${{ env.SONAR_PROJECT_KEY }}
            -Dsonar.projectName="Mi Proyecto — Frontend"
            -Dsonar.sources=src
            -Dsonar.exclusions=**/__tests__/**,**/node_modules/**,**/dist/**,coverage/**
            -Dsonar.tests=src
            -Dsonar.test.inclusions=**/*.test.tsx,**/*.test.ts,**/*.spec.ts
            -Dsonar.javascript.lcov.reportPaths=coverage/lcov.info
            -Dsonar.qualitygate.wait=false

      - name: Resumen SonarQube en Actions
        if: always()
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        run: |
          # ── Bloque Sonar Summary (§3.2) ──
          # (mismo bloque que §15.7, ajustando metricKeys para incluir coverage)

      - name: Quality Gate
        uses: sonarsource/sonarqube-quality-gate-action@master
        timeout-minutes: 5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL }}
        with:
          scanMetadataReportFile: frontend/.scannerwork/report-task.txt

      - name: Trivy — escanear y guardar tabla
        if: always()
        run: |
          curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
          trivy fs . \
            --severity CRITICAL,HIGH,MEDIUM \
            --ignore-unfixed \
            --skip-dirs '.git,node_modules,dist' \
            --format table \
            --output trivy-table.txt 2>/dev/null || true
          # ... (resto del script de resumen — igual que §15.7)

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: trivy-sca-report-frontend-${{ github.run_id }}
          path: frontend/trivy-table.txt
          retention-days: 30
```

### 17.3 Template — Backend Python (en monorepo)

Idéntico a §15.7 pero con `frontend` reemplazado por `backend`. No hay diferencias estructurales — solo el directorio y el project key cambian.

### 17.4 Variables de entorno compartidas entre frontend y backend

Si ambas capas comparten el mismo `SONAR_TOKEN` / `SONAR_HOST_URL` (lo más común), no hay configuración adicional — los secrets del repo aplican a todos los workflows.

Si las capas apuntan a **instancias de Sonar distintas** (raro pero posible en proyectos enterprise), usar secrets con nombre diferente:

```yaml
# En pr-check-frontend.yml
env:
  SONAR_TOKEN: ${{ secrets.SONAR_TOKEN_FRONTEND }}
  SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL_FRONTEND }}

# En pr-check-backend.yml
env:
  SONAR_TOKEN: ${{ secrets.SONAR_TOKEN_BACKEND }}
  SONAR_HOST_URL: ${{ vars.SONAR_HOST_URL_BACKEND }}
```

### 17.5 Checklist — nuevo repo front + backend

```
[ ] Crear estructura: frontend/ y backend/ en la raíz del repo
[ ] Crear pr-check-frontend.yml copiando §17.2
[ ] Crear pr-check-backend.yml copiando §15.7
[ ] Ajustar SONAR_PROJECT_KEY en cada workflow (ej: "mi-proyecto-frontend" / "mi-proyecto-backend")
[ ] Confirmar que frontend/ tiene package.json con script "test" que acepta --reporter=junit
[ ] Confirmar que frontend/ tiene script de cobertura que genera coverage/lcov.info
[ ] Confirmar que backend/ tiene requirements.txt y tests/unit/
[ ] Verificar que en el primer PR aparecen exactamente 2 checks (uno por capa)
[ ] Si el PR toca solo una capa, verificar que solo dispara 1 check (paths: filter correcto)
[ ] Revisar en SonarQube que se crearon 2 proyectos independientes (frontend y backend)
```

### 17.6 Cuándo NO separar en dos workflows

Si el proyecto tiene un script de build que necesita frontend + backend juntos (ej. un test E2E que levanta ambos), ese step va en Jenkins post-deploy (§1, §13) — no en el PR check de GitHub Actions. El PR check siempre valida cada capa de forma independiente.
