import json
import boto3

s3 = boto3.client("s3")

# Base simulada de Runbooks operacionais da empresa
RUNBOOKS_DB = {
    "ConnectionPoolExhausted": {
        "titulo": "RB-001: Esgotamento de Pool de Conexoes Redis/DB",
        "severidade": "MEDIA",
        "auto_heal_permitido": True,
        "procedimento": "Executar flush de conexoes ociosas no Redis e reiniciar workers ociosos. Baixo risco, seguro para execucao automatica.",
        "comando_remediacao": "redis-cli CLIENT KILL TYPE normal && systemctl restart worker-pool"
    },
    "DataCorruptionException": {
        "titulo": "RB-002: Inconsistencia de Checksum em Tabela Critica",
        "severidade": "CRITICA",
        "auto_heal_permitido": False,
        "procedimento": "NUNCA executar correcao automatica em dados financeiros/pedidos. Isolar servico, verificar ultimo deploy e solicitar rollback manual pelo engenheiro de plantao.",
        "comando_remediacao": "kubectl rollout undo deployment/orders-service"
    }
}

# Historico simulado de deploys recentes
DEPLOYS_RECENTES = [
    {
        "versao": "v2.4.1",
        "servico": "orders-service",
        "autor": "dev.backend@empresa.com",
        "timestamp": "2026-11-17T22:15:00Z",
        "alteracao": "Otimizacao na serializacao de checksum do payload de pedidos"
    },
    {
        "versao": "v1.18.0",
        "servico": "cache-gateway",
        "autor": "sre@empresa.com",
        "timestamp": "2026-11-15T10:00:00Z",
        "alteracao": "Ajuste de timeout de leitura do Redis para 500ms"
    }
]


def ler_log_s3(bucket: str, chave: str) -> str:
    """Le o conteudo bruto de um arquivo de log de incidente no bucket S3."""
    obj = s3.get_object(Bucket=bucket, Key=chave)
    return obj["Body"].read().decode("utf-8")


def buscar_runbook(palavra_chave_erro: str) -> str:
    """Busca runbooks operacionais conhecidos com base no tipo de excecao ou servico."""
    resultados = []
    for chave, rb in RUNBOOKS_DB.items():
        if palavra_chave_erro.lower() in chave.lower() or palavra_chave_erro.lower() in rb["titulo"].lower():
            resultados.append(rb)
    if not resultados:
        return json.dumps({"mensagem": "Nenhum runbook especifico encontrado. Escalar para revisao humana."}, ensure_ascii=False)
    return json.dumps(resultados, ensure_ascii=False, indent=2)


def consultar_deploys(servico: str) -> str:
    """Consulta os ultimos deploys realizados para um determinado microsservico."""
    filtrados = [d for d in DEPLOYS_RECENTES if servico.lower() in d["servico"].lower()]
    if not filtrados:
        return json.dumps(DEPLOYS_RECENTES, ensure_ascii=False, indent=2)
    return json.dumps(filtrados, ensure_ascii=False, indent=2)
