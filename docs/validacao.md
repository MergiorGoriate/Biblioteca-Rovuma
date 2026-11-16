# Validação e dependências

## Executado

A suite Django cobriu 15 cenários em SQLite e PostgreSQL 16.2. Os cenários incluem autenticação e autorização, sessão anterior à suspensão, activação de utilização única, redefinição de senha, pesquisa e localização de exemplares, bloqueio de descarregamento, respostas parciais, marcadores, versões e importação repetida. A transferência de 101 MiB mais 123 bytes foi concluída depois de uma interrupção simulada e de uma repetição de parte. O processamento em segundo plano com validação estrutural foi seguido pela revisão e publicação de um PDF. O caso DOCX confirma que uma tarefa falhada impede a publicação.

O Chromium emulou computador (1440 × 900) e telemóvel (390 × 844). O ensaio incluiu início de sessão, pesquisa, abertura e navegação no PDF, texto pesquisável, marcador, saída e gestão do acervo e dos estudantes. O teste automatizado pode ser repetido com o ambiente local, Playwright e `python ops/browser_smoke.py`.

O ensaio de recuperação usou PostgreSQL, `pg_dump` e `pg_restore`, com um arquivo separado dos documentos privados. O PDF conservou o SHA-256 após a reaplicação das migrações e voltou a ser servido com autorização depois de restaurado para uma segunda base e directório. As saídas encontram-se em `docs/resultados/`.

## Configuração a validar no servidor de homologação

- O Compose inclui PostgreSQL 17, Caddy, processo em segundo plano com LibreOffice Writer e ClamAV, e volumes privados. A execução completa em contentores, as assinaturas e a conversão real de um DOCX requerem validação nesse ambiente.
- O procedimento de restauro foi ensaiado localmente. A cópia encriptada para um destino remoto com Restic, retenção agendada, renovação de assinaturas e canal de alertas dependem da infra-estrutura escolhida.
- A recuperação de senha foi ensaiada com correio em memória. A confirmação de entrega por SMTP requer as definições institucionais.
- O início de sessão usa credenciais próprias da biblioteca. A ligação ao portal académico depende de confirmação do fornecedor, protocolo, identificador dos estudantes, regras de validação e configuração autorizada.
- A universidade deve confirmar lista de estudantes, periodicidade de credenciamento, direitos de disponibilização das obras, acervo e localizações reais, domínio, capacidade do servidor e responsáveis pela operação.
