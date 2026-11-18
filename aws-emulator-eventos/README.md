# Arquitetura Orientada a Eventos com AWS Emulator

Este projeto implementa e valida um pipeline assíncrono de processamento de arquivos rodando 100% localmente utilizando o **AWS Emulator** em Docker.

## 1. O que é o AWS Emulator?
O **AWS Emulator** é um simulador local oficial da AWS que emula APIs, protocolos de rede, políticas IAM e comportamento de serviços (como S3, SQS e DynamoDB) diretamente em memória RAM, permitindo desenvolver e testar arquiteturas distribuídas sem custos de nuvem ou conexão com a internet.

---

## 2. Desenho da Arquitetura

### Fluxo Visual (Mermaid)
```mermaid
flowchart LR
    Client([Cliente / Upload]) -->|1. PutObject| S3In[(Amazon S3\nuploads-entrada)]
    S3In -->|2. Evento ObjectCreated| SQS[[Amazon SQS\nfila-processamento]]
    SQS -.->|Após 3 falhas| DLQ[[Amazon SQS\nfila-dlq]]
    SQS -->|3. Long Polling| Worker[Worker Python\nworker.py]
    Worker -->|4. GetObject| S3In
    Worker -->|5. PutObject| S3Out[(Amazon S3\nresultados-saida)]
    Worker -->|6. PutItem / Status| DDB[(DynamoDB\njobs-status)]


