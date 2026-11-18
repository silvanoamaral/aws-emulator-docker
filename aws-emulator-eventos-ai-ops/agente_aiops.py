import json
import os
from typing import Literal
from pydantic import BaseModel, Field

from tools_aiops import buscar_runbook, consultar_deploys


class DiagnosticoIncidente(BaseModel):
    causa_raiz: str = Field(description="Explicacao tecnica objetiva da causa raiz do incidente.")
    servico_afetado: str = Field(description="Nome do microsservico ou componente afetado.")
    confianca: float = Field(ge=0.0, le=1.0, description="Nivel de confianca no diagnostico entre 0.0 e 1.0.")
    acao_recomendada: Literal["AUTO_HEAL", "ROLLBACK_SUGERIDO", "ESCALAR_HUMANO"] = Field(
        description="Classificacao da acao com base no risco e no runbook."
    )
    comando_ou_patch: str = Field(description="Comando exato de remediacao ou rollback sugerido.")
    justificativa_risco: str = Field(description="Por que esta acao pode ser automatica ou exige aprovacao humana.")


def analisar_incidente_com_agente(payload_log: dict) -> DiagnosticoIncidente:
    """
    Executa a investigacao do incidente usando Gemini (se GEMINI_API_KEY estiver configurada)
    com Tool Calling e Structured Output, ou utiliza o motor heuristico local de fallback
    para validacao offline 100% gratuita.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""
        Voce e um Engenheiro SRE / Arquiteto AIOps Senior.
        Analise o log de incidente abaixo. Use obrigatoriamente as ferramentas `buscar_runbook` e `consultar_deploys`
        para verificar procedimentos autorizados e mudancas recentes antes de concluir o diagnostico.

        Regras de seguranca:
        - Use `AUTO_HEAL` APENAS se o runbook autorizar explicitamente (`auto_heal_permitido: true`) e o risco for baixo.
        - Use `ROLLBACK_SUGERIDO` ou `ESCALAR_HUMANO` se houver risco de perda de dados, mudanca recente de deploy suspeita ou ausencia de runbook.

        Log do Incidente:
        {json.dumps(payload_log, ensure_ascii=False, indent=2)}
        """

        # Passo 1: Agente investiga usando ferramentas (Tool Calling)
        investigacao = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[buscar_runbook, consultar_deploys],
                temperature=0.1,
            ),
        )

        # Passo 2: Consolida o diagnostico em JSON estrito (Structured Output via Pydantic)
        estruturado = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"Com base nesta investigacao tecnica, gere o objeto estruturado final:\n\n"
                f"Investigacao:\n{investigacao.text}\n\n"
                f"Log original:\n{json.dumps(payload_log, ensure_ascii=False)}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DiagnosticoIncidente,
                temperature=0.0,
            ),
        )
        return DiagnosticoIncidente.model_validate_json(estruturado.text)

    # --- MODO SIMULADO OFFLINE (Quando GEMINI_API_KEY nao esta definida) ---
    print("   [Agente] GEMINI_API_KEY nao detectada. Executando motor local com consulta as tools...")
    erro_tipo = payload_log.get("error_type", "")
    servico = payload_log.get("service", "desconhecido")

    rb_info = json.loads(buscar_runbook(erro_tipo))
    deploys_info = json.loads(consultar_deploys(servico))

    if "ConnectionPoolExhausted" in erro_tipo:
        rb = rb_info[0]
        return DiagnosticoIncidente(
            causa_raiz=f"Esgotamento do pool de conexoes no servico {servico}: {payload_log.get('message')}",
            servico_afetado=servico,
            confianca=0.95,
            acao_recomendada="AUTO_HEAL",
            comando_ou_patch=rb["comando_remediacao"],
            justificativa_risco=f"Autorizado pelo {rb['titulo']} ({rb['procedimento']})"
        )

    if "DataCorruptionException" in erro_tipo:
        deploy_suspeito = deploys_info[0]["versao"] if deploys_info else "desconhecido"
        return DiagnosticoIncidente(
            causa_raiz=f"Falha de checksum em {servico} correlacionada com o deploy recente {deploy_suspeito}.",
            servico_afetado=servico,
            confianca=0.82,
            acao_recomendada="ROLLBACK_SUGERIDO",
            comando_ou_patch=f"kubectl rollout undo deployment/{servico}",
            justificativa_risco="Alto risco de integridade de dados. Exige aprovacao humana (HITL) antes do rollback."
        )

    return DiagnosticoIncidente(
        causa_raiz=f"Erro nao catalogado em {servico}: {payload_log.get('message', 'Sem detalhes')}",
        servico_afetado=servico,
        confianca=0.50,
        acao_recomendada="ESCALAR_HUMANO",
        comando_ou_patch="N/A - Investigacao manual necessaria",
        justificativa_risco="Baixa confianca e ausencia de runbook automatizado."
    )
