#!/usr/bin/env bash
set -e

PORT=${1:-9297}
export AWS_CONFIG_FILE="$HOME/.aws/emulator/$PORT/config"
export AWS_SHARED_CREDENTIALS_FILE="$HOME/.aws/emulator/$PORT/emulator_credentials"

mkdir -p exemplos_logs

echo "=== Gerando payloads de teste para os 4 cenarios AIOps ==="

# Cenario 1: Erro conhecido de baixo risco (Auto-Heal)
cat << 'EOF' > exemplos_logs/cenario1_redis_timeout.json
{
  "service": "cache-gateway",
  "environment": "production",
  "error_type": "ConnectionPoolExhausted",
  "message": "TimeoutError: Redis connection pool exhausted after 500ms",
  "stack_trace_top": "at RedisPool.acquire (pool.py:142)"
}
EOF

# Cenario 3: Erro critico apos deploy (Human-in-the-Loop)
cat << 'EOF' > exemplos_logs/cenario3_corrupcao_dados.json
{
  "service": "orders-service",
  "environment": "production",
  "error_type": "DataCorruptionException",
  "message": "Checksum mismatch on table orders for batch #9941",
  "stack_trace_top": "at OrderSerializer.verify (serializer.py:88)"
}
EOF

# Cenario 4: Payload malformado (Para testar DLQ)
echo "{ json_invalido_sem_fechamento " > exemplos_logs/cenario4_malformado.json

echo "[1] Disparando Cenario 1 (Auto-Heal)..."
aws s3 cp exemplos_logs/cenario1_redis_timeout.json s3://logs-incidentes/incidente-redis-01.json

sleep 2
echo "[2] Disparando Cenario 2 (Tempestade de 5 alertas identicos - Deduplicacao)..."
for i in {1..5}; do
  aws s3 cp exemplos_logs/cenario1_redis_timeout.json "s3://logs-incidentes/tempestade-redis-0${i}.json"
done

sleep 2
echo "[3] Disparando Cenario 3 (Alto Risco / Human-in-the-Loop)..."
aws s3 cp exemplos_logs/cenario3_corrupcao_dados.json s3://logs-incidentes/incidente-orders-01.json

sleep 2
echo "[4] Disparando Cenario 4 (Payload Corrompido -> DLQ apos 3 falhas)..."
aws s3 cp exemplos_logs/cenario4_malformado.json s3://logs-incidentes/incidente-corrompido-01.json

echo ""
echo "=== Todos os cenarios foram enviados para s3://logs-incidentes/ ==="
echo "Acompanhe os logs no terminal do worker_aiops.py!"
