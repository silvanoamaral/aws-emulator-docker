# Ambiente Local: AWS Emulator com Docker

Este guia documenta a configuração, execução e validação do **AWS Emulator** rodando localmente em um contêiner Docker.

---

## O que é o AWS Emulator?

O **AWS Emulator** é uma ferramenta oficial da Amazon Web Services que simula APIs e serviços da AWS diretamente na sua máquina local. Ele permite desenvolver, testar e validar aplicações, scripts de infraestrutura e integrações com SDKs sem precisar de conexão com a nuvem real e sem gerar custos na sua conta AWS.

### Características principais:
* **Execução em Memória (RAM):** Todos os recursos criados (buckets S3, tabelas DynamoDB, filas SQS, etc.) ficam armazenados exclusivamente na memória RAM enquanto o contêiner estiver ativo. Ao encerrar o processo (`Ctrl+C`), o ambiente é limpo automaticamente.
* **Autenticação Local Realista:** Diferente de simuladores que aceitam qualquer chave genérica, o AWS Emulator gera certificados TLS (`ca.pem`) e credenciais temporárias exclusivas a cada inicialização, exigindo que as requisições sejam devidamente assinadas.
* **Isolamento de Rede:** Configurado para responder exclusivamente em `127.0.0.1`, garantindo que os serviços simulados não fiquem expostos na sua rede local.

---

## Pré-requisitos

* **Docker** instalado e em execução.
* **AWS CLI v2** instalado na máquina host para interação e validação via terminal.
* Pelo menos **2 GiB de memória RAM** disponíveis para o contêiner.

---

## 1. Construindo a Imagem Docker

Como a AWS não disponibiliza uma imagem pré-compilada no Docker Hub, a imagem é construída localmente a partir do `Dockerfile` do projeto (baseado em `amazonlinux:2023-minimal`).

No diretório onde está o `Dockerfile`, execute:

```bash
sudo docker build -t aws-emulator .
```

> **Nota para ambientes Live CD / Sistemas sobre `overlayfs` (ex: Linux Mint Live):**  
> Caso ocorra erro de montagem (`err: invalid argument` no driver `overlay`), configure o daemon do Docker para usar o driver `vfs` antes do build:
> ```bash
> sudo mkdir -p /etc/docker
> echo '{"storage-driver": "vfs"}' | sudo tee /etc/docker/daemon.json
> sudo systemctl restart docker
> ```

---

## 2. Executando o Emulador Localmente

Antes de iniciar o contêiner, crie o diretório compartilhado no seu usuário para evitar que o Docker o crie com permissões de `root`.

### Iniciar o servidor (Porta padrão `9297`)

```bash
mkdir -p ~/.aws/emulator

PORT=9297
sudo docker run --rm --memory=2g --memory-swap=2g \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:$PORT:$PORT \
  -e HOME="$HOME" \
  -v "$HOME/.aws/emulator:$HOME/.aws/emulator" \
  aws-emulator -p $PORT
```

### Entendendo os parâmetros utilizados:
* `--rm`: Remove automaticamente o contêiner quando ele for interrompido.
* `--memory=2g --memory-swap=2g`: Limita o uso máximo de RAM em 2 GiB (sem swap) para evitar travamentos no sistema host.
* `--user "$(id -u):$(id -g)"` e `-e HOME="$HOME"`: Garante que os arquivos de configuração e certificados sejam gravados com as permissões do seu usuário local.
* `-p 127.0.0.1:$PORT:$PORT`: Mapeia a porta apenas para o endereço de loopback local (`localhost`), bloqueando acessos externos.
* `-v "$HOME/.aws/emulator:$HOME/.aws/emulator"`: Compartilha a pasta onde o emulador gera as credenciais e o certificado raiz (`ca.pem`).

> **Dica:** Mantenha este terminal aberto. Para encerrar o emulador e apagar os recursos em memória, pressione `Ctrl+C`.

---

## 3. Configurando o AWS CLI e Validando

Abra um **segundo terminal** para interagir com o emulador.

### Passo 1: Apontar as variáveis de ambiente para os arquivos gerados
Ao iniciar, o emulador cria uma subpasta correspondente à porta (`~/.aws/emulator/9297/`) contendo os arquivos `config`, `emulator_credentials` e `ca.pem`. Aponte o AWS CLI para eles:

```bash
export AWS_CONFIG_FILE=~/.aws/emulator/9297/config
export AWS_SHARED_CREDENTIALS_FILE=~/.aws/emulator/9297/emulator_credentials
```

Para confirmar que o AWS CLI reconheceu as credenciais do emulador:

```bash
aws configure list
```

### Passo 2: Testar a criação e listagem de um Bucket S3
Execute os comandos abaixo para validar a comunicação TLS, a assinatura das credenciais e a resposta da API:

```bash
# Criar um bucket de teste
aws s3 mb s3://meu-bucket-teste

# Listar buckets existentes no emulador
aws s3 ls
```

**Saída esperada:**
```text
make_bucket: meu-bucket-teste
2026-11-17 23:38:00 meu-bucket-teste
```

---

## 4. Rodando Múltiplas Instâncias (Opcional)

Caso precise de ambientes isolados simultaneamente, abra novos terminais e altere a variável `PORT` (ex: `9298`, `9299`). O emulador criará diretórios separados dentro de `~/.aws/emulator/` para cada porta:

```bash
PORT=9298
sudo docker run --rm --memory=2g --memory-swap=2g \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:$PORT:$PORT \
  -e HOME="$HOME" \
  -v "$HOME/.aws/emulator:$HOME/.aws/emulator" \
  aws-emulator -p $PORT
```

Para conectar o CLI à segunda instância, basta apontar as variáveis para a pasta `9298`:
```bash
export AWS_CONFIG_FILE=~/.aws/emulator/9298/config
export AWS_SHARED_CREDENTIALS_FILE=~/.aws/emulator/9298/emulator_credentials
```

---

## Referências

* [Documentação Oficial: AWS Emulator User Guide](https://docs.aws.amazon.com/emulator/latest/userguide/what-is-emulator.html)
* [Guia Oficial: Getting Started with Docker (AWS Emulator)](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html)
* [Instalação Oficial do AWS CLI v2 no Linux](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
* [Documentação Docker: Storage Drivers (overlay2 e vfs)](https://docs.docker.com/storage/storagedriver/select-storage-driver/)