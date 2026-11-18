#!/usr/bin/env bash
set -e

PORT=${1:-9297}
export AWS_CONFIG_FILE="$HOME/.aws/emulator/$PORT/config"
export AWS_SHARED_CREDENTIALS_FILE="$HOME/.aws/emulator/$PORT/emulator_credentials"

echo "=== Provisionando infraestrutura no AWS Emulator (Porta $PORT) ==="

# 1. Criar Buckets S3
echo "[1/4] Criando buckets S3..."
aws s3 mb s3://uploads-entrada 2>/dev/null || true
aws s3 mb s3://resultados-saida 2>/dev/null || true

# 2. Criar Tabela DynamoDB
echo "[2/4] Criando tabela DynamoDB (jobs-status)..."
aws dynamodb create-table \
  --table-name jobs-status \
  --attribute-definitions AttributeName=arquivo_id,AttributeType=S \
  --key-schema AttributeName=arquivo_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST >/dev/null 2>&1 || true

# 3. Criar Fila SQS + DLQ
echo "[3/4] Criando filas SQS e DLQ..."
DLQ_URL=$(aws sqs create-queue --queue-name fila-dlq --query 'QueueUrl' --output text)
DLQ_ARN=$(aws sqs get-queue-attributes --queue-url "$DLQ_URL" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

QUEUE_URL=$(aws sqs create-queue \
  --queue-name fila-processamento \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
  --query 'QueueUrl' --output text)

QUEUE_ARN=$(aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

# 4. Configurar evento S3 -> SQS
echo "[4/4] Conectando evento S3 (ObjectCreated) ao SQS..."
aws sqs set-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attributes "{\"Policy\":\"{\\\"Version\\\":\\\"2012-10-17\\\",\\\"Statement\\\":[{\\\"Effect\\\":\\\"Allow\\\",\\\"Principal\\\":{\\\"Service\\\":\\\"s3.amazonaws.com\\\"},\\\"Action\\\":\\\"SQS:SendMessage\\\",\\\"Resource\\\":\\\"$QUEUE_ARN\\\"}]}\"}"

aws s3api put-bucket-notification-configuration \
  --bucket uploads-entrada \
  --notification-configuration "{\"QueueConfigurations\":[{\"QueueArn\":\"$QUEUE_ARN\",\"Events\":[\"s3:ObjectCreated:*\"]}]}"

echo ""
echo "=== Infraestrutura concluída! ==="
echo "Fila Principal: $QUEUE_URL"
echo "Fila DLQ:       $DLQ_URL"