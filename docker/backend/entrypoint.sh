#!/bin/bash

# =============================================================================
# ENTRYPOINT UNIFICADO - EVAonline
# =============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
MAX_RETRIES=${MAX_RETRIES:-30}
RETRY_INTERVAL=${RETRY_INTERVAL:-2}
SERVICE=${SERVICE:-api}
ENVIRONMENT=${ENVIRONMENT:-development}
LOG_LEVEL=${LOG_LEVEL:-info}

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

# Função de logging com timestamp e emoji
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Função para aguardar serviço com timeout
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    local attempt=1

    log "🕐 Aguardando $service_name em $host:$port (máximo: ${MAX_RETRIES} tentativas)..."

    while [ $attempt -le $MAX_RETRIES ]; do
        if nc -z -w 5 "$host" "$port" 2>/dev/null; then
            log "✅ $service_name está disponível!"
            return 0
        fi

        log "⏳ Tentativa $attempt/$MAX_RETRIES: $service_name ainda não está disponível..."
        sleep $RETRY_INTERVAL
        ((attempt++))
    done

    log "❌ ERRO: $service_name não ficou disponível após $MAX_RETRIES tentativas"
    return 1
}

# Função SEGURA para verificar saúde do banco (CORRIGIDA)
check_database_health() {
    log "🔍 Verificando saúde do banco de dados..."

    # Usar sub-shell para evitar kill do processo principal
    if (python -c "
import sys
try:
    from backend.database.connection import get_db
    from sqlalchemy import text
    db = next(get_db())
    db.execute(text('SELECT 1'))
    print('✅ Conexão com banco estabelecida e saudável')
    sys.exit(0)
except Exception as e:
    print(f'❌ Erro na conexão com banco: {e}')
    sys.exit(1)
" > /dev/null 2>&1); then
        return 0
    else
        return 1
    fi
}

# Função alternativa mais simples para verificar banco
check_database_connection() {
    log "🔍 Verificando conexão com banco de dados..."
    python3 << 'EOF'
import sys
import os
sys.path.insert(0, '/app')

try:
    # Tentar importar módulos do banco
    from backend.database.connection import get_db_context
    print("✅ Módulos de banco importados com sucesso!")
except ImportError as e:
    print(f"⚠️ Aviso ao importar módulos: {e}")
    # Não falhar - tentar continuar
except Exception as e:
    print(f"❌ Erro crítico nos módulos: {e}")
    sys.exit(1)
EOF
}

# Função para executar migrações com fallback
run_migrations() {
    log "🔄 Verificando migrações do banco de dados..."

    if command -v alembic >/dev/null 2>&1 && [ -f "alembic.ini" ]; then
        log "📦 Alembic detectado, verificando migrações..."
        if alembic current >/dev/null 2>&1; then
            log "📦 Aplicando migrações pendentes..."
            if alembic upgrade head; then
                log "✅ Migrações aplicadas com sucesso"
            else
                log "⚠️ Aviso: Falha ao aplicar migrações com Alembic"
                create_tables_directly
            fi
        else
            log "ℹ️ Nenhuma migração Alembic detectada, criando tabelas diretamente..."
            create_tables_directly
        fi
    else
        log "ℹ️ Alembic não disponível, criando tabelas diretamente..."
        create_tables_directly
    fi
}

# Função para criar tabelas diretamente (fallback)
create_tables_directly() {
    log "🏗️ Criando tabelas diretamente..."
    python -c "
try:
    from backend.database.connection import engine
    from backend.database.models import Base
    Base.metadata.create_all(bind=engine)
    print('✅ Tabelas criadas/verificadas com sucesso')
except Exception as e:
    print(f'⚠️ Aviso ao criar tabelas: {e}')
    # Não falhar - a aplicação pode tentar recriar depois
"
}

# Função para configurar ambiente
setup_environment() {
    log "⚙️ Configurando ambiente..."

    # Timezone
    export TZ=${TZ:-America/Sao_Paulo}

    # Python path
    export PYTHONPATH=/app:$PYTHONPATH

    # Criar diretórios necessários
    mkdir -p /app/logs /app/data /app/temp

    # Configurar nível de log baseado no ambiente
    if [ "$ENVIRONMENT" = "production" ]; then
        export LOG_LEVEL="info"
        export RELOAD=""
        export WORKERS="4"
    else
        export LOG_LEVEL="debug"
        export RELOAD="--reload"
        export WORKERS="1"
    fi

    log "✅ Ambiente configurado (TZ: $TZ, ENV: $ENVIRONMENT, LOG: $LOG_LEVEL)"
}

# =============================================================================
# HANDLERS DE SERVIÇOS
# =============================================================================

start_api() {
    local service_name="$1"
    log "🚀 Iniciando serviço $service_name..."

    wait_for_service "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"
    wait_for_service "${REDIS_HOST:-redis}" "6379" "Redis"

    if ! check_database_health; then
        log "❌ Banco de dados não está saudável, tentando verificação alternativa..."
        check_database_connection
    fi

    run_migrations

    if [ "$ENVIRONMENT" = "production" ]; then
        log "🌐 Iniciando API FastAPI com Gunicorn (Produção)..."
        exec gunicorn backend.main:app \
            --bind 0.0.0.0:8000 \
            --workers "$WORKERS" \
            --worker-class uvicorn.workers.UvicornWorker \
            --timeout 120 \
            --keep-alive 5 \
            --max-requests 1000 \
            --max-requests-jitter 100 \
            --access-logfile - \
            --error-logfile - \
            --log-level "$LOG_LEVEL"
    else
        log "🌐 Iniciando API FastAPI com Uvicorn (Desenvolvimento)..."
        exec uvicorn backend.main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --workers "$WORKERS" \
            $RELOAD \
            --reload-dir /app/backend \
            --log-level "$LOG_LEVEL"
    fi
}

start_worker() {
    log "🔧 Iniciando Celery Worker..."
    wait_for_service "${REDIS_HOST:-redis}" "6379" "Redis"
    wait_for_service "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"

    check_database_connection

    exec celery -A backend.infrastructure.celery.celery_config:celery_app worker \
        --loglevel="$LOG_LEVEL" \
        --concurrency="${CELERY_WORKER_CONCURRENCY:-4}" \
        --prefetch-multiplier="${CELERY_WORKER_PREFETCH_MULTIPLIER:-4}" \
        --max-tasks-per-child=100
}

start_worker_eto() {
    log "🔧 Iniciando Celery Worker ETo (CPU-intensive)..."
    wait_for_service "${REDIS_HOST:-redis}" "6379" "Redis"
    wait_for_service "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"

    check_database_connection

    # Worker especializado para cálculos ETo
    exec celery -A backend.infrastructure.celery.celery_config:celery_app worker \
        --loglevel="$LOG_LEVEL" \
        --queues=eto \
        --concurrency="${CELERY_CONCURRENCY:-2}" \
        --prefetch-multiplier="${CELERY_PREFETCH_MULTIPLIER:-1}" \
        --max-tasks-per-child=50 \
        --pool=prefork
}

start_flower() {
    log "📊 Iniciando Flower Monitor..."
    wait_for_service "${REDIS_HOST:-redis}" "6379" "Redis"

    exec celery -A backend.infrastructure.celery.celery_config:celery_app flower \
        --address=0.0.0.0 \
        --port=5555 \
        --basic_auth="${FLOWER_USER:-admin}:${FLOWER_PASSWORD:-admin}" \
        --url_prefix=flower
}

start_migrate() {
    log "🗃️ Executando apenas migrações..."
    wait_for_service "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"

    if check_database_health; then
        run_migrations
        log "✅ Migrações concluídas!"
    else
        log "❌ Não foi possível conectar ao banco para migrações"
        exit 1
    fi
}

start_all_services() {
    log "🎯 Iniciando todos os serviços em modo desenvolvimento..."

    # Aguardar dependências
    wait_for_service "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"
    wait_for_service "${REDIS_HOST:-redis}" "6379" "Redis"

    check_database_connection
    run_migrations

    # Array para armazenar PIDs
    declare -a PIDS=()

    # Iniciar FastAPI em background
    log "🌐 Iniciando FastAPI..."
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload --log-level debug &
    PIDS+=($!)

    # Aguardar API iniciar
    sleep 10

    # Iniciar worker Celery em background
    log "🔧 Iniciando Celery Worker..."
    celery -A backend.infrastructure.celery.celery_config:celery_app worker --loglevel=debug --concurrency=2 --pool=solo &
    PIDS+=($!)

    sleep 5

    # Iniciar Celery Beat em background
    log "⏰ Iniciando Celery Beat..."
    celery -A backend.infrastructure.celery.celery_config:celery_app beat --loglevel=debug &
    PIDS+=($!)

    sleep 5

    # Iniciar Flower em background
    log "📊 Iniciando Flower..."
    celery -A backend.infrastructure.celery.celery_config:celery_app flower --address=0.0.0.0 --port=5555 &
    PIDS+=($!)

    # Função para cleanup
    cleanup() {
        log "🛑 Parando todos os serviços..."
        for pid in "${PIDS[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
        wait
        log "✅ Todos os serviços parados"
        exit 0
    }

    # Registrar trap para cleanup
    trap cleanup SIGTERM SIGINT

    log "✅ Todos os serviços iniciados!"
    log "📝 Logs disponíveis em /app/logs/"
    log "🛑 Use Ctrl+C para parar todos os serviços"

    # Aguardar indefinidamente
    wait
}

# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

main() {
    log "🚀 Iniciando EVAonline Backend"
    log "📋 Serviço: $SERVICE, Ambiente: $ENVIRONMENT, Log Level: $LOG_LEVEL"

    # Configurar ambiente
    setup_environment

    # Executar serviço específico
    case "$SERVICE" in
        "api")
            start_api "API"
            ;;
        "worker")
            start_worker
            ;;
        "worker-eto")
            start_worker_eto
            ;;
        "beat")
            start_beat
            ;;
        "flower")
            start_flower
            ;;
        "migrate")
            start_migrate
            ;;
        "all")
            start_all_services
            ;;
        *)
            log "❌ Erro: Serviço '$SERVICE' não reconhecido."
            log "📚 Serviços disponíveis: api, worker, worker-eto, beat, flower, migrate, all"
            exit 1
            ;;
    esac
}

# =============================================================================
# HANDLERS DE SINAL PARA SHUTDOWN GRACEFUL
# =============================================================================

graceful_shutdown() {
    log "🛑 Recebido sinal de desligamento graceful..."
    exit 0
}

# Registrar handlers de sinal
trap graceful_shutdown SIGTERM SIGINT

# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

# Executar apenas se for o processo principal
if [ $$ -eq 1 ]; then
    main "$@"
else
    # Se for um subprocesso, executar diretamente
    "$@"
fi
