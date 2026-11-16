# Validação e dependências

## Executado

A suite Django tem 28 testes e cobre o catálogo privado, o acesso aos PDFs publicados, a recusa de descarregamento, os pedidos parciais, a suspensão, a activação de utilização única, a recuperação, os marcadores, o painel administrativo, os filtros, a fila de documentos e a auditoria por permissões. Inclui emissão e reemissão de convites para funcionários, activação de uso único e acesso ao painel com a função atribuída. Uma base PostgreSQL nova, depois das migrações, ficou sem contas e obras. Verifica ainda erros antes da confirmação de importações, carregamento de 101 MiB com retoma, limpeza de transferências expiradas, capas optimizadas e bloqueio de publicação sem análise concluída.

O ensaio de restauro usou PostgreSQL 16.2, `pg_dump`, `pg_restore` e uma cópia separada dos ficheiros privados. Foi usado um PDF fictício numa base restaurada separada. O SHA-256 coincidiu e o servidor recusou a consulta anónima, servindo um pedido parcial autorizado com HTTP 206. As saídas das validações estão em [resultados](resultados/).

O ensaio de navegação é reproduzível com o ambiente local, Playwright e `python ops/browser_smoke.py`. Utilize as duas palavras-passe que definiu ao criar a demonstração local.

## Configuração a validar no servidor de homologação

- O Compose inclui PostgreSQL 17, Caddy, processo em segundo plano com LibreOffice Writer e ClamAV, e volumes privados. A execução completa em contentores, as assinaturas e a conversão real de um DOCX requerem validação nesse ambiente.
- O procedimento de restauro foi ensaiado localmente. A cópia encriptada para um destino remoto com Restic, retenção agendada, renovação de assinaturas e canal de alertas dependem da infra-estrutura escolhida.
- A recuperação de senha foi ensaiada com correio em memória. A confirmação de entrega por SMTP requer um remetente e um serviço de correio autorizados. O teste da API Resend simula o envio na suite.
- O início de sessão usa credenciais próprias da biblioteca. A ligação ao portal académico depende de confirmação do fornecedor e protocolo (por exemplo, OIDC ou SAML), identificação estável dos estudantes, regras de validação e configuração autorizada.
- A universidade deve confirmar lista de estudantes, periodicidade de credenciamento, direitos de disponibilização das obras, acervo e localizações reais, domínio, capacidade do servidor e responsáveis pela operação.
