# Instalação e manutenção

## Produção

1. Confirme o domínio, servidor, capacidade, espaço persistente, SMTP, destino externo de cópias e responsáveis. Instale Docker Engine e Docker Compose num ambiente compatível.
2. Copie `.env.example` para `.env`, restrinja as permissões a `0600` e preencha os campos. Use um segredo Django de pelo menos 50 caracteres. Preencha senhas distintas para o utilizador da aplicação e para o administrador inicial de PostgreSQL. Os contentores da aplicação recebem apenas a senha da aplicação. Configure DNS e encaminhe as portas TCP 80 e 443 para o proxy. As listas de hosts contêm nomes, sem esquema.
3. Execute `docker compose config --quiet` e `docker compose build`. Obtenha as assinaturas com `docker compose run --rm signatures --stdout`. Inicie com `docker compose up -d db migrate web dispatcher processor proxy`. O serviço `migrate` termina após aplicar as migrações. O servidor Web e o despachante aguardam pela sua conclusão.
4. Crie a primeira conta individual por convite, depois de validada a designação. Substitua os campos seguintes pelos dados da instalação. Entregue a ligação apenas pelo canal confirmado do destinatário. O convite expira em 24 horas e permite ao destinatário escolher a palavra-passe. Acrescente `--reemitir` apenas para substituir um convite ainda pendente.
5. Em homologação, valide HTTPS, o envio de correio, as assinaturas, a conversão real de um DOCX, as permissões, a leitura parcial de PDF e o restauro. Execute `docker compose exec web python manage.py check --deploy`.

```sh
docker compose exec web python manage.py invite_staff NOME bibliotecario \
  --url-base https://DOMINIO_CONFIRMADO \
  --responsavel 'Nome de quem aprovou' \
  --referencia 'Referência da designação' \
  --email-validado ENDERECO_VALIDADO
```

A configuração aplica HSTS ao domínio da biblioteca. Os avisos W005 e W021 referem-se à extensão aos subdomínios e à adesão à lista de pré-carregamento dos navegadores. Confirme as implicações para o domínio com o seu responsável antes de activar essas opções.

O endereço validado é opcional e permite recuperação da palavra-passe depois de configurado o correio. Use o painel em `/gestao/` e registe o acervo e as listas de estudantes autorizadas. Para contas já criadas, use `set_role CONTA bibliotecario --actor RESPONSAVEL --reason 'Referência da decisão'`. Estão disponíveis as funções `bibliotecario`, `tecnico` e `correccao`. A atribuição fica registada na auditoria, e o acesso de quem administra o servidor aos volumes, ao PostgreSQL e aos segredos decorre das permissões da infra-estrutura.

O Compose aceita SMTP ou Resend. Para SMTP, configure `EMAIL_HOST`, a autenticação quando exigida e `DEFAULT_FROM_EMAIL`. Para Resend, configure `EMAIL_BACKEND=rovuma.resend_backend.ResendEmailBackend`, `RESEND_API_KEY` e um remetente verificado em `DEFAULT_FROM_EMAIL`. Apenas o serviço Web recebe as variáveis de correio.


O Caddy permite até 6 MB por pedido. O JavaScript envia partes de 1 MiB e a aplicação valida tamanho e posição no servidor. O limite total é configurado em `UPLOAD_MAX_BYTES` e deve respeitar a capacidade dos volumes, o motor antivírus e o espaço temporário. O predefinido é 1 GiB. Um original em análise ocupa espaço no acervo privado e na fila. A conversão Word requer ainda área temporária e espaço para o PDF. Dimensione o servidor pela maior carga simultânea esperada. O worker tem rede desactivada, raiz só de leitura, limite de memória, CPU e processos, e volumes restritos. O serviço de despacho mantém a fila em PostgreSQL. O motor de análise recusa documentos quando o antivírus falha ou o formato é inválido.

A separação de ambientes usa bases, volumes, segredos e domínios distintos. Em homologação, adopte dados fictícios ou devidamente anonimizados. Agende `docker compose exec -T web python manage.py clean_uploads` diariamente. Depois de 72 horas a transferência incompleta deve começar de novo. Monitorize espaço livre, falhas de análise, tamanho da fila e actualização das assinaturas. Evite que o proxy, a observabilidade ou o SMTP registrem caminhos com tokens. Restrinja acesso aos logs administrativos.

## Correio por HTTPS no Railway

