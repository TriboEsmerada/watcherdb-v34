# WatcherDB V3.3 Standard Edition — Clausulas Contratuais Sugeridas

## IMPORTANTE: Este documento NAO substitui aconselhamento juridico.
## Deve ser revisto por um advogado de tecnologia antes de uso comercial.

---

## 1. Limitacao de Responsabilidade

```
O WatcherDB e uma ferramenta de MONITORING e DIAGNOSTICO. O software
fornece informacoes, recomendacoes e alertas baseados em dados recolhidos
dos servidores SQL Server do cliente.

O WatcherDB NAO executa accoes automaticas em servidores de producao.
Todas as accoes correctivas (shrink, rebuild, failover, etc.) requerem
intervencao humana do DBA.

O fornecedor nao se responsabiliza por:
- Decisoes tomadas com base nas recomendacoes do software
- Perda de dados resultante de accoes executadas pelo cliente
- Indisponibilidade causada por falha no SQL Server monitorizado
- Danos indirectos, consequenciais ou perda de lucros

A responsabilidade maxima do fornecedor esta limitada ao valor pago
pelo cliente nos ultimos 12 meses de licenca.
```

## 2. Propriedade Intelectual

```
O codigo-fonte do WatcherDB e propriedade exclusiva do fornecedor.
O cliente recebe uma licenca de USO, nao de propriedade.

E expressamente proibido:
- Descompilar, reverter ou desofuscar o software
- Copiar, redistribuir ou sublicenciar o software
- Modificar o software sem autorizacao escrita
- Usar o software para desenvolver produto concorrente

O cliente e proprietario dos DADOS armazenados na base de dados
WatcherDB_Intelligence. Em caso de termino do contrato, o cliente
mantem acesso total aos seus dados.
```

## 3. Proteccao de Dados (RGPD)

```
O WatcherDB processa METADATA TECNICA de bases de dados SQL Server
(nomes de databases, tabelas, filegroups, metricas de performance).

O WatcherDB NAO acede ao CONTEUDO das tabelas do cliente.

Nos termos do RGPD, o fornecedor actua como SUB-PROCESSADOR.
O cliente (responsavel pelo tratamento) deve:
- Realizar DPIA se as bases monitorizadas contenham dados pessoais
- Incluir o WatcherDB no registo de actividades de tratamento
- Garantir base legal para o monitoring (interesse legitimo)

Todos os dados sao armazenados no servidor do cliente (self-hosted).
Nenhum dado e transmitido para servidores externos.
```

## 4. SLA (Service Level Agreement)

```
Nivel Basico (incluido na licenca):
- Suporte por email em dias uteis (9h-18h, fuso Lisboa)
- Tempo de resposta: 48 horas uteis
- Bug fixes em versoes futuras
- Actualizacoes de seguranca

Nivel Prioritario (add-on +2.000€/ano):
- Suporte por email + telefone
- Tempo de resposta: 4 horas uteis
- Hot fixes criticos em 24 horas
- Acesso a versoes beta
```

## 5. Termino

```
O cliente pode terminar o contrato a qualquer momento com 30 dias
de aviso previo.

Apos termino:
- O cliente mantem acesso aos seus dados na Intelligence DB
- A licenca do software e desactivada
- O cliente deve desinstalar o software em 30 dias
- Nao ha reembolso de licenca anual ja paga
```

## 6. Garantia

```
O fornecedor garante que o software:
- Funciona conforme descrito na documentacao tecnica
- E livre de malware, backdoors ou funcionalidades ocultas
- Recebe actualizacoes de seguranca durante o periodo de licenca

O fornecedor NAO garante:
- Que o software sera livre de bugs (best-effort para corrigir)
- Compatibilidade com versoes futuras do SQL Server ou Windows
- Uptime de 100% (dependente da infraestrutura do cliente)
```

---

## Checklist Juridico (antes de comercializar)

- [ ] Revisar este documento com advogado de tecnologia
- [ ] Criar contrato formal de licenciamento
- [ ] Criar contrato de sub-processamento (Art. 28 RGPD)
- [ ] Criar termos de servico e politica de privacidade
- [ ] Registar marca "WatcherDB" (INPI Portugal / EUIPO)
- [ ] Verificar obrigacoes fiscais (facturacao, IVA)
- [ ] Seguro de responsabilidade profissional (opcional mas recomendado)
