# Aula Prática: Arquitetura Orientada a Eventos na Nuvem

Imagine uma **cozinha de restaurante movimentada**. Se o garçom precisasse ficar parado na frente do fogão esperando cada prato ficar pronto antes de anotar o próximo pedido, o restaurante pararia na primeira fila. Em vez disso, ele coloca a comanda num trilho, volta para atender as mesas e os cozinheiros preparam os pedidos no ritmo deles.

Na computação em nuvem, chamamos isso de **Arquitetura Orientada a Eventos (EDA - Event-Driven Architecture)**. Vamos conhecer cada "integrante" da nossa cozinha distribuída e entender por que ele existe.

---

## 1. O Balcão de Entrega: Amazon S3 (`uploads-entrada`)
* **O que é:** Um serviço de armazenamento de objetos altamente escalável.
* **Papel na arquitetura:** É a nossa **porta de entrada**. O cliente não precisa saber como ou quando o arquivo será processado; ele apenas deposita o arquivo no bucket.
* **O pulo do gato (S3 Event Notification):** Assim que o arquivo aterrissa no bucket, o próprio S3 avisa automaticamente ao sistema: *"Ei, chegou um arquivo novo chamado `relatorio.txt`!"*. Esse aviso é o nosso **Evento**.

## 2. O Trilho de Comandas: Amazon SQS (`fila-processamento`)
* **O que é:** Um serviço de filas de mensagens (*Simple Queue Service*).
* **Papel na arquitetura:** É o **amortecedor (buffer)** que garante o **desacoplamento**.
* **Por que não ligar o S3 direto no Worker?**
  * **Picos de tráfego:** Se chegarem 500 arquivos em um segundo, a fila segura todos eles com segurança sem derrubar o servidor de processamento.
  * **Tolerância a falhas:** Se o nosso Worker precisar reiniciar ou cair por alguns minutos, as mensagens continuam guardadas na fila esperando ele voltar. Nenhuma informação se perde.

## 3. A Caixa de Problemas: Dead Letter Queue (`fila-dlq`)
* **O que é:** Uma fila especial configurada para receber mensagens que falharam repetidamente.
* **Papel na arquitetura:** É o **isolamento de falhas**.
* **Como funciona na prática:** Às vezes chega um arquivo corrompido (como no nosso Cenário 3). Se o Worker tentar processá-lo infinitamente, vai gastar processamento à toa e atrasar os arquivos saudáveis. Com a DLQ (`maxReceiveCount: 3`), após 3 tentativas sem sucesso, a mensagem "envenenada" (*poison pill*) é movida para uma fila separada para investigação humana, deixando o fluxo principal livre.

## 4. O Cozinheiro: Worker (`worker.py`)
* **O que é:** Nossa aplicação consumidora que roda de forma contínua em segundo plano.
* **Papel na arquitetura:** É quem executa a **regra de negócio**.
* **Conceitos-chave que aplicamos nele:**
  * **Long Polling (`WaitTimeSeconds=10`):** Em vez de perguntar à fila a cada milissegundo *"Tem mensagem? Tem mensagem?"* (o que gera custo e tráfego inútil), o Worker abre uma conexão e aguarda pacientemente até 10 segundos por uma novidade.
  * **Confirmação Explícita (`delete_message`):** A mensagem só é apagada da fila **depois** que todo o trabalho termina com sucesso. Se o Worker cair no meio do caminho, a mensagem volta a ficar visível na fila para outro Worker assumir.

## 5. O Quadro de Acompanhamento: Amazon DynamoDB (`jobs-status`)
* **O que é:** Um banco de dados NoSQL de chave-valor extremamente rápido.
* **Papel na arquitetura:** É a **memória de estado (rastreabilidade)** do sistema.
* **Por que precisamos dele?** Como o processamento é assíncrono (acontece em segundo plano), o usuário ou outro sistema precisa saber se o arquivo ainda está na fila (`PROCESSANDO`), se já acabou (`CONCLUIDO`) ou se deu problema (`ERRO`). Consultar uma tabela indexada por `arquivo_id` no DynamoDB leva apenas alguns milissegundos.

## 6. A Estante de Pratos Prontos: Amazon S3 (`resultados-saida`)
* **O que é:** Um segundo bucket S3 separado do bucket de entrada.
* **Papel na arquitetura:** É o **destino final** do artefato gerado.
* **Boa prática essencial:** Nunca grave o arquivo processado no mesmo bucket de entrada onde há um gatilho `s3:ObjectCreated:*`. Se fizer isso, o novo arquivo vai disparar um novo evento, criando um **loop infinito** que pode gerar custos enormes na nuvem real!

---

## Resumo em 30 Segundos

| Componente | Analogia | Garantia Arquitetural |
| :--- | :--- | :--- |
| **S3 (Entrada)** | Balcão de pedidos | Disparador automático de eventos |
| **SQS (Principal)** | Trilho de comandas | Desacoplamento e absorção de picos |
| **SQS (DLQ)** | Mesa de revisão | Resiliência contra arquivos defeituosos |
| **Worker** | Cozinheiro | Processamento escalável e idempotente |
| **DynamoDB** | Painel de status | Visibilidade em tempo real do ciclo de vida |
| **S3 (Saída)** | Balcão de entrega | Persistência isolada sem risco de loops |