No serviço web do ambiente de homologação, defina `EMAIL_BACKEND=rovuma.resend_backend.ResendEmailBackend`, guarde a chave de envio em `RESEND_API_KEY` e use em `DEFAULT_FROM_EMAIL` um remetente do domínio verificado no Resend. Desactive o rastreio de cliques no domínio de envio para preservar a ligação de recuperação. Com uma conta local de ensaio e um endereço validado, peça a recuperação pelo formulário, confirme a chegada da mensagem e use a ligação HTTPS para definir uma nova senha. Confirme que a nova senha permite iniciar sessão e que a ligação usada deixa de funcionar.

## Tarefas agendadas

Configure o agendador do servidor para executar diariamente, a partir da pasta do projecto, `docker compose exec -T web python manage.py clean_uploads` e `bash ops/backup.sh`. Programe a cópia para um período de baixa utilização, pois o procedimento suspende temporariamente os escritores. Encaminhe a saída para o registo operacional. Configure `BACKUP_ALERT_COMMAND` com o caminho de um executável de alerta, quando existir um canal aprovado, e configure a renovação de assinaturas do ClamAV.

O proxy Caddy fornece o endereço observado da ligação através de `X-Rovuma-Client`, substituindo o cabeçalho recebido. Active `TRUST_ROVUMA_PROXY=1` apenas se o serviço Web for acessível exclusivamente por um proxy que sobrescreva esse cabeçalho. Noutras instalações, a aplicação utiliza o endereço da ligação apresentado pelo servidor de aplicação. Verifique o comportamento de limitação quando os utilizadores partilham um proxy ou uma rede.

O carregamento aceita PDF e DOCX. O limite do documento é configurável e o envio usa partes de 1 MiB; o proxy aceita pedidos até 6 MB. A conversão de DOCX está sujeita aos limites de expansão do ZIP, de espaço temporário, de memória e de duração do processador. Documentos Word antigos em formato DOC e documentos com macros devem ser convertidos para DOCX sem macros antes do carregamento.

Serviços de proxy ou de observabilidade geridos pelo alojamento podem registar o caminho das ligações de activação e recuperação independentemente do Django. O operador deve configurar a omissão desses caminhos e restringir o acesso aos registos do alojamento antes de utilizar dados reais.

## Cópias e restauro

O script `ops/backup.sh` usa Restic para deduplicar e encriptar os dados num repositório externo. Configure `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE` e permissões de escrita restritas. Inicialize com `restic init` uma vez. Programe a execução diária fora das horas de maior utilização, por exemplo com cron. Registe a saída e, se houver, configure `BACKUP_ALERT_COMMAND` como o caminho para um programa que notifique falhas. A retenção usa `KEEP_DAILY`, `KEEP_WEEKLY` e `KEEP_MONTHLY`. O script interrompe temporariamente os escritores da aplicação para obter uma cópia coerente e relança-os antes de fazer a transferência.

Restaure primeiro num ambiente isolado e noutra configuração Compose, com volumes vazios. Identifique o snapshot através de `restic snapshots --tag biblioteca-rovuma` e extraia com `restic restore ID --target ./restore`. O alvo deve conter `rovuma.dump` e `private/`, conforme indicado por `restic ls ID`. Mantenha o processo Web e o despachante parados durante a operação.

```sh
docker compose up -d --wait db
docker compose exec -T db sh -ec 'pg_restore --clean --if-exists --exit-on-error --no-owner -U "$ROVUMA_DB_USER" -d "$POSTGRES_DB"' < restore/rovuma.dump
tar -C restore/private -cf - . | docker compose run --rm --no-deps -T web tar -C /data/private -xf -
docker compose run --rm --no-deps web python manage.py migrate --noinput
docker compose run --rm --no-deps web python manage.py requeue_restored_documents
docker compose up -d web dispatcher processor proxy
```

O utilizador dos contentores tem UID 10001 e necessita de espaço e direitos de escrita nos volumes. Use cópias de ficheiros de configuração e segredos guardadas por um canal separado e restrito. Verifique contas, ligações, inventário, progresso, hash e leitura de PDFs, e simule novo carregamento. Exercite o procedimento periodicamente e antes de alterações de infra-estrutura.

## Actualização e reversão

Crie uma cópia adicional. Guarde a revisão do código e as etiquetas anteriores de imagens. Teste a nova revisão num ambiente separado. Defina um novo `APP_TAG`, construa as imagens, pare `web` e `dispatcher`, aplique as migrações, suba os serviços e verifique os fluxos. Preserve os volumes nomeados. Se for preciso reverter uma migração incompatível, pare os escritores, restaure o par base/acervo da cópia anterior e só depois reponha as imagens e a configuração correspondentes.
