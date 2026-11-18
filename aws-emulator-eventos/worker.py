import json
import os
from datetime import datetime, timezone
import boto3

# Garante o carregamento das credenciais do emulador caso não estejam no ambiente
port = os.getenv("EMULATOR_PORT", "9297")
home = os.path.expanduser("~")
os.environ.setdefault("AWS_CONFIG_FILE", f"{home}/.aws/emulator/{port}/config")
os.environ.setdefault("AWS_SHARED_CREDENTIALS_FILE", f"{home}/.aws/emulator/{port}/emulator_credentials")

s3 = boto3.client("s3")
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = sqs.get_queue_url(QueueName="fila-processamento")["QueueUrl"]
tabela_jobs = dynamodb.Table("jobs-status")

print(f"[*] Worker iniciado. Escutando fila: {QUEUE_URL}")

while True:
    resposta = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10
    )

    for msg in resposta.get("Messages", []):
        receipt_handle = msg["ReceiptHandle"]
        corpo = json.loads(msg["Body"])

        # Ignora evento de verificação inicial do S3
        if corpo.get("Event") == "s3:TestEvent":
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
            continue

        try:
            for registro in corpo.get("Records", []):
                bucket_origem = registro["s3"]["bucket"]["name"]
                chave_arquivo = registro["s3"]["object"]["key"]

                print(f"[->] Novo evento recebido: s3://{bucket_origem}/{chave_arquivo}")

                # 1. Marca como PROCESSANDO no DynamoDB
                tabela_jobs.put_item(Item={
                    "arquivo_id": chave_arquivo,
                    "status": "PROCESSANDO",
                    "atualizado_em": datetime.now(timezone.utc).isoformat()
                })

                # 2. Baixa arquivo original do S3
                obj = s3.get_object(Bucket=bucket_origem, Key=chave_arquivo)
                conteudo = obj["Body"].read().decode("utf-8")

                # 3. Processamento simulado
                resultado = (
                    f"PROCESSADO EM: {datetime.now(timezone.utc).isoformat()}\n"
                    f"TOTAL DE CARACTERES: {len(conteudo)}\n"
                    f"{'-' * 40}\n"
                    f"{conteudo.upper()}"
                )

                # 4. Grava artefato processado no bucket de saída
                chave_saida = f"processado-{chave_arquivo}"
                s3.put_object(
                    Bucket="resultados-saida",
                    Key=chave_saida,
                    Body=resultado.encode("utf-8")
                )

                # 5. Marca como CONCLUIDO no DynamoDB
                tabela_jobs.put_item(Item={
                    "arquivo_id": chave_arquivo,
                    "status": "CONCLUIDO",
                    "arquivo_saida": f"s3://resultados-saida/{chave_saida}",
                    "atualizado_em": datetime.now(timezone.utc).isoformat()
                })

                print(f"[OK] Concluído: s3://resultados-saida/{chave_saida}")

            # 6. Confirma consumo da mensagem na fila apenas se tudo deu certo
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)

        except Exception as erro:
            print(f"[ERRO] Falha ao processar mensagem: {erro}")
            print("[!] Mensagem mantida na fila para retentativa/DLQ.")
            # Registra a falha no DynamoDB se soubermos qual era o arquivo
            if "chave_arquivo" in locals():
                tabela_jobs.put_item(Item={
                    "arquivo_id": chave_arquivo,
                    "status": "ERRO",
                    "detalhe_erro": str(erro),
                    "atualizado_em": datetime.now(timezone.utc).isoformat()
                })