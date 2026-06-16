# Trycore

Consultoría de software especializada en arquitecturas modernas: microservicios, BPM, integraciones y plataformas de datos.

## Estándares de ingeniería

- [Guía de Pipelines CI/CD](https://github.com/trycore-co/.github/blob/main/docs/BUENAS-PRACTICAS-PIPELINE.md) — GitHub Actions · SonarQube · Trivy · referencia técnica completa
- [Implementar Pipeline en un repo](https://github.com/trycore-co/.github/blob/main/docs/IMPLEMENTAR-PIPELINE.md) — prompts listos para IA · árbol de decisión · casos nuevo vs migración · crear job en Jenkins
- [Jenkins CI/CD — Despliegue on-premise](https://github.com/trycore-co/.github/blob/main/docs/jenkins-cicd-policy.md) — Poll SCM · rollback automático · notificaciones · crear job y credenciales paso a paso

### Reusable workflows disponibles

Los workflows reutilizables viven en `.github/workflows/` de este repo y se consumen desde cualquier repo de la org con ~25 líneas:

| Workflow | Stack | Estado |
|---|---|---|
| `reusable-pr-check-python.yml` | Python · FastAPI · pytest | ✅ Disponible |
| `reusable-pr-check-node.yml` | React · Vite · Vitest · Node.js | ✅ Disponible |
| Java · Spring Boot · Maven | — | Pendiente |
| Angular | — | Pendiente |

Para implementar cualquiera de estos en un repo, seguir la [Guía de Implementación](https://github.com/trycore-co/.github/blob/main/docs/IMPLEMENTAR-PIPELINE.md).

## Stack habitual

- **Backend:** Python (FastAPI), Java (Spring Boot / JHipster), Node.js
- **BPM:** Bonita BPM
- **CI/CD:** GitHub Actions + SonarQube + Trivy
- **Infra:** Docker, Kubernetes, AWS, GCP

## Contacto

[trycore.com.co](https://trycore.com.co) · infraestructura@trycore.com
