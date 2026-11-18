# AIOps Orientado a Eventos com AWS Emulator e Agentes de IA

Implementação prática de uma arquitetura de **Triagem e Autocorreção de Incidentes (AIOps)** utilizando **AWS Emulator** (S3, SQS, DLQ, DynamoDB) e um **Worker Agêntico** em Python.

---

## 1. Desenho da Arquitetura

```text
  [1. Observabilidade / App]
    (Alarme CloudWatch / Log de Erro Crítico)
               │
               ▼ (PutObject: incidente.json)
       ┌───────────────┐
       │   Amazon S3   │  (Bucket: logs-incidentes)
       └───────┬───────┘
               │ (S3 Event Notification: s3:ObjectCreated:*)
               ▼
       ┌───────────────┐       (Falha após 3 tentativas)      ┌───────────────────┐
       │  Amazon SQS   │ ───────────────────────────────────► │  Amazon SQS (DLQ) │
       └───────┬───────┘                                      └───────────────────┘
               │ (Long Polling)
               ▼
┌─────────────────────────────────────────────────────────────┐
│                  WORKER AGÊNTICO (worker_aiops.py)          │
│                                                             │
│  1. Guardrail de Idempotência (Checa hash no DynamoDB)      │
│  2. Orquestrador do Agente (LLM + Structured Output JSON)   │
│                                                             │
│     ┌─────────────── FERRAMENTAS (TOOLS) ───────────────┐   │
│     │ • ler_log_s3()         -> Extrai log do S3        │   │
│     │ • buscar_runbook()     -> Consulta base técnica   │   │
│     │ • consultar_deploys()  -> Verifica último commit  │   │
│     └───────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼ (PutItem: Estado)            ▼ (Roteamento por Risco)
       ┌───────────────┐              ┌───────────────────────┐
       │   DynamoDB    │              │   Amazon SQS (HITL)   │
       │(incidentes-   │              │(fila-aprovacao-humana)│
       │    aiops)     │              └───────────────────────┘
       └───────────────┘
```

---

## 2. Estrutura do Projeto

- `Dockerfile`: Imagem local do AWS Emulator.
- `setup-infra.sh`: Provisiona buckets S3, filas SQS (principal, HITL e DLQ) e tabela DynamoDB.
- `tools_aiops.py`: Ferramentas (*Tools*) que o agente usa para ler logs, consultar runbooks e verificar deploys.
- `agente_aiops.py`: Cérebro do agente com contrato Pydantic (`DiagnosticoIncidente`). Funciona com **Gemini API** (`GEMINI_API_KEY`) ou em **modo simulado offline** automático.
- `worker_aiops.py`: Consumidor SQS com deduplicação por hash, roteamento de risco e tratamento de falhas.
- `simular_cenarios.sh`: Dispara os 4 cenários de teste automaticamente.

---

## 3. Como Executar Localmente

### Passo 1: Iniciar o AWS Emulator (Terminal 1)
```bash
sudo docker build -t aws-emulator .
mkdir -p ~/.aws/emulator

PORT=9297
sudo docker run --rm --memory=2g --memory-swap=2g \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:$PORT:$PORT \
  -e HOME="$HOME" \
  -v "$HOME/.aws/emulator:$HOME/.aws/emulator" \
  aws-emulator -p $PORT
```

### Passo 2: Provisionar Infraestrutura e Ambiente Python (Terminal 2)
```bash
export AWS_CONFIG_FILE=~/.aws/emulator/9297/config
export AWS_SHARED_CREDENTIALS_FILE=~/.aws/emulator/9297/emulator_credentials

chmod +x setup-infra.sh simular_cenarios.sh
./setup-infra.sh

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Passo 3: Iniciar o Worker AIOps (Terminal 2)
* **Modo Offline (Gratuito / Sem chave de API):**
  ```bash
  python3 worker_aiops.py
  ```
* **Modo IA Real (com Google Gemini):**
  ```bash
  export GEMINI_API_KEY="sua-chave-aqui"
  python3 worker_aiops.py
  ```

---

## 4. Validando os 4 Cenários (Terminal 3)

Abra um terceiro terminal e dispare todos os cenários de uma vez:

```bash
./simular_cenarios.sh
```

### O que verificar em cada cenário:
1. **Cenário 1 (Auto-Heal):** O log `incidente-redis-01.json` consulta o `RB-001` e recebe status `REMEDIADO_AUTOMATICAMENTE`.
2. **Cenário 2 (Tempestade de Alertas / Idempotência):** Os 5 alertas idênticos (`tempestade-redis-01..05.json`) não chamam o agente novamente; o contador `ocorrencias` no DynamoDB sobe para `6`.
3. **Cenário 3 (Human-in-the-Loop):** O erro `DataCorruptionException` é correlacionado com o deploy `v2.4.1` e enviado para a `fila-aprovacao-humana` com status `AGUARDANDO_APROVACAO`.
4. **Cenário 4 (DLQ):** O arquivo `incidente-corrompido-01.json` falha no parser JSON e, após 3 tentativas, é isolado na `fila-incidentes-dlq`.

### Comandos de Inspeção:
```bash
export AWS_CONFIG_FILE=~/.aws/emulator/9297/config
export AWS_SHARED_CREDENTIALS_FILE=~/.aws/emulator/9297/emulator_credentials

# Ver incidentes e contagem de deduplicacao no DynamoDB
aws dynamodb scan --table-name incidentes-aiops

# Listar relatorios post-mortem gerados no S3
aws s3 ls s3://relatorios-postmortem/

# Verificar mensagens aguardando aprovacao humana (HITL)
HITL_URL=$(aws sqs get-queue-url --queue-name fila-aprovacao-humana --query 'QueueUrl' --output text)
aws sqs receive-message --queue-url "$HITL_URL"
```
