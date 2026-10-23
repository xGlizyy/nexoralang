# Despliegue de NEXORA en nexoralang.org

Cómo llega una versión a <https://nexoralang.org> y cómo se ha montado el servidor. En local nada
cambia: `npm start` en `servidor/` con tu `servidor/.env`, como siempre.

## Camino de una versión

1. Un cambio llega a `main` (push o pull request fusionada).
2. **nexora-ci** pasa las pruebas completas (intérprete, paquete de npm, servidor y web).
3. Si el CI termina bien, **nexora-deploy** (`.github/workflows/nexora-deploy.yml`):
   1. prepara la versión (`git archive` de `web`, `servidor`, `docs`, `ejemplos`, `nexora/examples`
      con `npm ci --omit=dev`) y la sube al VPS;
   2. la activa en <https://staging.nexoralang.org>: migra la base de staging, reinicia y comprueba
      `/api/health`; si no arranca, vuelve sola a la versión anterior;
   3. comprueba staging desde fuera (health y las páginas principales) y la marca como verificada;
   4. **espera tu aprobación** en el environment `production` de GitHub;
   5. promueve a producción ese mismo commit y lo comprueba desde fuera.

El VPS se niega a promover un commit que no sea el que hay en staging o que no esté verificado
(`deploy/bin/nexora-deploy`). Y el job de producción se detiene si el environment `production` no
exige revisión, para que un environment sin protección no despliegue sin preguntar. Nada llega a
producción sin pasar por el CI, por staging y por ti.

Para aprobar: GitHub → Actions → la ejecución de *nexora-deploy* → **Review deployments** →
`production` → **Approve and deploy**. Antes puedes revisar staging en el navegador (usuario `nexora`,
la contraseña de staging que guardaste).

La contraseña de staging nunca se muestra: `setup-vps.sh` la deja en `/root/nexora-staging-password`
(solo root), en el formato `nexora:<contraseña>` que espera el secreto `STAGING_BASIC_AUTH`.

## Piezas

| Dónde | Qué |
| --- | --- |
| Cloudflare | DNS con proxy (`@`, `www`, `staging`), SSL **Full (strict)**, TLS mínimo 1.2, *Always Use HTTPS*, Email Routing `support@nexoralang.org` → Gmail. |
| `/etc/nginx/sites-available/nexoralang.org` | `www` → dominio raíz; producción → `127.0.0.1:3100`; staging (contraseña, `noindex`) → `127.0.0.1:3101`. Solo atiende conexiones de Cloudflare; el resto se cortan (444). |
| `/etc/ssl/cloudflare/nexoralang.org.{pem,key}` | Certificado de origen de Cloudflare (hasta 2041). La clave se generó en el VPS y no ha salido de él. |
| `nexora@staging`, `nexora@production` | Servicios systemd (usuario `nexora`, Node de `/opt/node24`, sistema de archivos de solo lectura). |
| `/etc/nexora/<entorno>.env` | Configuración de cada entorno (root:nexora 640). No está en el repositorio. |
| MariaDB (`127.0.0.1:3306`) | Bases `nexora_staging` y `nexora_production`, un usuario por base. |
| `/opt/nexora/releases/<commit>` | Versiones desplegadas (se guardan 5); `/opt/nexora/<entorno>/current` apunta a la activa. |
| `nexora-deploy` | Usuario del CI. Su clave solo puede ejecutar `/opt/nexora/bin/nexora-deploy`, y sudo solo le deja migrar, reiniciar o parar los dos servicios. |
| `nexora-backup.timer` | Copia diaria de las dos bases en `/var/backups/nexora` (14 días). |

## Tareas habituales

Ver qué versión hay en cada entorno:

```sh
ssh contabo 'sudo -u nexora-deploy /opt/nexora/bin/nexora-deploy status'
```

Registros: `journalctl -u nexora@production -f` (o `nexora@staging`, `nexora-migrate@production`).

Volver a una versión anterior: se despliega su commit de nuevo. Revierte el cambio en `main` y el
camino de siempre lo lleva a staging y, con tu aprobación, a producción.

Activar Google, GitHub o reCAPTCHA: rellena las variables en `/etc/nexora/<entorno>.env` (explicadas
en `servidor/.env.example`; las URL de retorno usan `PUBLIC_URL`) y reinicia el servicio con
`systemctl restart nexora@<entorno>`. Prueba primero en staging.

Actualizar las direcciones de Cloudflare que acepta nginx: `deploy/setup-vps.sh cloudflare-ips`.

## Montarlo desde cero

Como root, desde una copia de esta carpeta en el VPS:

```sh
./setup-vps.sh base                  # MariaDB, usuarios, systemd, sudoers, bases y .env
./setup-vps.sh deploy-key "<clave>"  # clave pública ssh-ed25519 del CI
# certificado de origen en /etc/ssl/cloudflare/nexoralang.org.{pem,key}
./setup-vps.sh nginx                 # sitio de nginx; crea la contraseña de staging si no hay
./setup-vps.sh staging-password      # cambia la contraseña de staging
```

En GitHub: environments `staging` (secreto `STAGING_BASIC_AUTH` = `nexora:<contraseña>`) y
`production` (con revisión obligatoria); secretos del repositorio `DEPLOY_SSH_KEY` y
`DEPLOY_KNOWN_HOSTS`; variable `DEPLOY_HOST` con la IP del VPS.

## Lo que no está en producción

- El playground está apagado (`PLAYGROUND_ENABLED=false`) hasta validar el aislamiento con Docker
  real (`nexora/docs/playground.md`).
- Google, GitHub y reCAPTCHA están sin claves: los botones avisan de que no están disponibles y los
  formularios usan el límite estricto.
- Las páginas legales siguen siendo borradores pendientes de revisión.
