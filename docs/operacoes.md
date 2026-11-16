# Instalação e manutenção

## Produção

1. Confirme o domínio, servidor, capacidade, espaço persistente, SMTP, destino externo de cópias e responsáveis. Instale Docker Engine e Docker Compose num ambiente compatível.
2. Copie `.env.example` para `.env`, restrinja as permissões a `0600` e preencha os campos. Use um segredo Django de pelo menos 50 caracteres. Preencha senhas distintas para o utilizador da aplicação e para o administrador inicial de PostgreSQL. Os contentores da aplicação recebem apenas a senha da aplicação. Configure DNS e encaminhe as portas TCP 80 e 443 para o proxy. As listas de hosts contêm nomes, sem esquema.
3. Execute `docker compose config --quiet` e `docker compose build`. Obtenha as assinaturas com `docker compose run --rm signatures --stdout`. Execute `docker compose run --rm --no-deps processor python -m ops.verify_processor` para verificar a análise e a conversão de um DOCX gerado na hora. Inicie com `docker compose up -d db migrate web dispatcher processor proxy`. O serviço `migrate` termina após aplicar as migrações. O servidor Web e o despachante aguardam pela sua conclusão.
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

O endereço validado é opcional e permite recuperação da palavra-passe depois de configurado o correio. O convite inicial pode ser emitido antes de configurar o correio. Entregue-o directamente ao destinatário por um canal reservado, confirme que o utilizador consegue iniciar sessão e evite guardar a ligação em tickets, repositórios ou registos partilhados. Use o painel em `/admin/` e registe o acervo e as listas de estudantes autorizadas. Para contas já criadas, use `set_role CONTA bibliotecario --actor RESPONSAVEL --reason 'Referência da decisão'`. Estão disponíveis as funções `bibliotecario`, `tecnico` e `correccao`. A atribuição fica registada na auditoria, e o acesso de quem administra o servidor aos volumes, ao PostgreSQL e aos segredos decorre das permissões da infra-estrutura.

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

## Processamento no alojamento actual

O Railway mantém a aplicação Web, o PostgreSQL e o acervo privado. O processo Web só deve iniciar o despachante depois de verificar o serviço de análise. O limite de 1 GB observado no Railway impede o carregamento das assinaturas oficiais neste serviço. Para usar o mesmo alojamento depois de disponibilizar memória suficiente, teste o serviço `biblioteca-processador` em `/health` antes de iniciar o despachante.

### Processador num servidor separado

O ficheiro `compose.processor.yaml` instala somente o processador. A aplicação e os seus volumes continuam no Railway. O proxy encaminha HTTPS para `gateway:8080`. O gateway aceita um documento de cada vez e autentica o despachante através de uma chave longa partilhada. O contentor que executa ClamAV e LibreOffice tem a rede desactivada e recebe os pedidos por um volume de trabalho. Um terceiro contentor actualiza as assinaturas. Nenhum destes contentores recebe credenciais da base de dados ou monta o acervo. O volume de trabalho contém ficheiros temporários que são removidos após o pedido. Pastas antigas abandonadas por uma interrupção são limpas quando chega um novo pedido.

1. Confirme que o servidor foi autorizado para receber ficheiros em quarentena. Antes da instalação, verifique a memória livre e o espaço em disco para a fila e as imagens. A configuração permite até 4 GiB ao conversor e 3 GiB ao actualizador, cujos picos podem coincidir. Considere a carga dos outros serviços do servidor antes de definir estes limites.
2. Crie no Coolify um recurso Docker Compose a partir da revisão aprovada, com `compose.processor.yaml` como ficheiro de configuração. Defina `ROVUMA_PROCESSOR_TOKEN` como segredo com pelo menos 32 caracteres aleatórios. Aponte um subdomínio técnico autorizado para o proxy e configure HTTPS na porta interna 8080 do serviço `gateway`. Use um proxy com TLS válido e limites de duração e tamanho adequados ao acervo. O endereço público dos leitores e do painel continua o mesmo.
3. Verifique o estado HTTPS em `/health` e confirme que `POST /process` sem a chave devolve 401. Execute a sonda de análise e conversão no conversor com assinaturas oficiais. Para uma instalação pela linha de comandos, execute `docker compose -f compose.processor.yaml exec converter python -m ops.verify_processor`.
4. No serviço Web do Railway configure `ROVUMA_PROCESSOR_URL` com a origem HTTPS do gateway, sem caminho, e `ROVUMA_PROCESSOR_TOKEN` com a mesma chave. Depois de a revisão com suporte a HTTPS estar instalada, use `sh ops/start_railway_web.sh` como comando inicial. Teste primeiro um PDF e um DOCX fictícios no painel. Confirme que chegam a «Pendente de revisão», que o PDF convertido é legível e que só o bibliotecário pode publicar. Se houver falha, reponha o comando inicial Web anterior e mantenha os ficheiros em quarentena enquanto corrige a ligação.

A validação automatizada cria um PostgreSQL e volumes descartáveis e testa o fluxo desde a quarentena até à revisão usando ClamAV e LibreOffice. Usa uma assinatura mínima exclusivamente para verificar a execução da análise sem depender de downloads de assinaturas em CI. A instalação real deve continuar a obter as assinaturas oficiais com `freshclam` e a recusar ficheiros se a análise falhar.

Cópias de volume do Railway, quando configuradas, permitem recuperar volumes dentro do mesmo projecto e ambiente. Para a cópia diária externa e consistente, configure no servidor executor um destino Restic independente autorizado, o ficheiro da palavra-passe e a retenção. O procedimento de cópia e restauro acima aplica-se à instalação Compose, onde a base e os ficheiros podem ser coordenados. Confirme com o responsável o destino de produção antes de transferir documentos ou dados dos utilizadores.
