#!/usr/bin/env bash
# leaderbot's deploy. Runs on the Advergo VPS as root, for every deploy (called by
# .github/workflows/deploy.yml). It follows advergo-frontend's ops/deploy.sh; only the pre-deploy
# backup (SQLite instead of Postgres) differs.
#
#   bash deploy.sh <project dir> <new docker-compose.yml> <image tag> <health-check URL>
#
# The project folder (/docker/<project>) belongs to Hostinger's Docker Manager: the panel owns its
# .env (the Environment box). This script only replaces docker-compose.yml, so settings edited in
# the panel survive every deploy. Compose takes the project name from the folder name, which is
# also the name the panel shows, so the containers and volumes stay the same from deploy to deploy.
set -euo pipefail

DIR="$1"
NEW_COMPOSE="$2"
TAG="$3"
HEALTH_URL="$4"
PROJECT="$(basename "$DIR")"

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

if [ ! -f "$DIR/.env" ]; then
  echo "No $DIR/.env: the project's settings must be in place before the first deploy" \
    "(README, Deployment)." >&2
  exit 1
fi
cd "$DIR"

# Back up the SQLite database before touching anything, if the app is running. Found by Compose's
# labels rather than through a compose file, so it also works on the first deploy into a new
# folder. The image has no sqlite3 CLI, so its Python makes the copy with SQLite's backup API,
# which gives a consistent snapshot even while the app writes. Exit 3 means the app has not
# created leads.db yet (it does so on the first run); any other failure stops the deploy.
web="$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "label=com.docker.compose.service=web" --filter status=running)"
if [ -n "$web" ]; then
  mkdir -p backups/prod
  file="backups/prod/leaderbot-predeploy-$(date -u +%Y-%m-%dT%H-%M-%SZ).db"
  rc=0
  docker exec "$web" python -c '
import os, sqlite3, sys, tempfile
db = "/app/data/leads.db"
if not os.path.exists(db):
    sys.exit(3)
fd, tmp = tempfile.mkstemp(suffix=".db")
os.close(fd)
try:
    src = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()
    with open(tmp, "rb") as f:
        sys.stdout.buffer.write(f.read())
finally:
    os.unlink(tmp)
' > "$file.partial" || rc=$?
  if [ "$rc" -eq 3 ]; then
    rm -f "$file.partial"
    log "no leads.db in the running app yet; nothing to back up"
  elif [ "$rc" -ne 0 ]; then
    echo "database backup failed (exit $rc); not deploying" >&2
    exit 1
  elif [ "$(head -c 15 "$file.partial")" != "SQLite format 3" ]; then
    echo "database backup is not an SQLite file; not deploying" >&2
    exit 1
  else
    mv "$file.partial" "$file"
    log "database backed up to $DIR/$file ($(du -h "$file" | cut -f1))"
  fi
fi

# Keep the compose file being replaced, for reference or a manual rollback.
mkdir -p backups
[ -f docker-compose.yml ] && cp docker-compose.yml backups/docker-compose.previous.yml
install -m 644 "$NEW_COMPOSE" docker-compose.yml
rm -f "$NEW_COMPOSE"

if [ -z "${DEPLOY_SKIP_PULL:-}" ]; then # set only by local tests
  log "pulling images ($TAG)"
  docker compose pull --quiet
fi
log "starting"
docker compose up -d --remove-orphans --wait --wait-timeout 300

# Every container built from our own image must now run the tag this deploy was for.
for c in $(docker compose ps -q); do
  image="$(docker inspect --format '{{.Config.Image}}' "$c")"
  case "$image" in
    itzwasik/*)
      if [ "${image##*:}" != "$TAG" ]; then
        echo "$(docker inspect --format '{{.Name}}' "$c") runs $image, expected tag $TAG" >&2
        exit 1
      fi
      ;;
  esac
done

for i in $(seq 1 30); do
  if curl -fs -o /dev/null "$HEALTH_URL"; then
    log "healthy: $HEALTH_URL"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "$HEALTH_URL did not answer after the deploy" >&2
    docker compose logs --tail 80 >&2 || true
    exit 1
  fi
  sleep 4
done

docker image prune -f > /dev/null
docker compose ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'
