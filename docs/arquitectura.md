# Arquitectura da Biblioteca Rovuma

O [diagrama fornecido para o projecto](arquitectura-referencia.png) define a arquitectura funcional. O [diagrama técnico](arquitectura.svg) mostra os serviços, a fila e os volumes usados na instalação com Docker Compose.

| Bloco | Implementação | Operação no endereço actual |
| --- | --- | --- |
| Entrada protegida | HTTPS, autenticação Django e controlo de sessão. A consulta exige conta activa e credenciamento válido. | A entrada HTTPS e o redireccionamento de visitantes sem sessão foram verificados. |
| Contas e permissões | Número institucional guardado como texto, importação validada, activação, suspensão e permissões por função. | Autenticação própria disponível. A integração com o portal académico depende da confirmação do serviço e do protocolo pela universidade. |
| Catálogo, leitura e acervo físico | Pesquisa e filtros num catálogo único. O leitor regista progresso e marcadores. A ficha mostra localização e a quantidade de exemplares catalogados para consulta local. | Funcionalidades disponíveis conforme o perfil, as obras e os exemplares registados. A quantidade resulta do inventário e não indica quantos exemplares estão livres naquele momento. |
| Administração | Painel de acervo, edições, licenças, revisão, publicação e auditoria. A publicação digital exige o processamento concluído e a revisão confirmada. | O bibliotecário gere o acervo com conta individual. O administrador técnico opera a infra-estrutura e só recebe permissões editoriais por atribuição explícita. |
| PostgreSQL e armazenamento privado | Metadados em PostgreSQL. Originais, PDFs de leitura e capas ficam no volume persistente, fora das rotas públicas. O servidor verifica o acesso a cada pedido, incluindo pedidos parciais. | PostgreSQL e volume persistente da aplicação configurados. |
| Processamento | O despachante prepara os trabalhos. Um processador sem rede lê a fila, analisa com ClamAV, valida o formato e converte DOCX com LibreOffice. | O ambiente actual tem aplicação Web e PostgreSQL. O processador isolado ainda precisa de ser instalado e validado. Execute a sonda indicada no [procedimento de instalação](operacoes.md#produção). |
| Cópias e recuperação | O Restic reúne a base e os ficheiros numa cópia coerente, com retenção e destino externo configuráveis. Um restauro local verificou a integridade do PDF e o acesso autorizado. | O agendamento e a cópia externa ainda dependem de um destino aprovado e de um ensaio de restauro nessa infra-estrutura. |

## Fluxos de referência

**Estudante.** Depois da autenticação e da validação do credenciamento, pesquisa no catálogo e abre a ficha da obra. Para exemplares físicos, consulta o inventário e a localização. Para documentos digitais, o servidor verifica a autorização antes de servir páginas ou descarregamentos. A modalidade da versão determina se a aplicação permite descarregar o original.

**Bibliotecário.** Cria o rascunho, regista a licença, escolhe a modalidade e carrega o PDF ou DOCX em partes. Se a análise ou a conversão falhar, a fila apresenta o motivo. Após o processamento, o bibliotecário revê o PDF e confirma a publicação. A substituição preserva a versão anterior no histórico.
