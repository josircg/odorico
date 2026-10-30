#!/usr/bin/env bash
#
# deploy.sh — Deploy local do Odorico (Opção B)
#
# Executa, em ordem, os passos de atualização da aplicação no próprio servidor:
#   1. git pull do projeto
#   2. git pull do tema (se o diretório existir)
#   3. migrate
#   4. collectstatic --noinput
#   5. restart do serviço via supervisor (desacoplado, para não derrubar
#      o worker que respondeu ao request que disparou o deploy)
#
# Aborta no primeiro erro (set -euo pipefail) e propaga o código de saída.
#
# Parametrização por variáveis de ambiente (com defaults):
#   PROJECT_DIR         raiz do projeto            (default: diretório do script)
#   VENV_DIR            raiz do virtualenv          (default: /var/webapp/odorico310)
#   SUPERVISOR_SERVICE  nome do serviço supervisor  (default: odorico)
#   SKIP_RESTART        se "1", não reinicia o serviço (usar em DEBUG/dev)
#
set -euo pipefail

# Diretório onde este script reside = raiz do projeto por padrão
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
VENV_DIR="${VENV_DIR:-/var/webapp/odorico310}"
SUPERVISOR_SERVICE="${SUPERVISOR_SERVICE:-odorico}"
SKIP_RESTART="${SKIP_RESTART:-0}"

PYTHON="$VENV_DIR/bin/python"

echo "== Deploy iniciado em $(date '+%Y-%m-%d %H:%M:%S') =="
echo "PROJECT_DIR=$PROJECT_DIR"
echo "VENV_DIR=$VENV_DIR"
echo "SUPERVISOR_SERVICE=$SUPERVISOR_SERVICE"

cd "$PROJECT_DIR"

echo "== [1/5] git pull (projeto) =="
git pull

if [ -d "$PROJECT_DIR/tema/.git" ] || [ -d "$PROJECT_DIR/tema" ]; then
    echo "== [2/5] git pull (tema) =="
    git -C "$PROJECT_DIR/tema" pull
else
    echo "== [2/5] tema/ ausente — pulando =="
fi

echo "== [3/5] migrate =="
"$PYTHON" manage.py migrate --noinput

echo "== [4/5] collectstatic =="
"$PYTHON" manage.py collectstatic --noinput

if [ "$SKIP_RESTART" = "1" ]; then
    echo "== [5/5] restart pulado (SKIP_RESTART=1) =="
else
    echo "== [5/5] agendando restart assíncrono de '$SUPERVISOR_SERVICE' =="
    # Dispara o restart em uma sessão desacoplada do processo atual, com um
    # pequeno atraso para que a resposta HTTP do deploy consiga ser enviada
    # antes de os workers serem reiniciados.
    setsid bash -c "sleep 2 && supervisorctl restart '$SUPERVISOR_SERVICE'" \
        >/dev/null 2>&1 < /dev/null &
    echo "restart agendado"
fi

echo "== Deploy concluído com sucesso =="
