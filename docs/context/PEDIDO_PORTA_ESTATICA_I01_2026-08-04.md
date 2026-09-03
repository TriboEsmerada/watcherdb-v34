# Pedido à equipa de rede — porta TCP estática para SQLHDSTST505\I01

**Data:** 2026-08-04
**Requerente:** equipa WatcherDB
**Instância:** `SQLHDSTST505\I01` (IP 172.17.152.49)
**Prioridade:** média-alta — já causou 11 dias de indisponibilidade de um motor de produto

---

## O pedido, em uma linha

Atribuir e **fixar uma porta TCP estática** à instância nomeada `SQLHDSTST505\I01`,
e **abrir essa porta** no perfil de firewall que cobre a sub-rede
`172.17.0.0/17` (a rede dos postos de trabalho da equipa).

## Porquê

A instância `I01` usa hoje **porta TCP dinâmica** (observada em 50760, mas muda a
cada reinício da instância). O acesso por *nome de instância* (`SQLHDSTST505\I01`)
depende do **SQL Server Browser (UDP 1434)**, que a firewall da empresa **bloqueia**.

Consequência medida (não teórica):
- Ligações por nome de instância falham com `08001 — Unable to complete login
  process due to delay in opening server connection` (timeout de 7-10 minutos).
- O comportamento é **intermitente** (flap): por vezes passa, por vezes não —
  o que torna as falhas difíceis de diagnosticar e mascara indisponibilidades.
- **Impacto real 2026-07-24 a 08-04:** um processo de produção que corre de
  madrugada ficou 11 dias sem executar, sem qualquer alerta, por não conseguir
  ligar à base de dados. Só foi detectado por um verificador construído para o
  efeito.

O acesso por **IP + porta directa** (`172.17.152.49,<porta>`) **contorna** o
Browser e liga em **< 1 segundo**, de forma fiável — provámo-lo repetidamente.
Mas depende de a porta ser conhecida e estável, o que hoje não acontece.

## O que resolve, em concreto

1. **Fixar a porta estática do I01** (SQL Server Configuration Manager → TCP/IP →
   IPAll → *TCP Dynamic Ports* = vazio; *TCP Port* = `<porta escolhida>`; reiniciar
   a instância). Sugestão de porta: manter `50760` se estiver livre, ou atribuir
   uma na gama 49152-65535 acordada com a rede.
2. **Regra de firewall inbound** para essa porta TCP, no perfil que cobre a
   interface pela qual os postos de `172.17.0.0/17` chegam ao servidor.
   (Nota da experiência anterior: a regra tem de cobrir o **perfil da interface**,
   não só a porta — uma regra `-Profile Domain` falha se a interface do lado do
   cliente estiver classificada como `Public`.)

## Alternativa se a porta estática não for possível já

Desbloquear o **UDP 1434 (SQL Browser)** da mesma sub-rede — resolve o mesmo
problema mas é menos seguro (expõe o Browser) e não elimina a porta dinâmica.
A porta estática é preferível.

## Verificação pós-mudança (a equipa WatcherDB corre)

```
Test-NetConnection 172.17.152.49 -Port <porta>      # tem de dar TcpTestSucceeded=True
# e uma ligacao SQL por 172.17.152.49,<porta> tem de ligar em < 1s
```

Assim que a porta estiver fixa e aberta, a configuração dos serviços WatcherDB
passa a `SERVER=172.17.152.49,<porta>` (precedência já suportada no código:
porta manual do servers.json > porta descoberta na BD > SQL Browser) e a
dependência do Browser desaparece.
