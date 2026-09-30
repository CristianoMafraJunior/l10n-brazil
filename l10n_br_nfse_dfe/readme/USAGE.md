## Configuração

1. Acesse **Configurações > Usuários e Empresas > Empresas**.
2. Abra o cadastro da empresa e localize a aba **Fiscal > NFS-e DF-e (ADN)**.
3. Escolha o **Ambiente** (Produção ou Homologação/produção restrita).
4. Marque **Auto-fetch NFS-e DF-e** para habilitar a consulta periódica via cron — **o cron vem desativado por padrão**, para que cada empresa valide seu próprio certificado antes de ligar a consulta automática.

## Painel de Controle (Dashboard)

Acesse **Faturamento > Fiscal > Consultas DF-e > NFS-e de Terceiros** para ver o painel de status (último NSU, próxima consulta, status da última consulta) e os botões de "Pesquisar Todos" / "Pesquisa Específica".

## Geração de DANFSe

Na lista de documentos, o botão **DANFSE** gera o PDF a partir do XML já armazenado do documento completo.

## Limitação conhecida

Os documentos baixados ficam guardados como anexo bruto (XML), sem serem convertidos em lançamento/despesa no Odoo — a importação não faz parte do escopo deste módulo.
