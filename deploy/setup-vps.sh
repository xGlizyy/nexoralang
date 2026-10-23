#!/bin/bash
# Prepara el VPS para NEXORA. Se ejecuta como root desde una copia de la carpeta deploy/.
# Se puede repetir: no regenera contraseñas ni archivos de entorno que ya existan.
#
#   ./setup-vps.sh base                 Paquetes, usuarios, carpetas, systemd, sudoers, MariaDB, copias.
#   ./setup-vps.sh deploy-key "<clave>" Autoriza la clave pública del CI (solo puede usar nexora-deploy).
#   ./setup-vps.sh nginx                Sitio de nginx (exige el certificado de origen ya instalado).
#   ./setup-vps.sh staging-password     Cambia la contraseña de staging (la deja en /root, no la muestra).
#   ./setup-vps.sh cloudflare-ips       Vuelve a descargar las direcciones de Cloudflare y recarga nginx.
#
# No toca nada que no sea de NEXORA: los demás sitios, servicios y bases siguen como estaban.

set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ENVS=(staging production)

port_of() { [ "$1" = staging ] && echo 3101 || echo 3100; }
url_of() { [ "$1" = staging ] && echo https://staging.nexoralang.org || echo https://nexoralang.org; }

base() {
  [ -x /opt/node24/bin/node ] || { echo "falta /opt/node24/bin/node" >&2; exit 1; }
  DEBIAN_FRONTEND=noninteractive apt-get install -y mariadb-server
  systemctl enable --now mariadb

  id nexora > /dev/null 2>&1 || useradd --system --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin nexora
  id nexora-deploy > /dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/nexora-deploy --shell /bin/sh nexora-deploy

  install -d -o root -g root -m 755 /opt/nexora /opt/nexora/bin
  install -d -o nexora-deploy -g nexora-deploy -m 755 /opt/nexora/releases /opt/nexora/staging /opt/nexora/production
  install -o root -g root -m 755 "$HERE/bin/nexora-deploy" "$HERE/bin/nexora-backup" /opt/nexora/bin/

  install -o root -g root -m 644 "$HERE"/systemd/* /etc/systemd/system/
  install -o root -g root -m 440 "$HERE/sudoers/nexora-deploy" /etc/sudoers.d/nexora-deploy
  visudo -cf /etc/sudoers.d/nexora-deploy

  install -d -o root -g nexora -m 750 /etc/nexora
  for env in "${ENVS[@]}"; do
    local file=/etc/nexora/$env.env
    [ -f "$file" ] && continue
    local password
    password=$(openssl rand -hex 24)
    mariadb <<SQL
CREATE DATABASE IF NOT EXISTS nexora_$env CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'nexora_$env'@'127.0.0.1' IDENTIFIED BY '$password';
ALTER USER 'nexora_$env'@'127.0.0.1' IDENTIFIED BY '$password';
GRANT ALL PRIVILEGES ON nexora_$env.* TO 'nexora_$env'@'127.0.0.1';
SQL
    umask 027
    cat > "$file" <<ENV
# Generado por deploy/setup-vps.sh. Variables explicadas en servidor/.env.example.
NODE_ENV=production
PORT=$(port_of "$env")
LISTEN_HOST=127.0.0.1
TRUST_PROXY=loopback
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=nexora_$env
DB_PASSWORD=$password
DB_NAME=nexora_$env
PUBLIC_URL=$(url_of "$env")
PLAYGROUND_ENABLED=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
RECAPTCHA_SECRET_KEY=
RECAPTCHA_HOSTNAMES=
ENV
    umask 022
    chown root:nexora "$file"
    chmod 640 "$file"
  done

  systemctl daemon-reload
  for env in "${ENVS[@]}"; do systemctl enable "nexora@$env.service"; done
  systemctl enable --now nexora-backup.timer
}

deploy_key() {
  local key=${1:?falta la clave pública}
  [[ "$key" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]] || { echo "se esperaba una clave ssh-ed25519" >&2; exit 1; }
  local dir=/var/lib/nexora-deploy/.ssh
  install -d -o nexora-deploy -g nexora-deploy -m 700 "$dir"
  echo "restrict,command=\"/opt/nexora/bin/nexora-deploy\" $key" > "$dir/authorized_keys"
  chown nexora-deploy:nexora-deploy "$dir/authorized_keys"
  chmod 600 "$dir/authorized_keys"
}

cloudflare_ips() {
  local tmp
  tmp=$(mktemp -d)
  curl -fsS https://www.cloudflare.com/ips-v4 > "$tmp/v4"
  curl -fsS https://www.cloudflare.com/ips-v6 > "$tmp/v6"
  # Una lista corta o vacía dejaría el sitio sin servicio (o abierto): se exige un mínimo razonable.
  [ "$({ cat "$tmp/v4"; echo; cat "$tmp/v6"; echo; } | grep -c /)" -ge 10 ] || { echo "lista de Cloudflare sospechosa" >&2; exit 1; }
  install -d -m 755 /etc/nginx/nexora
  { echo "# Generado por setup-vps.sh cloudflare-ips el $(date -u +%F)."; { cat "$tmp/v4"; echo; cat "$tmp/v6"; echo; } | grep / | sed 's/$/ 1;/'; } > /etc/nginx/nexora/cloudflare-geo.conf
  { echo "# Generado por setup-vps.sh cloudflare-ips el $(date -u +%F)."; { cat "$tmp/v4"; echo; cat "$tmp/v6"; echo; } | grep / | sed 's/^/set_real_ip_from /; s/$/;/'; } > /etc/nginx/nexora/cloudflare-realip.conf
  rm -rf "$tmp"
}

# Contraseña de staging (usuario nexora): nueva cada vez. No se muestra: queda solo en
# /root/nexora-staging-password (600), para copiarla al gestor de contraseñas y al secreto
# STAGING_BASIC_AUTH. nginx lee el archivo en cada petición: no hace falta recargarlo.
staging_password() {
  local password
  password=$(openssl rand -base64 24 | tr -d '/+=')
  install -d -m 755 /etc/nginx/nexora
  printf 'nexora:%s\n' "$(openssl passwd -apr1 "$password")" > /etc/nginx/nexora/staging.htpasswd.new
  chown root:www-data /etc/nginx/nexora/staging.htpasswd.new
  chmod 640 /etc/nginx/nexora/staging.htpasswd.new
  mv /etc/nginx/nexora/staging.htpasswd.new /etc/nginx/nexora/staging.htpasswd
  (umask 077; printf 'nexora:%s\n' "$password" > /root/nexora-staging-password)
  echo "contraseña de staging nueva en /root/nexora-staging-password"
}

nginx_site() {
  [ -f /etc/ssl/cloudflare/nexoralang.org.pem ] && [ -f /etc/ssl/cloudflare/nexoralang.org.key ] \
    || { echo "falta el certificado de origen en /etc/ssl/cloudflare/nexoralang.org.{pem,key}" >&2; exit 1; }
  cloudflare_ips
  [ -f /etc/nginx/nexora/staging.htpasswd ] || staging_password
  install -m 644 "$HERE/nginx/nexora-cloudflare.conf" /etc/nginx/conf.d/
  install -m 644 "$HERE/nginx/nexora-edge.conf" "$HERE/nginx/nexora-proxy.conf" /etc/nginx/snippets/
  install -m 644 "$HERE/nginx/nexoralang.org.conf" /etc/nginx/sites-available/nexoralang.org
  ln -sfn /etc/nginx/sites-available/nexoralang.org /etc/nginx/sites-enabled/nexoralang.org
  # Si la configuración no es válida se retira entera: los otros sitios no pueden quedar con un nginx
  # que no recarga.
  if ! nginx -t; then
    rm -f /etc/nginx/sites-enabled/nexoralang.org /etc/nginx/conf.d/nexora-cloudflare.conf
    echo "configuración de nginx no válida: retirada" >&2
    exit 1
  fi
  systemctl reload nginx
}

case "${1:-}" in
  base) base ;;
  deploy-key) deploy_key "${2:-}" ;;
  nginx) nginx_site ;;
  staging-password) staging_password ;;
  cloudflare-ips) cloudflare_ips; nginx -t; systemctl reload nginx ;;
  *) echo "uso: $0 base | deploy-key <clave> | nginx | staging-password | cloudflare-ips" >&2; exit 1 ;;
esac
