# Biblioteca Rovuma

Aplicação Django para o catálogo privado da Biblioteca da Universidade Rovuma. O projecto usa PostgreSQL em produção e suporta SQLite numa instalação local. O nome e a iconografia da interface são apresentados como proposta de trabalho.

## Executar localmente

Requer Python 3.12. Abra um terminal na pasta extraída.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py demo_rovuma
python manage.py runserver 127.0.0.1:8000
```

Abra [Biblioteca Rovuma](http://127.0.0.1:8000). Em Windows use `.venv\Scripts\activate` ou execute `.venv\Scripts\python.exe` directamente. As contas e o acervo seguintes são fictícios e o comando recusa a instalação em produção.

| Perfil | Nome de utilizador | Senha |
|---|---|---|
| Estudante | `000042` | `Rovuma!Demo-42` |
| Bibliotecário | `bibliotecario.demo` | `Acervo!Demo-42` |

Para analisar novos documentos num ambiente local com ficheiros de teste, execute em dois terminais adicionais `python manage.py dispatch_documents` e `python -m documents.worker --spool var/spool`. Instale ClamAV com assinaturas e LibreOffice Writer. Para um ensaio com documentos próprios e inofensivos, a opção explícita `--development-no-antivirus` permite executar o teste estrutural sem ClamAV. A configuração de produção usa o processador em contentor, sem essa opção.

Para executar os testes use `python manage.py test`. Uma instalação com PostgreSQL pode executar a mesma suite definindo as variáveis `POSTGRES_*` e dando ao utilizador de teste permissão para criar a base de dados temporária. O ambiente local usa o backend de correio em memória. Os testes verificam a mensagem e a ligação, enquanto a entrega real requer SMTP.

## Documentação

- [Instalação, actualização e recuperação](docs/operacoes.md)
- [Manual breve do bibliotecário](docs/bibliotecario.md)
- [Diagrama de arquitectura](docs/arquitectura.svg)
- [Modelo de dados](docs/modelo-de-dados.md)
- [Validação efectuada e pendências](docs/validacao.md)

## Limites de leitura e integração

Em Só leitura, o servidor recusa a rota de descarregamento e o leitor omite a opção. A consulta no navegador entrega bytes ao dispositivo e permite que o conteúdo seja copiado ou capturado. A suspensão e a validade são verificadas nos novos pedidos, incluindo os pedidos parciais. Os bytes anteriormente recebidos pelo dispositivo podem permanecer acessíveis ao utilizador.

A integração académica tem campos próprios para origem e identificador do fornecedor. Quando o protocolo for confirmado, o adaptador deverá verificar emissor, audiência, assinatura, estado e nonce, confirmar o mapeamento para uma conta importada e respeitar o credenciamento local. As contas marcadas como institucionais não usam sessões por senha local nem recuperação por SMTP. O sistema não recolhe senhas do portal académico.
