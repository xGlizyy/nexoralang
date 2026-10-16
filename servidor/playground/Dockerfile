# Imagen del worker del playground: Python y el intérprete de NEXORA, nada más.
#
# ESTADO: preparada, no probada. En el equipo donde se desarrolló el playground no había Docker.
# Antes de usarla en un servidor público, constrúyela y verifica los pasos de
# nexora/docs/playground.md ("Comprobar el aislamiento").
#
# Se construye desde la raíz del repositorio:
#
#     docker build -f servidor/playground/Dockerfile -t nexora-worker .
#
# El servidor web la usa para CADA petición con una orden como esta (variable
# PLAYGROUND_WORKER_COMMAND de servidor/.env), que es la que impone el aislamiento:
#
#     docker run --rm -i --init --name {container} --network none --read-only --cap-drop ALL
#       --security-opt no-new-privileges --pids-limit 32 --memory 256m --memory-swap 256m
#       --cpus 0.5 --user 65534:65534 --tmpfs /tmp:rw,size=1m,noexec nexora-worker

FROM python:3.12-slim

# Solo el paquete del intérprete: sin pruebas, sin documentación, sin herramientas de desarrollo.
COPY nexora/pyproject.toml nexora/README.md /src/
COPY nexora/src /src/src
RUN pip install --no-cache-dir /src && rm -rf /src

# Sin privilegios. La orden `docker run` lo repite con --user por si la imagen se usa de otro modo.
USER 65534:65534
WORKDIR /tmp

# -I: modo aislado de Python. El worker lee una petición JSON por la entrada estándar,
# escribe una respuesta JSON por la salida estándar y termina.
ENTRYPOINT ["python", "-I", "-m", "nexora.worker"]
