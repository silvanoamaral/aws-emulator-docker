import hashlib
import json
import os
from datetime import datetime, timezone
import boto3

from tools_aiops import ler_log_s3
from agente_aiops import analisar_incidente_com_agente

# Configura credenciais locais do AWS Emulator caso nao estejam exportadas
port = os.getenv("EMULATOR_PORT", "9297")
home = os.path.expanduser("~")
os.environ.setdefault("AWS_CONFIG_FILE", f"{home}/.aws/emulator/{port}/config")
os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", f"{home}/.aws/emulator/{port}/emulator_credentials")

s3 = boto3.client("s3")
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = sqs.get_queue_url(QueueName="fila-incidentes")["QueueUrl"]
HITL_QUEUE_URL = sqs.get_queue_url(QueueName="fila-aprovacao-humana")["QueueUrl"]
tabela_incidentes = dynamodb.Table("incidentes-aiops")


def gerar_assinatura_erro(payload: dict) -> str:
    """Gera um hash deterministico para deduplicar tempestades de alertas identicos."""
    chave = f"{payload.get('service', '')}:{payload.get('error_type', '')}:{payload.get('stack_trace_top', '')}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()[:16]


print(f"[*] Worker AIOps iniciado. Escutando fila: {QUEUE_URL}")
print(f"[*] Modo LLM: {'Gemini API Ativo' if os.getenv('GEMINI_API_KEY') else 'Simulador Local (defina GEMINI_API_KEY para usar IA real)'}")

while True:
    resposta = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10
    )

    for msg in resposta.get("Messages", []):
        receipt_handle = msg["ReceiptHandle"]
        corpo = json.loads(msg["Body"])

        if corpo.get("Event") == "s3:TestEvent":
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
            continue

        try:
            for registro in corpo.get("Records", []):
                bucket_origem = registro["s3"]["bucket"]["name"]
                chave_arquivo = registro["s3"]["object"]["key"]

                print(f"\n[->] Alerta recebido: s3://{bucket_origem}/{chave_arquivo}")

                # 1. Le e valida o JSON do log (se estiver corrompido, lanca excecao -> DLQ)
                conteudo_bruto = ler_log_s3(bucket_origem, chave_arquivo)
                payload_log = json.loads(conteudo_bruto)

                # 2. Guardrail de Idempotencia / Deduplicacao
                assinatura = gerar_assinatura_erro(payload_log)
                existente = tabela_incidentes.get_item(Key={"assinatura_erro": assinatura}).get("Item")

                if existente and existente.get("status") in ("REMEDIADO_AUTOMATICAMENTE", "AGUARDANDO_APROVACAO"):
                    nova_contagem = int(existente.get("ocorrencias", 1)) + 1
                    tabela_incidentes.update_item(
                        Key={"assinatura_erro": assinatura},
                        UpdateExpression="SET ocorrencias = :c, ultimo_evento = :u",
                        ExpressionAttributeValues={
                            ":c": nova_contagem,
                            ":u": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    print(f"[DEDUP] Alerta duplicado (assinatura={assinatura}). Ocorrencias atualizadas para {nova_contagem}. LLM economizado!")
                    continue

                # 3. Aciona o Agente Investigador
                print(f"[IA] Investigando incidente (assinatura={assinatura})...")
                diagnostico = analisar_incidente_com_agente(payload_log)

                # 4. Roteamento baseado em Risco e Confianca (Portao HITL)
                if diagnostico.acao_recomendada == "AUTO_HEAL" and diagnostico.confianca >= 0.90:
                    status_final = "REMEDIADO_AUTOMATICAMENTE"
                    print(f"[AUTO-HEAL] Confianca {diagnostico.confianca:.2f} | Executando: {diagnostico.comando_ou_patch}")
                else:
                    status_final = "AGUARDANDO_APROVACAO"
                    print(f"[HITL] Acao '{diagnostico.acao_recomendada}' (confianca {diagnostico.confianca:.2f}) enviada para fila humana.")
                    sqs.send_message(
                        QueueUrl=HITL_QUEUE_URL,
                        MessageBody=json.dumps({
                            "assinatura_erro": assinatura,
                            "arquivo_origem": chave_arquivo,
                            "diagnostico": diagnostico.model_dump()
                        }, ensure_ascii=False)
                    )

                # 5. Salva Dossie Post-Mortem no S3
                chave_relatorio = f"postmortem-{assinatura}-{chave_arquivo}"
                dossie = {
                    "assinatura_erro": assinatura,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": status_final,
                    "diagnostico": diagnostico.model_dump(),
                    "log_original": payload_log
                }
                s3.put_object(
                    Bucket="relatorios-postmortem",
                    Key=chave_relatorio,
                    Body=json.dumps(dossie, ensure_ascii=False, indent=2).encode("utf-8")
                )

                # 6. Persiste estado no DynamoDB
                tabela_incidentes.put_item(Item={
                    "assinatura_erro": assinatura,
                    "servico": diagnostico.servico_afetado,
                    "status": status_final,
                    "acao_recomendada": diagnostico.acao_recomendada,
                    "confianca": str(diagnostico.confianca),
                    "comando_sugerido": diagnostico.comando_ou_patch,
                    "relatorio_s3": f"s3://relatorios-postmortem/{chave_relatorio}",
                    "ocorrencias": 1,
                    "ultimo_evento": datetime.now(timezone.utc).isoformat()
                })

                print(f"[OK] Incidente registrado ({status_final}) -> s3://relatorios-postmortem/{chave_relatorio}")

            # 7. Confirma consumo na fila principal
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)

        except Exception as erro:
            print(f"[ERRO] Falha ao processar alerta: {erro}")
            print("[!] Mensagem mantida na fila para retentativa / isolamento na DLQ.")
